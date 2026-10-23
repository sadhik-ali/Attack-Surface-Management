"""Company (tenant) management, ownership authorizations and scan policy."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Pagination,
    RequestMeta,
    TenantContext,
    get_current_user,
    get_pagination,
    get_request_meta,
    record_audit,
    require_platform_admin,
    tenant_dependency,
)
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError_
from app.core.permissions import permissions_for
from app.db.session import get_session
from app.models import (
    Alert,
    Asset,
    AuditAction,
    AuditOutcome,
    AuditLog,
    AuthorizationRecord,
    AuthorizationStatus,
    Company,
    CompanyMembership,
    Role,
    Scan,
    ScanPolicy,
    User,
)
from app.schemas.common import MessageResponse, Page, SeverityCounts
from app.schemas.company import (
    AuthorizationCreateRequest,
    AuthorizationDecisionRequest,
    AuthorizationOut,
    CompanyCreateRequest,
    CompanyOut,
    CompanySummary,
    CompanyUpdateRequest,
    ScanPolicyOut,
    ScanPolicyUpdateRequest,
)
from app.services.presenters import company_severity_counts, role_name

router = APIRouter(tags=["Companies"])


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "company"


async def _company_out(session: AsyncSession, company: Company) -> CompanyOut:
    from app.models import Finding
    from app.models.enums import OPEN_FINDING_STATUSES

    member_count = (await session.execute(select(func.count()).select_from(CompanyMembership).where(CompanyMembership.company_id == company.id))).scalar_one()
    authorized = (
        await session.execute(
            select(func.count())
            .select_from(AuthorizationRecord)
            .where(AuthorizationRecord.company_id == company.id, AuthorizationRecord.status == AuthorizationStatus.APPROVED.value)
        )
    ).scalar_one()
    last_scan_at = (await session.execute(select(func.max(Scan.finished_at)).where(Scan.company_id == company.id))).scalar_one()
    counts = await company_severity_counts(session, company.id)
    open_findings = (
        await session.execute(
            select(func.count())
            .select_from(Finding)
            .where(Finding.company_id == company.id, Finding.status.in_(list(OPEN_FINDING_STATUSES)))
        )
    ).scalar_one()

    return CompanyOut(
        id=company.id,
        name=company.name,
        slug=company.slug,
        industry=company.industry,
        status=company.status,
        website=company.website,
        asset_count=company.asset_count,
        risk_score=company.risk_score,
        is_demo_tenant=company.is_demo_tenant,
        description=company.description,
        contact_email=company.contact_email,
        contact_name=company.contact_name,
        root_domains=company.root_domains or [],
        tags=company.tags or [],
        created_at=company.created_at,
        updated_at=company.updated_at,
        member_count=member_count,
        open_findings=open_findings,
        severity_counts=SeverityCounts(**counts),
        authorized_scope_count=authorized,
        last_scan_at=last_scan_at,
    )


@router.get("/companies", response_model=list[CompanySummary])
async def list_companies(
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[CompanySummary]:
    stmt = select(Company)
    if not include_archived:
        stmt = stmt.where(Company.status != "archived")
    if not user.is_super_admin:
        company_ids = [m.company_id for m in user.memberships if m.is_active and permissions_for(m.role_code)]
        if not company_ids:
            return []
        stmt = stmt.where(Company.id.in_(company_ids))
    rows = (await session.execute(stmt.order_by(Company.name))).scalars().all()
    return [CompanySummary.model_validate(c) for c in rows]


@router.post("/companies", response_model=CompanyOut, status_code=201)
async def create_company(
    payload: CompanyCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_platform_admin),
) -> CompanyOut:
    meta = get_request_meta(request)
    slug = payload.slug or _slugify(payload.name)
    existing = (await session.execute(select(Company).where((Company.slug == slug) | (Company.name == payload.name)))).scalar_one_or_none()
    if existing:
        raise ConflictError("A company with that name or slug already exists")

    company = Company(
        name=payload.name.strip(),
        slug=slug,
        description=payload.description,
        industry=payload.industry,
        website=payload.website,
        contact_email=payload.contact_email,
        contact_name=payload.contact_name,
        root_domains=[d.lower().strip() for d in payload.root_domains],
        tags=payload.tags,
    )
    session.add(company)
    await session.flush()

    session.add(
        ScanPolicy(
            company_id=company.id,
            max_concurrency=settings.scan_max_concurrency,
            requests_per_second=settings.scan_requests_per_second,
            allowed_ports=settings.default_scan_ports,
            max_targets_per_run=settings.scan_max_targets_per_run,
        )
    )
    await record_audit(
        session,
        action=AuditAction.COMPANY_CREATED,
        user=admin,
        company_id=company.id,
        meta=meta,
        object_type="company",
        object_id=company.id,
        object_label=company.name,
    )
    await session.flush()
    return await _company_out(session, company)


@router.get("/companies/{company_id}", response_model=CompanyOut)
async def get_company(
    ctx: TenantContext = Depends(tenant_dependency("company:read")),
    session: AsyncSession = Depends(get_session),
) -> CompanyOut:
    return await _company_out(session, ctx.company)


@router.patch("/companies/{company_id}", response_model=CompanyOut)
async def update_company(
    payload: CompanyUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("company:write")),
    session: AsyncSession = Depends(get_session),
) -> CompanyOut:
    meta = get_request_meta(request)
    company = ctx.company
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "root_domains" and value is not None:
            value = [d.lower().strip() for d in value]
        setattr(company, key, value)
    await record_audit(
        session,
        action=AuditAction.COMPANY_UPDATED,
        user=ctx.user,
        company_id=company.id,
        meta=meta,
        object_type="company",
        object_id=company.id,
        object_label=company.name,
        detail={"fields": sorted(updates)},
    )
    return await _company_out(session, company)


# --- members ---------------------------------------------------------------


@router.get("/companies/{company_id}/members")
async def list_members(
    ctx: TenantContext = Depends(tenant_dependency("user:read")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(CompanyMembership, User)
            .join(User, User.id == CompanyMembership.user_id)
            .where(CompanyMembership.company_id == ctx.company.id)
            .order_by(User.full_name)
        )
    ).all()
    return [
        {
            "id": membership.id,
            "user_id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "job_title": user.job_title,
            "role_code": membership.role_code,
            "role_name": role_name(membership.role_code),
            "is_active": membership.is_active and user.is_active,
            "last_login_at": user.last_login_at,
            "expires_at": membership.expires_at,
            "avatar_color": user.avatar_color,
        }
        for membership, user in rows
    ]


@router.post("/companies/{company_id}/members", status_code=201)
async def add_member(
    payload: dict,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("user:write")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    meta = get_request_meta(request)
    user_id = payload.get("user_id")
    email = (payload.get("email") or "").strip().lower()
    role_code = payload.get("role_code")
    if not role_code:
        raise ValidationError_("role_code is required")
    if not user_id and not email:
        raise ValidationError_("Provide user_id or email")

    role = (await session.execute(select(Role).where(Role.code == role_code))).scalar_one_or_none()
    if role is None:
        raise ValidationError_("Unknown role")
    if role_code == "super_admin":
        raise ValidationError_("Super Admin is a platform role and cannot be granted per company")

    user = await session.get(User, user_id) if user_id else (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError(
            "No account uses this email. Ask a platform administrator to create the account first."
            if email and not user_id
            else "User not found"
        )
    user_id = user.id
    existing = (
        await session.execute(
            select(CompanyMembership).where(CompanyMembership.company_id == ctx.company.id, CompanyMembership.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing:
        existing.role_code = role_code
        existing.is_active = True
        membership = existing
    else:
        membership = CompanyMembership(
            company_id=ctx.company.id,
            user_id=user_id,
            role_code=role_code,
            granted_by_id=ctx.user.id,
        )
        session.add(membership)
    await record_audit(
        session,
        action=AuditAction.MEMBERSHIP_GRANTED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="user",
        object_id=user_id,
        object_label=user.email,
        detail={"role": role_code},
    )
    await session.flush()
    return {"id": membership.id, "message": "Membership saved"}


@router.delete("/companies/{company_id}/members/{membership_id}", response_model=MessageResponse)
async def revoke_member(
    membership_id: str,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("user:write")),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    meta = get_request_meta(request)
    membership = await session.get(CompanyMembership, membership_id)
    if membership is None or membership.company_id != ctx.company.id:
        raise NotFoundError("Membership not found")
    if membership.user_id == ctx.user.id:
        raise ValidationError_("You cannot revoke your own access")
    membership.is_active = False
    await record_audit(
        session,
        action=AuditAction.MEMBERSHIP_REVOKED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="user",
        object_id=membership.user_id,
        detail={"role_previous": membership.role_code},
    )
    return MessageResponse(message="Access revoked")


# --- authorizations --------------------------------------------------------


def _auth_out(record: AuthorizationRecord) -> AuthorizationOut:
    data = AuthorizationOut.model_validate(record)
    data.is_live = record.is_live
    return data


@router.get("/companies/{company_id}/authorizations", response_model=list[AuthorizationOut])
async def list_authorizations(
    ctx: TenantContext = Depends(tenant_dependency("company:read")),
    session: AsyncSession = Depends(get_session),
) -> list[AuthorizationOut]:
    rows = (
        await session.execute(
            select(AuthorizationRecord)
            .where(AuthorizationRecord.company_id == ctx.company.id)
            .order_by(AuthorizationRecord.created_at.desc())
        )
    ).scalars().all()
    return [_auth_out(r) for r in rows]


@router.post("/companies/{company_id}/authorizations", response_model=AuthorizationOut, status_code=201)
async def create_authorization(
    payload: AuthorizationCreateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("company:write")),
    session: AsyncSession = Depends(get_session),
) -> AuthorizationOut:
    meta = get_request_meta(request)
    existing = (
        await session.execute(
            select(AuthorizationRecord).where(
                AuthorizationRecord.company_id == ctx.company.id,
                AuthorizationRecord.scope_type == payload.scope_type,
                AuthorizationRecord.value == payload.value,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("An authorization for this scope already exists")

    record = AuthorizationRecord(
        company_id=ctx.company.id,
        scope_type=payload.scope_type,
        value=payload.value,
        method=payload.method,
        evidence=payload.evidence,
        notes=payload.notes,
        expires_at=payload.expires_at,
        allow_active_probing=payload.allow_active_probing,
        max_ports_per_target=payload.max_ports_per_target,
        requested_by_id=ctx.user.id,
        status=AuthorizationStatus.PENDING.value,
    )
    session.add(record)
    await record_audit(
        session,
        action=AuditAction.AUTHORIZATION_CREATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="authorization",
        object_label=payload.value,
        detail={"scope_type": payload.scope_type, "active_probing": payload.allow_active_probing},
    )
    await session.flush()
    return _auth_out(record)


@router.post("/companies/{company_id}/authorizations/{authorization_id}/decision", response_model=AuthorizationOut)
async def decide_authorization(
    authorization_id: str,
    payload: AuthorizationDecisionRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("authorization:approve")),
    session: AsyncSession = Depends(get_session),
) -> AuthorizationOut:
    meta = get_request_meta(request)
    record = await session.get(AuthorizationRecord, authorization_id)
    if record is None or record.company_id != ctx.company.id:
        raise NotFoundError("Authorization record not found")

    if payload.decision == "approved":
        if record.requested_by_id == ctx.user.id and not ctx.user.is_super_admin:
            # Four-eyes rule: the person who requested scope cannot approve it.
            raise ValidationError_("A different administrator must approve this authorization")
        record.status = AuthorizationStatus.APPROVED.value
        record.verified_at = datetime.now(timezone.utc)
        record.verified_by_id = ctx.user.id
        action = AuditAction.AUTHORIZATION_APPROVED
    else:
        record.status = AuthorizationStatus.REJECTED.value
        record.verified_at = datetime.now(timezone.utc)
        record.verified_by_id = ctx.user.id
        action = AuditAction.AUTHORIZATION_REJECTED

    if payload.notes:
        record.notes = payload.notes
    await record_audit(
        session,
        action=action,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="authorization",
        object_id=record.id,
        object_label=record.value,
        detail={"decision": payload.decision},
    )
    return _auth_out(record)


# --- scan policy -----------------------------------------------------------


@router.get("/companies/{company_id}/scan-policy", response_model=ScanPolicyOut)
async def get_scan_policy(
    ctx: TenantContext = Depends(tenant_dependency("scan:read")),
    session: AsyncSession = Depends(get_session),
) -> ScanPolicyOut:
    policy = (await session.execute(select(ScanPolicy).where(ScanPolicy.company_id == ctx.company.id))).scalar_one_or_none()
    if policy is None:
        policy = ScanPolicy(company_id=ctx.company.id, allowed_ports=settings.default_scan_ports)
        session.add(policy)
        await session.flush()
    return ScanPolicyOut.model_validate(policy)


@router.patch("/companies/{company_id}/scan-policy", response_model=ScanPolicyOut)
async def update_scan_policy(
    payload: ScanPolicyUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("settings:write")),
    session: AsyncSession = Depends(get_session),
) -> ScanPolicyOut:
    meta = get_request_meta(request)
    policy = (await session.execute(select(ScanPolicy).where(ScanPolicy.company_id == ctx.company.id))).scalar_one_or_none()
    if policy is None:
        policy = ScanPolicy(company_id=ctx.company.id, allowed_ports=settings.default_scan_ports)
        session.add(policy)
        await session.flush()
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(policy, key, value)
    await record_audit(
        session,
        action=AuditAction.SETTINGS_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="scan_policy",
        object_id=policy.id,
        detail={"fields": sorted(updates)},
    )
    return ScanPolicyOut.model_validate(policy)


# --- audit log -------------------------------------------------------------


@router.get("/companies/{company_id}/audit-logs")
async def list_audit_logs(
    ctx: TenantContext = Depends(tenant_dependency("audit:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    action: str | None = None,
    outcome: str | None = None,
) -> Page[dict]:
    stmt = select(AuditLog).where(AuditLog.company_id == ctx.company.id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(AuditLog.created_at.desc()).offset(pagination.offset).limit(pagination.page_size))
    ).scalars().all()
    items = [
        {
            "id": row.id,
            "actor_email": row.actor_email,
            "actor_role": row.actor_role,
            "action": row.action,
            "outcome": row.outcome,
            "object_type": row.object_type,
            "object_label": row.object_label,
            "ip_address": row.ip_address,
            "detail": row.detail,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return Page.build(items, total, pagination.page, pagination.page_size)
