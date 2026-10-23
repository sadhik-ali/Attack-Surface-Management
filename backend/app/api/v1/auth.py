"""Authentication endpoints."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import RequestMeta, get_current_user, get_request_meta, permissions_for_user, record_audit
from app.core.config import settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.session import get_session
from app.models import AuditAction, AuditOutcome, Company, CompanyMembership, User, clear_login_failures, register_login_failure
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.services.presenters import company_access, user_out

logger = get_logger("asm.auth.api")
router = APIRouter(prefix="/auth", tags=["Authentication"])

# A real hash of an unguessable value. Verifying against it when the account is
# unknown keeps the response time similar to a wrong-password attempt, so login
# latency does not disclose which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password-8f2a1c9d")


async def _load_user(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        select(User)
        .options(selectinload(User.memberships).selectinload(CompanyMembership.company))
        .where(func.lower(User.email) == email.lower())
    )
    return result.scalar_one_or_none()


def _companies_for(session_companies: list[Company], user: User) -> list:
    return [company_access(user, c) for c in session_companies]


async def _accessible_companies(session: AsyncSession, user: User) -> list[Company]:
    if user.is_super_admin:
        rows = await session.execute(select(Company).where(Company.status != "archived").order_by(Company.name))
        return list(rows.scalars().all())
    ids = [m.company_id for m in user.memberships if m.is_active]
    if not ids:
        return []
    rows = await session.execute(select(Company).where(Company.id.in_(ids)).order_by(Company.name))
    return list(rows.scalars().all())


def _issue_tokens(user: User) -> tuple[str, str]:
    access = create_token(user.id, "access", extra_claims={"email": user.email})
    refresh = create_token(user.id, "refresh")
    return access, refresh


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    meta = get_request_meta(request)
    user = await _load_user(session, payload.email)

    if user is None:
        verify_password(payload.password, _DUMMY_HASH)  # constant-ish time
        await record_audit(
            session,
            action=AuditAction.LOGIN_FAILED,
            outcome=AuditOutcome.FAILURE,
            user=None,
            company_id=None,
            meta=meta,
            detail={"email_attempted": payload.email[:320], "reason": "unknown_account"},
        )
        raise UnauthorizedError("Invalid email or password")

    if user.is_locked:
        await record_audit(
            session,
            action=AuditAction.LOGIN_FAILED,
            outcome=AuditOutcome.DENIED,
            user=user,
            company_id=None,
            meta=meta,
            detail={"reason": "account_locked"},
        )
        raise ForbiddenError("This account is temporarily locked. Try again later.")

    if not verify_password(payload.password, user.hashed_password):
        locked = register_login_failure(user, settings.login_max_failed_attempts, settings.login_lockout_minutes)
        await record_audit(
            session,
            action=AuditAction.LOGIN_FAILED,
            outcome=AuditOutcome.FAILURE,
            user=user,
            company_id=None,
            meta=meta,
            detail={"reason": "bad_password", "lockout_triggered": locked},
        )
        raise UnauthorizedError("Invalid email or password")

    if not user.is_active:
        raise ForbiddenError("This account has been disabled")

    clear_login_failures(user)
    companies = await _accessible_companies(session, user)

    # Permissions are resolved per company; the union is what the client uses to
    # decide which navigation items to show. Every request re-checks anyway.
    permission_union: set[str] = set()
    for company in companies:
        permission_union.update(permissions_for_user(user, company.id))

    access, refresh = _issue_tokens(user)
    await record_audit(
        session,
        action=AuditAction.LOGIN,
        user=user,
        company_id=companies[0].id if len(companies) == 1 else None,
        meta=meta,
        detail={"company_count": len(companies)},
    )
    logger.info("login succeeded", extra={"user_id": user.id, "companies": len(companies)})

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
        user=user_out(user),
        permissions=sorted(permission_union),
        companies=_companies_for(companies, user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    meta = get_request_meta(request)
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired refresh token") from exc

    user_id = claims.get("sub", "")
    result = await session.execute(
        select(User).options(selectinload(User.memberships).selectinload(CompanyMembership.company)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("This account is disabled or no longer exists")

    companies = await _accessible_companies(session, user)
    permission_union: set[str] = set()
    for company in companies:
        permission_union.update(permissions_for_user(user, company.id))

    access, refresh = _issue_tokens(user)
    await record_audit(session, action=AuditAction.TOKEN_REFRESH, user=user, company_id=None, meta=meta)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
        user=user_out(user),
        permissions=sorted(permission_union),
        companies=_companies_for(companies, user),
    )


@router.get("/me", response_model=MeResponse)
async def me(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MeResponse:
    companies = await _accessible_companies(session, user)
    permission_union: set[str] = set()
    for company in companies:
        permission_union.update(permissions_for_user(user, company.id))

    return MeResponse(
        user=user_out(user),
        permissions=sorted(permission_union),
        companies=_companies_for(companies, user),
        alert_counts={},
    )


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    meta = get_request_meta(request)
    if not verify_password(payload.current_password, user.hashed_password):
        await record_audit(
            session,
            action=AuditAction.PASSWORD_CHANGE,
            outcome=AuditOutcome.FAILURE,
            user=user,
            company_id=None,
            meta=meta,
            detail={"reason": "wrong_current_password"},
        )
        raise UnauthorizedError("Current password is incorrect")
    if verify_password(payload.new_password, user.hashed_password):
        raise ForbiddenError("The new password must differ from the current one")

    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = False
    await record_audit(session, action=AuditAction.PASSWORD_CHANGE, user=user, company_id=None, meta=meta)
    return MessageResponse(message="Password updated. Sign in again on your other devices.")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    meta = get_request_meta(request)
    await record_audit(session, action=AuditAction.LOGOUT, user=user, company_id=None, meta=meta)
    return MessageResponse(message="Signed out")
