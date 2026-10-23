"""Asset registration, upsert and risk roll-up.

One service used by three callers so an asset created by CSV import, manual
registration or the discovery engine ends up with identical invariants:
normalised identity, provenance, a timeline event, and a recomputed risk score.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError_
from app.models import Asset, AssetEvent, AssetEventType, AssetStatus, AssetType, Company, ConfigurationChange, Finding, RecordSource
from app.models.enums import OBSERVED_SOURCES, OPEN_FINDING_STATUSES
from app.services.risk import aggregate_asset_risk, assess_finding

VALID_TYPES = {t.value for t in AssetType}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_identifier(asset_type: str, name: str) -> str:
    """Canonical identity for dedupe. Two discoveries of the same host collide here."""
    value = name.strip().lower().rstrip(".")
    if asset_type in {AssetType.DOMAIN.value, AssetType.SUBDOMAIN.value, AssetType.WEB_APPLICATION.value, AssetType.API_ENDPOINT.value}:
        value = value.removeprefix("https://").removeprefix("http://").split("/")[0]
    return f"{asset_type}:{value}"


def validate_asset_type(asset_type: str) -> str:
    if asset_type not in VALID_TYPES:
        raise ValidationError_(f"Unknown asset type '{asset_type}'", details={"allowed": sorted(VALID_TYPES)})
    return asset_type


def log_event(
    session: AsyncSession,
    asset: Asset,
    event_type: AssetEventType,
    summary: str,
    *,
    source: str = RecordSource.MANUAL.value,
    severity: str | None = None,
    detail: dict | None = None,
    occurred_at: datetime | None = None,
    scan_id: str | None = None,
    actor_id: str | None = None,
) -> AssetEvent:
    event = AssetEvent(
        company_id=asset.company_id,
        asset_id=asset.id,
        event_type=event_type.value,
        summary=summary[:400],
        detail=detail,
        severity=severity,
        source=source,
        occurred_at=occurred_at or utcnow(),
        scan_id=scan_id,
        actor_id=actor_id,
    )
    session.add(event)
    return event


async def find_asset(session: AsyncSession, company_id: str, asset_type: str, identifier: str) -> Asset | None:
    normalized = normalize_identifier(asset_type, identifier)
    return (
        await session.execute(select(Asset).where(Asset.company_id == company_id, Asset.normalized_identifier == normalized))
    ).scalar_one_or_none()


async def create_asset(
    session: AsyncSession,
    company: Company,
    *,
    name: str,
    asset_type: str,
    source: str = RecordSource.MANUAL.value,
    criticality: str = "unknown",
    exposure: str = "unknown",
    description: str | None = None,
    owner: str | None = None,
    technical_contact: str | None = None,
    environment: str | None = None,
    url: str | None = None,
    tags: list[str] | None = None,
    attributes: dict | None = None,
    actor_id: str | None = None,
    is_subdomain: bool = False,
) -> Asset:
    validate_asset_type(asset_type)
    normalized = normalize_identifier(asset_type, name)
    existing = await find_asset(session, company.id, asset_type, name)
    if existing is not None:
        raise ValidationError_(
            "An asset with this identifier already exists",
            details={"asset_id": existing.id, "name": existing.name},
        )

    now = utcnow()
    asset = Asset(
        company_id=company.id,
        name=name.strip()[:300],
        normalized_identifier=normalized,
        asset_type=asset_type,
        status=AssetStatus.NEW.value,
        criticality=criticality,
        exposure=exposure,
        description=description,
        owner=owner,
        technical_contact=technical_contact,
        environment=environment,
        url=url,
        tags=tags or [],
        attributes=attributes or {},
        source=source,
        first_seen=now,
        last_seen=now,
        observation_count=1,
    )
    session.add(asset)
    await session.flush()

    log_event(
        session,
        asset,
        AssetEventType.CREATED,
        f"Asset registered ({source.replace('_', ' ')})",
        source=source,
        detail={"asset_type": asset_type, "criticality": criticality, "exposure": exposure},
        actor_id=actor_id,
    )
    company.asset_count = (company.asset_count or 0) + 1
    return asset


async def mark_observed(
    session: AsyncSession,
    asset: Asset,
    *,
    source: str,
    scan_id: str | None = None,
    changed: bool = False,
) -> None:
    """Record that a scan saw this asset again, optionally with a change."""
    now = utcnow()
    asset.last_seen = now
    asset.observation_count = (asset.observation_count or 0) + 1
    if asset.status == AssetStatus.NEW.value:
        asset.status = AssetStatus.ACTIVE.value
    if asset.source not in OBSERVED_SOURCES and source in OBSERVED_SOURCES:
        # A live observation supersedes a fixture or manual record; provenance
        # must follow the strongest evidence so the UI stops calling it sample data.
        asset.source = source
    if changed:
        asset.status = AssetStatus.CHANGED.value
        asset.last_changed_at = now
    log_event(
        session,
        asset,
        AssetEventType.SCAN_OBSERVED,
        "Seen during an authorized scan" if not changed else "Observed configuration change",
        source=source,
        scan_id=scan_id,
    )


async def record_change(
    session: AsyncSession,
    asset: Asset,
    *,
    change_type: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
    summary: str,
    severity: str = "informational",
    source: str = RecordSource.PASSIVE_DNS.value,
    scan_id: str | None = None,
    suspicious: bool = False,
    unplanned_exposure: bool = False,
    detail: dict | None = None,
) -> ConfigurationChange:
    change = ConfigurationChange(
        company_id=asset.company_id,
        asset_id=asset.id,
        scan_id=scan_id,
        change_type=change_type,
        field=field,
        old_value=old_value,
        new_value=new_value,
        summary=summary[:500],
        severity=severity,
        source=source,
        is_suspicious=suspicious,
        is_unplanned_exposure=unplanned_exposure,
        detail=detail or {},
        occurred_at=utcnow(),
    )
    session.add(change)
    log_event(
        session,
        asset,
        AssetEventType.CONFIGURATION_CHANGED,
        summary,
        source=source,
        severity=severity,
        detail={"change_type": change_type, "field": field, "old": old_value, "new": new_value},
        scan_id=scan_id,
    )
    return change


async def recompute_asset_risk(session: AsyncSession, asset: Asset) -> float:
    """Recompute from open findings, then propagate to the company roll-up."""
    rows = (
        await session.execute(
            select(Finding).where(Finding.asset_id == asset.id, Finding.status.in_(list(OPEN_FINDING_STATUSES)))
        )
    ).scalars().all()

    scores: list[float] = []
    critical = high = 0
    for finding in rows:
        if finding.risk_score:
            scores.append(finding.risk_score)
        else:
            assessed = assess_finding(
                severity=finding.severity,
                asset_type=asset.asset_type,
                exposure=asset.exposure,
                criticality=asset.criticality,
                confidence=finding.confidence,
                cvss=finding.cvss_base_score,
            )
            finding.risk_score = assessed.score
            finding.score_factors = assessed.factors_dict()
            scores.append(assessed.score)
        if finding.severity == "critical":
            critical += 1
        elif finding.severity == "high":
            high += 1

    asset.risk_score = aggregate_asset_risk(scores)
    from app.models import classify

    asset.risk_classification = classify(asset.risk_score) if scores else None
    asset.open_findings = len(rows)
    asset.critical_findings = critical
    asset.high_findings = high
    asset.last_risk_computed_at = utcnow()
    return asset.risk_score


async def recompute_company_risk(session: AsyncSession, company_id: str) -> float:
    from app.models import classify
    from app.services.risk import aggregate_company_risk

    scores = (
        await session.execute(select(Asset.risk_score).where(Asset.company_id == company_id))
    ).scalars().all()
    company = await session.get(Company, company_id)
    if company is None:
        return 0.0
    company.risk_score = aggregate_company_risk([s for s in scores if s])
    company.asset_count = (
        await session.execute(
            select(func.count()).select_from(Asset).where(Asset.company_id == company_id, Asset.status != AssetStatus.RETIRED.value)
        )
    ).scalar_one()
    return company.risk_score

