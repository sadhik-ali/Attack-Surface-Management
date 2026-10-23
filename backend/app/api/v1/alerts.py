"""Alert triage, per-user notifications and alert routing preferences."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Pagination,
    TenantContext,
    apply_sort,
    get_any_company_scope,
    get_current_user,
    get_pagination,
    get_request_meta,
    record_audit,
    tenant_dependency,
)
from app.core.errors import NotFoundError, ValidationError_
from app.db.session import get_session
from app.models import (
    Alert,
    AlertPreference,
    AlertStatus,
    AlertType,
    Asset,
    AuditAction,
    Notification,
    NotificationChannel,
    Severity,
    User,
)
from app.models.enums import SEVERITY_ORDER
from app.schemas.alert import (
    AlertAcknowledgeRequest,
    AlertCounts,
    AlertDismissRequest,
    AlertOut,
    AlertPreferenceOut,
    AlertPreferenceUpdateRequest,
    NotificationOut,
)
from app.schemas.common import MessageResponse, Page
from app.services.presenters import alert_out

router = APIRouter(tags=["Alerts & Notifications"])

#: An alert stops being "active" once dismissed or resolved.
ACTIVE_ALERT_STATUSES = [AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]

#: Higher rank = more severe, so a descending sort lists critical alerts first.
SEVERITY_RANK = {name: len(SEVERITY_ORDER) - index for index, name in enumerate(SEVERITY_ORDER)}

ALERT_SORTABLE = {
    "occurred_at": Alert.occurred_at,
    "severity": case(SEVERITY_RANK, value=Alert.severity, else_=0),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _checked_enum(value: str, enum_cls, label: str) -> str:
    allowed = {member.value for member in enum_cls}
    if value not in allowed:
        raise ValidationError_(f"Invalid {label} '{value}'", details={"allowed": sorted(allowed)})
    return value


async def _load_alert(session: AsyncSession, ctx: TenantContext, alert_id: str) -> Alert:
    alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None or alert.company_id != ctx.company.id:
        raise NotFoundError("Alert not found")
    return alert


async def _alert_names(session: AsyncSession, alert: Alert) -> tuple[str | None, str | None]:
    asset_name = None
    if alert.asset_id:
        asset_name = (await session.execute(select(Asset.name).where(Asset.id == alert.asset_id))).scalar_one_or_none()
    acknowledged_by_name = None
    if alert.acknowledged_by_id:
        acknowledged_by_name = (
            await session.execute(select(User.full_name).where(User.id == alert.acknowledged_by_id))
        ).scalar_one_or_none()
    return asset_name, acknowledged_by_name


async def _alert_response(session: AsyncSession, alert: Alert) -> AlertOut:
    asset_name, acknowledged_by_name = await _alert_names(session, alert)
    return alert_out(alert, asset_name=asset_name, acknowledged_by_name=acknowledged_by_name)


async def _load_preferences(session: AsyncSession, ctx: TenantContext) -> AlertPreference:
    preference = (
        await session.execute(
            select(AlertPreference).where(
                AlertPreference.user_id == ctx.user.id,
                AlertPreference.company_id == ctx.company.id,
            )
        )
    ).scalar_one_or_none()
    if preference is None:
        preference = AlertPreference(
            user_id=ctx.user.id,
            company_id=ctx.company.id,
            min_severity=Severity.LOW.value,
            channels=[NotificationChannel.IN_APP.value],
            muted_types=[],
            daily_digest=False,
        )
        session.add(preference)
        await session.flush()
    return preference


@router.get("/companies/{company_id}/alerts", response_model=Page[AlertOut])
async def list_alerts(
    ctx: TenantContext = Depends(tenant_dependency("alert:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    status: str | None = None,
    include_resolved: bool = False,
    severity: str | None = None,
    alert_type: str | None = None,
    asset_id: str | None = None,
    source: str | None = None,
    q: str | None = Query(default=None, max_length=200),
) -> Page[AlertOut]:
    stmt = select(Alert).where(Alert.company_id == ctx.company.id)
    if status:
        stmt = stmt.where(Alert.status == status)
    elif not include_resolved:
        # Default view: the still-actionable alerts only.
        stmt = stmt.where(Alert.status.in_(ACTIVE_ALERT_STATUSES))
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if alert_type:
        stmt = stmt.where(Alert.alert_type == alert_type)
    if asset_id:
        stmt = stmt.where(Alert.asset_id == asset_id)
    if source:
        stmt = stmt.where(Alert.source == source)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Alert.title).like(like), func.lower(Alert.message).like(like)))

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    page_stmt = stmt.add_columns(Asset.name, User.full_name).outerjoin(Asset, Asset.id == Alert.asset_id)
    page_stmt = page_stmt.outerjoin(User, User.id == Alert.acknowledged_by_id)
    page_stmt = apply_sort(page_stmt, ALERT_SORTABLE, pagination, Alert.occurred_at)
    rows = (await session.execute(page_stmt.offset(pagination.offset).limit(pagination.page_size))).all()

    items = [
        alert_out(alert, asset_name=asset_name, acknowledged_by_name=acknowledged_by_name)
        for alert, asset_name, acknowledged_by_name in rows
    ]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/alerts/counts", response_model=AlertCounts)
async def alert_counts(
    ctx: TenantContext = Depends(tenant_dependency("alert:read")),
    session: AsyncSession = Depends(get_session),
) -> AlertCounts:
    status_rows = dict(
        (
            await session.execute(
                select(Alert.status, func.count(Alert.id))
                .where(Alert.company_id == ctx.company.id)
                .group_by(Alert.status)
            )
        ).all()
    )
    severity_rows = dict(
        (
            await session.execute(
                select(Alert.severity, func.count(Alert.id))
                .where(Alert.company_id == ctx.company.id, Alert.status.in_(ACTIVE_ALERT_STATUSES))
                .group_by(Alert.severity)
            )
        ).all()
    )
    unread = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == ctx.user.id,
                Notification.company_id == ctx.company.id,
                Notification.read_at.is_(None),
            )
        )
    ).scalar_one()
    return AlertCounts(
        new=status_rows.get(AlertStatus.NEW.value, 0),
        acknowledged=status_rows.get(AlertStatus.ACKNOWLEDGED.value, 0),
        critical=severity_rows.get(Severity.CRITICAL.value, 0),
        high=severity_rows.get(Severity.HIGH.value, 0),
        unread_notifications=unread,
    )


@router.post("/companies/{company_id}/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: str,
    payload: AlertAcknowledgeRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("alert:write")),
    session: AsyncSession = Depends(get_session),
) -> AlertOut:
    meta = get_request_meta(request)
    alert = await _load_alert(session, ctx, alert_id)
    alert.status = AlertStatus.ACKNOWLEDGED.value
    alert.acknowledged_at = _utcnow()
    alert.acknowledged_by_id = ctx.user.id
    if payload.note:
        alert.payload = {**(alert.payload or {}), "acknowledgement_note": payload.note}

    await record_audit(
        session,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="alert",
        object_id=alert.id,
        object_label=alert.title,
        detail={"alert_type": alert.alert_type, "note": bool(payload.note)},
    )
    return await _alert_response(session, alert)


@router.post("/companies/{company_id}/alerts/{alert_id}/dismiss", response_model=AlertOut)
async def dismiss_alert(
    alert_id: str,
    payload: AlertDismissRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("alert:write")),
    session: AsyncSession = Depends(get_session),
) -> AlertOut:
    meta = get_request_meta(request)
    alert = await _load_alert(session, ctx, alert_id)
    alert.status = AlertStatus.DISMISSED.value
    alert.dismissed_reason = payload.reason

    await record_audit(
        session,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="alert",
        object_id=alert.id,
        object_label=alert.title,
        detail={"action": "dismissed", "reason": payload.reason},
    )
    return await _alert_response(session, alert)


@router.post("/companies/{company_id}/alerts/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(
    alert_id: str,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("alert:write")),
    session: AsyncSession = Depends(get_session),
) -> AlertOut:
    meta = get_request_meta(request)
    alert = await _load_alert(session, ctx, alert_id)
    alert.status = AlertStatus.RESOLVED.value
    alert.resolved_at = _utcnow()

    await record_audit(
        session,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="alert",
        object_id=alert.id,
        object_label=alert.title,
        detail={"action": "resolved"},
    )
    return await _alert_response(session, alert)


# --- notifications ---------------------------------------------------------


@router.get("/notifications", response_model=Page[NotificationOut])
async def list_notifications(
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    unread_only: bool = False,
    scope: tuple[User, list[str]] = Depends(get_any_company_scope),
) -> Page[NotificationOut]:
    user, company_ids = scope
    stmt = select(Notification).where(Notification.user_id == user.id)
    # Cross-company by design: the caller sees their own notifications in every
    # company they belong to, plus platform-level ones with no company.
    if company_ids:
        stmt = stmt.where(or_(Notification.company_id.in_(company_ids), Notification.company_id.is_(None)))
    else:
        stmt = stmt.where(Notification.company_id.is_(None))
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Notification.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
        )
    ).scalars().all()
    items = [NotificationOut.model_validate(row) for row in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.post("/notifications/read-all", response_model=MessageResponse)
async def mark_all_notifications_read(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    meta = get_request_meta(request)
    result = await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=_utcnow())
    )
    marked = result.rowcount or 0
    await record_audit(
        session,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        user=user,
        company_id=None,
        meta=meta,
        object_type="notification",
        detail={"action": "read_all", "count": marked},
    )
    return MessageResponse(message=f"Marked {marked} notifications as read")


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> NotificationOut:
    meta = get_request_meta(request)
    notification = (
        await session.execute(
            select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
        )
    ).scalar_one_or_none()
    if notification is None:
        raise NotFoundError("Notification not found")
    if notification.read_at is None:
        notification.read_at = _utcnow()
    await record_audit(
        session,
        action=AuditAction.ALERT_ACKNOWLEDGED,
        user=user,
        company_id=notification.company_id,
        meta=meta,
        object_type="notification",
        object_id=notification.id,
        object_label=notification.title,
        detail={"action": "read"},
    )
    return NotificationOut.model_validate(notification)


# --- alert preferences -----------------------------------------------------


@router.get("/companies/{company_id}/alert-preferences", response_model=AlertPreferenceOut)
async def get_alert_preferences(
    ctx: TenantContext = Depends(tenant_dependency("alert:read")),
    session: AsyncSession = Depends(get_session),
) -> AlertPreferenceOut:
    preference = await _load_preferences(session, ctx)
    return AlertPreferenceOut.model_validate(preference)


@router.put("/companies/{company_id}/alert-preferences", response_model=AlertPreferenceOut)
async def update_alert_preferences(
    payload: AlertPreferenceUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("alert:write")),
    session: AsyncSession = Depends(get_session),
) -> AlertPreferenceOut:
    meta = get_request_meta(request)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("min_severity") is not None:
        _checked_enum(updates["min_severity"], Severity, "minimum severity")
    if updates.get("channels") is not None:
        for channel in updates["channels"]:
            _checked_enum(channel, NotificationChannel, "notification channel")
    if updates.get("muted_types") is not None:
        for alert_type in updates["muted_types"]:
            _checked_enum(alert_type, AlertType, "alert type")

    preference = await _load_preferences(session, ctx)
    for key, value in updates.items():
        if value is not None:
            setattr(preference, key, value)

    await record_audit(
        session,
        action=AuditAction.SETTINGS_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="alert_preference",
        object_id=preference.id,
        object_label=ctx.user.email,
        detail={"fields": sorted(updates)},
    )
    return AlertPreferenceOut.model_validate(preference)
