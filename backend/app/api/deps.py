"""Request dependencies: authentication, authorization and tenant resolution.

The critical invariant in this module is that **every route handler resolves a
`TenantContext`**, and that context is produced by verifying both the caller's
capability and their membership of the target company. Routes never query by a
client-supplied company id without going through here first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.logging import get_logger
from app.core.permissions import ROLE_DEFINITIONS, permissions_for
from app.core.security import decode_token
from app.db.session import get_session
from app.models import AuditAction, AuditLog, AuditOutcome, Company, CompanyMembership, User

logger = get_logger("asm.auth")


@dataclass(slots=True)
class TenantContext:
    """Authenticated, authorized view of one company for one request."""

    user: User
    company: Company
    role_code: str
    permissions: list[str] = field(default_factory=list)
    request_id: str = ""

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise ForbiddenError(f"Your role ({self.role_code}) does not allow '{permission}'")


@dataclass(slots=True)
class RequestMeta:
    ip_address: str | None
    user_agent: str | None
    request_id: str


def get_request_meta(request: Request) -> RequestMeta:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (forwarded.split(",")[0].strip() if forwarded else None) or (request.client.host if request.client else None)
    return RequestMeta(
        ip_address=ip,
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        request_id=getattr(request.state, "request_id", str(uuid.uuid4())),
    )


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("Missing or malformed Authorization header")
    return token.strip()


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    token = _bearer_token(request)
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired. Sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid authentication token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid authentication token")

    # Memberships are eagerly loaded: `User.effective_role_code` reads them, and
    # a lazy load inside async request handling would raise MissingGreenlet.
    result = await session.execute(
        select(User).options(selectinload(User.memberships).selectinload(CompanyMembership.company)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("This account is disabled or no longer exists")
    if user.is_locked:
        raise ForbiddenError("This account is temporarily locked after repeated failed sign-in attempts")
    return user


def permissions_for_user(user: User, company_id: str | None) -> list[str]:
    role_code = user.effective_role_code(company_id) if company_id else ("super_admin" if user.is_super_admin else "")
    if not role_code:
        return []
    if role_code == "super_admin":
        return permissions_for(role_code)
    # Membership may have expired even though the row is still active.
    if company_id:
        membership = next((m for m in user.memberships if m.company_id == company_id), None)
        if membership is None or not membership.is_active:
            return []
        if membership.expires_at and membership.expires_at < datetime.now(membership.expires_at.tzinfo):
            return []
    return permissions_for(role_code)


async def get_tenant_context(
    company_id: str,
    request: Request,
    session: AsyncSession,
    user: User,
    permission: str,
    *,
    record_denial: bool = True,
) -> TenantContext:
    """Resolve a company for the caller or fail closed.

    A caller without membership receives 404 (not 403) for companies they cannot
    see: responding 403 for an existing company and 404 for a missing one would
    let a member of one tenant enumerate the ids of others.
    """
    meta = get_request_meta(request)
    company = await session.get(Company, company_id)

    if company is None:
        raise NotFoundError("Company not found")

    role_code = user.effective_role_code(company.id)
    perms = permissions_for_user(user, company.id)

    if not role_code:
        if record_denial:
            await record_audit(
                session,
                action=AuditAction.ACCESS_DENIED,
                outcome=AuditOutcome.DENIED,
                user=user,
                company_id=None,
                meta=meta,
                detail={"reason": "no membership", "requested_company": company_id, "path": request.url.path},
            )
        raise NotFoundError("Company not found")

    if permission not in perms:
        if record_denial:
            await record_audit(
                session,
                action=AuditAction.ACCESS_DENIED,
                outcome=AuditOutcome.DENIED,
                user=user,
                company_id=company.id,
                meta=meta,
                detail={"reason": "missing permission", "permission": permission, "role": role_code, "path": request.url.path},
            )
        raise ForbiddenError(f"Your role ({ROLE_DEFINITIONS.get(role_code, {}).get('name', role_code)}) cannot perform this action")

    return TenantContext(user=user, company=company, role_code=role_code, permissions=perms, request_id=meta.request_id)


def tenant_dependency(permission: str):
    """FastAPI dependency factory: `Depends(tenant_dependency('asset:read'))`.

    The returned coroutine declares explicit parameters, so FastAPI resolves the
    path's `company_id` and the shared request/session dependencies normally.
    """

    async def guard(
        company_id: str,
        request: Request,
        session: AsyncSession = Depends(get_session),
        user: User = Depends(get_current_user),
    ) -> TenantContext:
        return await get_tenant_context(company_id, request, session, user, permission)

    guard.required_permission = permission  # type: ignore[attr-defined]
    return guard


async def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    """Gate for platform-level operations that are not scoped to one tenant."""
    if not user.is_super_admin:
        raise ForbiddenError("Platform administrator access is required")
    return user


async def get_any_company_scope(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> tuple[User, list[str]]:
    """Every company id the caller may read, for cross-tenant list endpoints."""
    if user.is_super_admin:
        ids = (await session.execute(select(Company.id).where(Company.status != "archived"))).scalars().all()
        return user, list(ids)
    valid = []
    for membership in user.memberships:
        if membership.is_active and permissions_for_user(user, membership.company_id):
            valid.append(membership.company_id)
    return user, valid


async def record_audit(
    session: AsyncSession,
    *,
    action: AuditAction,
    user: User | None,
    company_id: str | None,
    meta: RequestMeta,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    object_type: str | None = None,
    object_id: str | None = None,
    object_label: str | None = None,
    detail: dict | None = None,
) -> None:
    """Append an audit entry. Never raises: an audit failure must not 500 a request."""
    try:
        session.add(
            AuditLog(
                company_id=company_id,
                actor_id=user.id if user else None,
                actor_email=user.email if user else None,
                actor_role=user.role_code if user else None,
                action=action.value,
                outcome=outcome.value,
                object_type=object_type,
                object_id=object_id,
                object_label=object_label,
                ip_address=meta.ip_address,
                user_agent=meta.user_agent,
                request_id=meta.request_id,
                detail=detail or {},
            )
        )
        await session.flush()
    except Exception:  # pragma: no cover - never block the request on an audit write
        logger.exception("failed to write audit entry", extra={"action": str(action)})


class Pagination:
    def __init__(
        self,
        page: int = 1,
        page_size: int = 25,
        sort: str | None = None,
        order: str = "desc",
    ) -> None:
        self.page = max(1, page)
        self.page_size = min(200, max(1, page_size))
        self.sort = sort
        self.order = order if order in {"asc", "desc"} else "desc"
        self.offset = (self.page - 1) * self.page_size


async def get_pagination(page: int = 1, page_size: int = 25, sort: str | None = None, order: str = "desc") -> Pagination:
    return Pagination(page=page, page_size=page_size, sort=sort, order=order)


def apply_sort(stmt, column_map: dict, pagination: Pagination, default):
    """Apply a whitelisted sort key; unknown keys fall back instead of erroring on user input."""
    column = column_map.get(pagination.sort or "", default)
    direction = column.desc() if pagination.order == "desc" else column.asc()
    return stmt.order_by(direction)
