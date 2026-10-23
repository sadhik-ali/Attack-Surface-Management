"""SSL/TLS certificate API: monitored certificates, expiry health and detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, TenantContext, get_pagination, tenant_dependency
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import Asset, Certificate
from app.schemas.certificate import CertificateHealth, CertificateOut
from app.schemas.common import Page
from app.services.presenters import certificate_out

router = APIRouter(tags=["SSL/TLS Certificates"])

CERTIFICATE_SORTABLE = {
    "not_after": Certificate.not_after,
    "host": Certificate.host,
    "days_remaining": Certificate.days_remaining,
}

EXPIRY_BUCKETS = [
    ("0-7 days", "7d"),
    ("8-30 days", "30d"),
    ("31-90 days", "90d"),
    ("90+ days", "beyond"),
    ("expired", "expired"),
]


def _apply_certificate_sort(stmt, pagination: Pagination):
    key = pagination.sort if pagination.sort in CERTIFICATE_SORTABLE else "not_after"
    column = CERTIFICATE_SORTABLE[key]
    if key != "not_after":
        return stmt.order_by(column.asc()) if pagination.order == "asc" else stmt.order_by(column.desc())
    ascending = pagination.sort is None or pagination.order == "asc"
    return stmt.order_by(column.asc().nullslast()) if ascending else stmt.order_by(column.desc().nullslast())


@router.get("/companies/{company_id}/certificates", response_model=Page[CertificateOut])
async def list_certificates(
    ctx: TenantContext = Depends(tenant_dependency("certificate:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    status: str | None = None,
    expires_within_days: int | None = Query(default=None, ge=0),
    expired: bool | None = None,
    hostname_mismatch: bool | None = None,
    self_signed: bool | None = None,
    port: int | None = Query(default=None, ge=0, le=65535),
) -> Page[CertificateOut]:
    stmt = (
        select(Certificate, Asset.name)
        .outerjoin(Asset, Certificate.asset_id == Asset.id)
        .where(Certificate.company_id == ctx.company.id)
    )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Certificate.host).like(like),
                func.lower(Certificate.subject_common_name).like(like),
                func.lower(Certificate.issuer_common_name).like(like),
            )
        )
    if status:
        stmt = stmt.where(func.lower(Certificate.status) == status.lower())
    if expires_within_days is not None:
        stmt = stmt.where(
            Certificate.not_after.is_not(None),
            Certificate.days_remaining.is_not(None),
            Certificate.days_remaining <= expires_within_days,
        )
    if expired is not None:
        stmt = stmt.where(Certificate.is_expired.is_(expired))
    if hostname_mismatch is not None:
        stmt = stmt.where(Certificate.hostname_matches.is_(not hostname_mismatch))
    if self_signed is not None:
        stmt = stmt.where(Certificate.is_self_signed.is_(self_signed))
    if port is not None:
        stmt = stmt.where(Certificate.port == port)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = _apply_certificate_sort(stmt, pagination)
    rows = (await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))).all()
    items = [certificate_out(cert, asset_name=asset_name) for cert, asset_name in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/certificates/health", response_model=CertificateHealth)
async def certificate_health(
    ctx: TenantContext = Depends(tenant_dependency("certificate:read")),
    session: AsyncSession = Depends(get_session),
) -> CertificateHealth:
    company_filter = Certificate.company_id == ctx.company.id
    status_rows = (
        await session.execute(
            select(
                Certificate.status,
                func.count(Certificate.id),
                func.coalesce(func.sum(case((Certificate.hostname_matches.is_(False), 1), else_=0)), 0),
                func.coalesce(func.sum(case((Certificate.is_self_signed.is_(True), 1), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (or_(Certificate.weak_key.is_(True), Certificate.deprecated_signature.is_(True)), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .where(company_filter)
            .group_by(Certificate.status)
        )
    ).all()

    by_status: dict[str, int] = {}
    hostname_mismatch = 0
    self_signed = 0
    weak_crypto = 0
    for status, count, mismatched, self_signed_count, weak_count in status_rows:
        by_status[str(getattr(status, "value", status))] = count
        hostname_mismatch += mismatched
        self_signed += self_signed_count
        weak_crypto += weak_count

    closest_expiry_days = (
        await session.execute(
            select(func.min(Certificate.days_remaining)).where(
                company_filter,
                Certificate.is_expired.is_(False),
                Certificate.days_remaining.is_not(None),
                Certificate.days_remaining >= 0,
            )
        )
    ).scalar_one()

    bucket = case(
        (Certificate.is_expired.is_(True), "expired"),
        (Certificate.days_remaining.is_(None), "unknown"),
        (Certificate.days_remaining < 0, "expired"),
        (Certificate.days_remaining <= 7, "7d"),
        (Certificate.days_remaining <= 30, "30d"),
        (Certificate.days_remaining <= 90, "90d"),
        else_="beyond",
    )
    bucket_counts = {key: 0 for _, key in EXPIRY_BUCKETS}
    bucket_rows = (
        await session.execute(
            select(bucket, func.count(Certificate.id)).where(company_filter).group_by(bucket)
        )
    ).all()
    for key, count in bucket_rows:
        if key in bucket_counts:
            bucket_counts[key] += count

    issuer_rows = (
        await session.execute(
            select(Certificate.issuer_organization, func.count(Certificate.id))
            .where(company_filter, Certificate.issuer_organization.is_not(None))
            .group_by(Certificate.issuer_organization)
            .order_by(func.count(Certificate.id).desc())
            .limit(5)
        )
    ).all()

    return CertificateHealth(
        total=sum(by_status.values()),
        valid=by_status.get("valid", 0),
        expiring_soon=by_status.get("expiring_soon", 0),
        expired=by_status.get("expired", 0),
        hostname_mismatch=hostname_mismatch,
        self_signed=self_signed,
        weak_crypto=weak_crypto,
        not_observed=by_status.get("not_observed", 0),
        closest_expiry_days=closest_expiry_days,
        expiry_buckets=[
            {"label": label, "key": key, "count": bucket_counts[key]} for label, key in EXPIRY_BUCKETS
        ],
        issuers=[{"issuer": issuer, "count": count} for issuer, count in issuer_rows],
    )


@router.get("/companies/{company_id}/certificates/{certificate_id}", response_model=CertificateOut)
async def certificate_detail(
    certificate_id: str,
    ctx: TenantContext = Depends(tenant_dependency("certificate:read")),
    session: AsyncSession = Depends(get_session),
) -> CertificateOut:
    row = (
        await session.execute(
            select(Certificate, Asset.name)
            .outerjoin(Asset, Certificate.asset_id == Asset.id)
            .where(Certificate.id == certificate_id, Certificate.company_id == ctx.company.id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Certificate not found")
    return certificate_out(row[0], asset_name=row[1])
