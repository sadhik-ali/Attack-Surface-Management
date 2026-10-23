"""Configuration change history: detection timeline, acknowledgement and summary.

There is no dedicated `change:write` capability in the RBAC matrix, so
acknowledging a change is gated on `alert:write` (the permission that already
covers acknowledging the alert a suspicious change raises).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Pagination,
    TenantContext,
    apply_sort,
    get_pagination,
    get_request_meta,
    record_audit,
    tenant_dependency,
)
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import Asset, AuditAction, ChangeType, ConfigurationChange
from app.models.enums import SEVERITY_ORDER
from app.schemas.common import Page
from app.schemas.dashboard import ConfigurationChangeOut
from app.services.presenters import change_out

router = APIRouter(tags=["Configuration Changes"])

#: Higher rank = more severe, so a descending sort lists critical changes first.
SEVERITY_RANK = {name: len(SEVERITY_ORDER) - index for index, name in enumerate(SEVERITY_ORDER)}

CHANGE_SORTABLE = {
    "occurred_at": ConfigurationChange.occurred_at,
    "severity": case(SEVERITY_RANK, value=ConfigurationChange.severity, else_=0),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _load_change(session: AsyncSession, ctx: TenantContext, change_id: str) -> ConfigurationChange:
    change = (
        await session.execute(select(ConfigurationChange).where(ConfigurationChange.id == change_id))
    ).scalar_one_or_none()
    if change is None or change.company_id != ctx.company.id:
        raise NotFoundError("Configuration change not found")
    return change


async def _asset_name(session: AsyncSession, asset_id: str | None) -> str | None:
    if not asset_id:
        return None
    return (await session.execute(select(Asset.name).where(Asset.id == asset_id))).scalar_one_or_none()


@router.get("/companies/{company_id}/changes", response_model=Page[ConfigurationChangeOut])
async def list_changes(
    ctx: TenantContext = Depends(tenant_dependency("change:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    change_type: str | None = None,
    severity: str | None = None,
    asset_id: str | None = None,
    suspicious_only: bool = False,
    unplanned_only: bool = False,
    acknowledged: bool | None = None,
    since: datetime | None = None,
) -> Page[ConfigurationChangeOut]:
    stmt = select(ConfigurationChange).where(ConfigurationChange.company_id == ctx.company.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(ConfigurationChange.summary).like(like),
                func.lower(ConfigurationChange.field).like(like),
            )
        )
    if change_type:
        stmt = stmt.where(ConfigurationChange.change_type == change_type)
    if severity:
        stmt = stmt.where(ConfigurationChange.severity == severity)
    if asset_id:
        stmt = stmt.where(ConfigurationChange.asset_id == asset_id)
    if suspicious_only:
        stmt = stmt.where(ConfigurationChange.is_suspicious.is_(True))
    if unplanned_only:
        stmt = stmt.where(ConfigurationChange.is_unplanned_exposure.is_(True))
    if acknowledged is not None:
        stmt = stmt.where(
            ConfigurationChange.acknowledged_at.is_not(None)
            if acknowledged
            else ConfigurationChange.acknowledged_at.is_(None)
        )
    if since is not None:
        stmt = stmt.where(ConfigurationChange.occurred_at >= since)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    page_stmt = stmt.add_columns(Asset.name).outerjoin(Asset, Asset.id == ConfigurationChange.asset_id)
    page_stmt = apply_sort(page_stmt, CHANGE_SORTABLE, pagination, ConfigurationChange.occurred_at)
    rows = (await session.execute(page_stmt.offset(pagination.offset).limit(pagination.page_size))).all()

    items = [change_out(change, asset_name=asset_name) for change, asset_name in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/changes/summary")
async def changes_summary(
    ctx: TenantContext = Depends(tenant_dependency("change:read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    since = _utcnow() - timedelta(days=30)
    base = select(func.count()).select_from(ConfigurationChange).where(
        ConfigurationChange.company_id == ctx.company.id,
        ConfigurationChange.occurred_at >= since,
    )
    total_30d = (await session.execute(base)).scalar_one()
    suspicious_30d = (
        await session.execute(
            base.where(ConfigurationChange.is_suspicious.is_(True))
        )
    ).scalar_one()
    unplanned_30d = (
        await session.execute(
            base.where(ConfigurationChange.is_unplanned_exposure.is_(True))
        )
    ).scalar_one()

    type_rows = dict(
        (
            await session.execute(
                select(ConfigurationChange.change_type, func.count(ConfigurationChange.id))
                .where(
                    ConfigurationChange.company_id == ctx.company.id,
                    ConfigurationChange.occurred_at >= since,
                )
                .group_by(ConfigurationChange.change_type)
            )
        ).all()
    )
    severity_rows = dict(
        (
            await session.execute(
                select(ConfigurationChange.severity, func.count(ConfigurationChange.id))
                .where(
                    ConfigurationChange.company_id == ctx.company.id,
                    ConfigurationChange.occurred_at >= since,
                )
                .group_by(ConfigurationChange.severity)
            )
        ).all()
    )

    return {
        "total_30d": total_30d,
        "suspicious_30d": suspicious_30d,
        "unplanned_exposure_30d": unplanned_30d,
        "by_type": [{"type": member.value, "count": type_rows.get(member.value, 0)} for member in ChangeType],
        "by_severity": [{"severity": name, "count": severity_rows.get(name, 0)} for name in SEVERITY_ORDER],
    }


@router.post("/companies/{company_id}/changes/{change_id}/acknowledge", response_model=ConfigurationChangeOut)
async def acknowledge_change(
    change_id: str,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("alert:write")),
    session: AsyncSession = Depends(get_session),
) -> ConfigurationChangeOut:
    meta = get_request_meta(request)
    change = await _load_change(session, ctx, change_id)
    change.acknowledged_at = _utcnow()
    change.acknowledged_by_id = ctx.user.id

    await record_audit(
        session,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="configuration_change",
        object_id=change.id,
        object_label=change.summary,
        detail={"action": "change_acknowledged", "change_type": change.change_type},
    )
    return change_out(change, asset_name=await _asset_name(session, change.asset_id))
