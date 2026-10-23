"""Platform user directory.

Account creation is a platform-level operation. Company administrators manage
which users belong to their company (and with which role) through the membership
endpoints in `companies.py`; they never create accounts here.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    Pagination,
    RequestMeta,
    apply_sort,
    get_pagination,
    get_request_meta,
    record_audit,
    require_platform_admin,
)
from app.core.errors import ConflictError, NotFoundError, ValidationError_
from app.core.permissions import ROLE_DEFINITIONS, is_valid_role
from app.core.security import hash_password
from app.db.session import get_session
from app.models import AuditAction, Company, CompanyMembership, User
from app.schemas.auth import UserCreateRequest, UserOut, UserUpdateRequest
from app.schemas.common import Page
from app.services.presenters import user_out

router = APIRouter(tags=["Users"])

SORTABLE = {
    "email": User.email,
    "full_name": User.full_name,
    "created_at": User.created_at,
    "last_login_at": User.last_login_at,
}


def _avatar_color() -> str:
    palette = ["#2563eb", "#0ea5e9", "#14b8a6", "#8b5cf6", "#f59e0b", "#ef4444", "#10b981"]
    return palette[secrets.randbelow(len(palette))]


def _validate_password(value: str) -> None:
    if not any(c.isupper() for c in value) or not any(c.islower() for c in value) or not any(c.isdigit() for c in value):
        raise ValidationError_(
            "Password must include at least one uppercase letter, one lowercase letter and one digit",
            details={"field": "password"},
        )


async def _load_user(session: AsyncSession, user_id: str) -> User:
    user = (
        await session.execute(
            select(User).options(selectinload(User.memberships).selectinload(CompanyMembership.company)).where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    return user


@router.get("/users", response_model=Page[UserOut], summary="List platform users")
async def list_users(
    _admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    role_code: str | None = None,
    is_active: bool | None = None,
) -> Page[UserOut]:
    stmt = select(User).options(selectinload(User.memberships).selectinload(CompanyMembership.company))
    count_stmt = select(func.count()).select_from(User)
    if q:
        like = f"%{q.lower()}%"
        condition = or_(func.lower(User.email).like(like), func.lower(User.full_name).like(like))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    if role_code:
        stmt = stmt.where(User.role_code == role_code)
        count_stmt = count_stmt.where(User.role_code == role_code)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
        count_stmt = count_stmt.where(User.is_active == is_active)
    total = (await session.execute(count_stmt)).scalar_one()
    stmt = apply_sort(stmt, SORTABLE, pagination, User.created_at)
    users = (await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))).scalars().all()
    return Page.build([user_out(user) for user in users], total, pagination.page, pagination.page_size)


@router.post("/users", response_model=UserOut, status_code=201, summary="Create a user account")
async def create_user(
    payload: UserCreateRequest,
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
    meta: RequestMeta = Depends(get_request_meta),
) -> UserOut:
    if not is_valid_role(payload.role_code):
        raise ValidationError_("Unknown role", details={"allowed": sorted(ROLE_DEFINITIONS)})
    _validate_password(payload.password)

    email = str(payload.email).lower()
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("An account with this email already exists")

    company: Company | None = None
    if payload.role_code != "super_admin":
        if not payload.company_id:
            raise ValidationError_("A company_id is required for tenant-scoped roles", details={"field": "company_id"})
        company = await session.get(Company, payload.company_id)
        if company is None:
            raise NotFoundError("Company not found")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        job_title=payload.job_title,
        hashed_password=hash_password(payload.password),
        role_code=payload.role_code,
        must_change_password=True,
        avatar_color=_avatar_color(),
    )
    session.add(user)
    await session.flush()

    if company is not None:
        session.add(
            CompanyMembership(
                company_id=company.id,
                user_id=user.id,
                role_code=payload.role_code,
                granted_by_id=admin.id,
            )
        )
    await record_audit(
        session,
        action=AuditAction.USER_CREATED,
        user=admin,
        company_id=company.id if company else None,
        meta=meta,
        object_type="user",
        object_id=user.id,
        object_label=user.email,
        detail={"role_code": payload.role_code, "company_id": company.id if company else None},
    )
    await session.commit()
    return user_out(await _load_user(session, user.id))


@router.patch("/users/{user_id}", response_model=UserOut, summary="Update a user account")
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    admin: User = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
    meta: RequestMeta = Depends(get_request_meta),
) -> UserOut:
    user = await _load_user(session, user_id)
    updates = payload.model_dump(exclude_unset=True)

    if "role_code" in updates and updates["role_code"] is not None:
        if not is_valid_role(updates["role_code"]):
            raise ValidationError_("Unknown role", details={"allowed": sorted(ROLE_DEFINITIONS)})
        if user.is_super_admin and updates["role_code"] != "super_admin":
            remaining = (
                await session.execute(
                    select(func.count())
                    .select_from(User)
                    .where(User.role_code == "super_admin", User.is_active.is_(True), User.id != user.id)
                )
            ).scalar_one()
            if remaining == 0:
                raise ConflictError("At least one active Super Admin must remain")
    if updates.get("is_active") is False:
        if user.id == admin.id:
            raise ValidationError_("You cannot disable your own account")
        if user.is_super_admin:
            remaining = (
                await session.execute(
                    select(func.count())
                    .select_from(User)
                    .where(User.role_code == "super_admin", User.is_active.is_(True), User.id != user.id)
                )
            ).scalar_one()
            if remaining == 0:
                raise ConflictError("At least one active Super Admin must remain")

    for key, value in updates.items():
        setattr(user, key, value)
    await record_audit(
        session,
        action=AuditAction.USER_DISABLED if updates.get("is_active") is False else AuditAction.USER_UPDATED,
        user=admin,
        company_id=None,
        meta=meta,
        object_type="user",
        object_id=user.id,
        object_label=user.email,
        detail={"fields": sorted(updates)},
    )
    await session.commit()
    return user_out(await _load_user(session, user.id))
