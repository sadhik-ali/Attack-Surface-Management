"""Finding and alert creation shared by scanning and manual workflows."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Alert, AlertPreference, AlertStatus, AlertType, Asset, CompanyMembership, Confidence, Finding, FindingStatus, Notification, RecordSource, Severity, User
from app.models.enums import OPEN_FINDING_STATUSES
from app.services.risk import assess_finding

logger = get_logger("asm.findings")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def fingerprint_for(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


async def upsert_finding(
    session: AsyncSession,
    *,
    asset: Asset,
    finding_type: str,
    title: str,
    severity: str,
    description: str | None = None,
    evidence: str | None = None,
    recommendation: str | None = None,
    confidence: str = Confidence.CONFIRMED.value,
    source: str = RecordSource.ACTIVE_HTTP_PROBE.value,
    cvss: float | None = None,
    service_id: str | None = None,
    certificate_id: str | None = None,
    change_id: str | None = None,
    scan_id: str | None = None,
    has_known_exploit: bool = False,
    extra_key: str = "",
) -> tuple[Finding, bool]:
    """Create a finding, or refresh the existing open one.

    Returns (finding, created). Re-running a scan must not multiply findings for
    the same condition, so identity is the stable fingerprint rather than the
    scan run.
    """
    fingerprint = fingerprint_for(asset.company_id, asset.id, finding_type, title, extra_key)
    existing = (
        await session.execute(
            select(Finding).where(Finding.company_id == asset.company_id, Finding.fingerprint == fingerprint)
        )
    ).scalar_one_or_none()

    if existing is not None and existing.status in OPEN_FINDING_STATUSES:
        existing.last_verified_at = utcnow()
        existing.evidence = evidence or existing.evidence
        existing.scan_id = scan_id or existing.scan_id
        return existing, False

    assessed = assess_finding(
        severity=severity,
        asset_type=asset.asset_type,
        exposure=asset.exposure,
        criticality=asset.criticality,
        confidence=confidence,
        cvss=cvss,
        has_known_exploit=has_known_exploit,
    )

    if existing is not None:
        # A previously closed finding that reoccurs is reopened rather than
        # duplicated, preserving its history.
        existing.status = FindingStatus.OPEN.value
        existing.reopen_count = (existing.reopen_count or 0) + 1
        existing.closed_at = None
        existing.remediated_at = None
        existing.last_verified_at = utcnow()
        existing.severity = severity
        existing.risk_score = assessed.score
        existing.score_factors = assessed.factors_dict()
        existing.evidence = evidence or existing.evidence
        existing.scan_id = scan_id
        existing.source = source
        return existing, False

    finding = Finding(
        company_id=asset.company_id,
        asset_id=asset.id,
        fingerprint=fingerprint,
        finding_type=finding_type,
        title=title[:400],
        description=description,
        evidence=evidence,
        severity=severity,
        confidence=confidence,
        status=FindingStatus.OPEN.value,
        risk_score=assessed.score,
        score_factors=assessed.factors_dict(),
        cvss_base_score=cvss,
        exposure=asset.exposure,
        business_impact=asset.criticality,
        recommendation=recommendation,
        service_id=service_id,
        certificate_id=certificate_id,
        change_id=change_id,
        scan_id=scan_id,
        source=source,
        discovered_at=utcnow(),
        last_verified_at=utcnow(),
    )
    session.add(finding)
    await session.flush()
    return finding, True


async def upsert_alert(
    session: AsyncSession,
    *,
    company_id: str,
    dedupe_key: str,
    alert_type: AlertType,
    severity: str,
    title: str,
    message: str,
    recommendation: str | None = None,
    asset_id: str | None = None,
    finding_id: str | None = None,
    certificate_id: str | None = None,
    change_id: str | None = None,
    scan_id: str | None = None,
    source: str = RecordSource.PASSIVE_DNS.value,
    payload: dict | None = None,
    notify: bool = True,
) -> tuple[Alert, bool]:
    existing = (
        await session.execute(select(Alert).where(Alert.company_id == company_id, Alert.dedupe_key == dedupe_key))
    ).scalar_one_or_none()

    if existing is not None:
        existing.occurrence_count = (existing.occurrence_count or 1) + 1
        existing.last_occurred_at = utcnow()
        existing.message = message
        existing.severity = severity
        if existing.status == AlertStatus.RESOLVED.value:
            existing.status = AlertStatus.NEW.value
            existing.resolved_at = None
        return existing, False

    alert = Alert(
        company_id=company_id,
        alert_type=alert_type.value,
        severity=severity,
        status=AlertStatus.NEW.value,
        title=title[:400],
        message=message,
        recommendation=recommendation,
        dedupe_key=dedupe_key[:200],
        asset_id=asset_id,
        finding_id=finding_id,
        certificate_id=certificate_id,
        change_id=change_id,
        scan_id=scan_id,
        payload=payload or {},
        channels=["in_app"],
        source=source,
        occurred_at=utcnow(),
        last_occurred_at=utcnow(),
    )
    session.add(alert)
    await session.flush()

    if notify:
        await notify_company_users(session, alert)
    return alert, True


async def notify_company_users(session: AsyncSession, alert: Alert) -> int:
    """Fan the alert out to the in-app notification centre.

    Only users with an active membership of the owning company receive it, which
    keeps notifications inside the tenant boundary. Each recipient's stored
    preference is applied: minimum severity, muted alert types and the in-app
    channel. Users without a preference row get the same defaults the
    preferences endpoint would create (low and above, in-app).
    """
    recipients = (
        await session.execute(
            select(User)
            .join(CompanyMembership, CompanyMembership.user_id == User.id)
            .where(
                CompanyMembership.company_id == alert.company_id,
                CompanyMembership.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
    ).scalars().all()

    unique_recipients = list({user.id: user for user in recipients}.values())
    preferences: dict[str, AlertPreference] = {}
    if unique_recipients:
        rows = (
            await session.execute(
                select(AlertPreference).where(
                    AlertPreference.user_id.in_([user.id for user in unique_recipients]),
                    AlertPreference.company_id.in_([alert.company_id, None]),
                )
            )
        ).scalars().all()
        for row in rows:
            if row.company_id == alert.company_id:
                preferences[row.user_id] = row
            else:
                preferences.setdefault(row.user_id, row)

    created = 0
    for user in unique_recipients:
        preference = preferences.get(user.id)
        minimum = preference.min_severity if preference is not None else Severity.LOW.value
        channels = preference.channels if preference is not None else ["in_app"]
        muted_types = preference.muted_types if preference is not None else []
        if not severity_meets(alert.severity, minimum):
            continue
        if alert.alert_type in muted_types:
            continue
        if "in_app" not in channels:
            continue
        session.add(
            Notification(
                user_id=user.id,
                alert_id=alert.id,
                company_id=alert.company_id,
                title=alert.title,
                message=alert.message[:500] if alert.message else None,
                severity=alert.severity,
                channel="in_app",
            )
        )
        created += 1
    return created


def severity_meets(severity: str, minimum: str) -> bool:
    order = [Severity.CRITICAL.value, Severity.HIGH.value, Severity.MEDIUM.value, Severity.LOW.value, Severity.INFORMATIONAL.value]
    try:
        return order.index(severity) <= order.index(minimum)
    except ValueError:
        return True
