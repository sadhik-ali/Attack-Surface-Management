"""Dashboard aggregation.

All figures come from stored rows. Nothing here estimates, interpolates or
invents a value: if a metric has no data the response says zero, and the
`data_provenance_note` states how many assets are sample fixtures versus live
observations so the UI can label the page honestly.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Alert,
    AlertStatus,
    Asset,
    AssetEvent,
    AssetStatus,
    AssetType,
    Certificate,
    CertificateStatus,
    Company,
    ConfigurationChange,
    ExposedService,
    Finding,
    RiskScore,
    Scan,
    Severity,
    Vulnerability,
    VulnerabilityStatus,
)
from app.models.enums import OBSERVED_SOURCES, OPEN_FINDING_STATUSES
from app.models.risk import RISK_MODEL_VERSION
from app.schemas.common import SeverityCounts
from app.schemas.dashboard import (
    AssetTypeCount,
    CertificateSnapshot,
    CompanyComparison,
    DashboardMetrics,
    DashboardOut,
    RecentEvent,
    RiskFactor,
    RiskSummary,
    ServiceSnapshot,
    TrendPoint,
)
from app.schemas.finding import FindingOut
from app.services.presenters import finding_out
from app.services.risk import aggregate_company_risk, assess_finding, classify

ASSET_TYPE_LABELS = {
    AssetType.DOMAIN.value: "Domains",
    AssetType.SUBDOMAIN.value: "Subdomains",
    AssetType.IP_ADDRESS.value: "IP addresses",
    AssetType.WEB_APPLICATION.value: "Web applications",
    AssetType.API_ENDPOINT.value: "API endpoints",
    AssetType.CLOUD_RESOURCE.value: "Cloud resources",
    AssetType.NETWORK_SERVICE.value: "Network services",
}

UNRESOLVED_VULN_STATUSES = [
    VulnerabilityStatus.UNRESOLVED.value,
    VulnerabilityStatus.TRIAGED.value,
    VulnerabilityStatus.IN_REMEDIATION.value,
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _day(value: datetime) -> str:
    return value.astimezone(timezone.utc).date().isoformat()


async def _latest_snapshot(session: AsyncSession, company_id: str) -> RiskScore | None:
    return (
        await session.execute(
            select(RiskScore)
            .where(RiskScore.company_id == company_id, RiskScore.scope == "company")
            .order_by(RiskScore.computed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _severity_breakdown(session: AsyncSession, model, company_id: str, status_filter) -> SeverityCounts:
    rows = (
        await session.execute(
            select(model.severity, func.count(model.id))
            .where(model.company_id == company_id, model.status.in_(status_filter))
            .group_by(model.severity)
        )
    ).all()
    counts = SeverityCounts()
    for severity, count in rows:
        if hasattr(counts, severity):
            setattr(counts, severity, count)
    return counts


def _risk_summary(snapshot: RiskScore | None, fallback_score: float, severity: SeverityCounts, findings_open: int) -> RiskSummary:
    if snapshot is None:
        return RiskSummary(
            score=fallback_score,
            classification=classify(fallback_score) if fallback_score else "informational",
            computed_at=None,
            model_version=RISK_MODEL_VERSION,
            factors=[],
            driver_summary="Computed on request from current open findings; no stored snapshot yet.",
            open_findings=findings_open,
            severity_counts=severity,
        )
    factors = [
        RiskFactor(
            key=key,
            label=str(value.get("label", key)),
            weight=float(value.get("weight", 0)),
            contribution=float(value.get("contribution", 0)),
        )
        for key, value in (snapshot.factors or {}).items()
        if isinstance(value, dict)
    ]
    return RiskSummary(
        score=snapshot.score,
        classification=snapshot.classification,
        previous_score=snapshot.previous_score,
        delta=snapshot.delta,
        model_version=snapshot.model_version,
        computed_at=snapshot.computed_at,
        factors=factors,
        driver_summary=snapshot.driver_summary,
        open_findings=findings_open,
        severity_counts=severity,
    )


def _trend(
    *,
    asset_rows: list,
    findings: list,
    snapshots: list[RiskScore],
    days: int = 30,
    now: datetime,
) -> list[TrendPoint]:
    start = (now - timedelta(days=days - 1)).date()

    # Asset population per day: an asset counts from its first_seen until it is retired.
    per_day_assets: Counter[str] = Counter()
    for row in asset_rows:
        first = (row.first_seen or now).date()
        last = (row.retired_at.date() if row.retired_at else now.date())
        cursor = max(first, start)
        while cursor <= min(last, now.date()):
            per_day_assets[cursor.isoformat()] += 1
            cursor += timedelta(days=1)

    findings_by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "critical": 0, "high": 0})
    for finding in findings:
        day = (finding.discovered_at or now).date()
        if day < start or day > now.date():
            continue
        key = day.isoformat()
        is_open = finding.status in OPEN_FINDING_STATUSES
        if is_open:
            findings_by_day[key]["total"] += 1
            if finding.severity == Severity.CRITICAL.value:
                findings_by_day[key]["critical"] += 1
            elif finding.severity == Severity.HIGH.value:
                findings_by_day[key]["high"] += 1

    # Findings/critical/high come from the stored daily snapshots. They are the
    # only historical counts the system actually recorded; deriving them by
    # summing today's open findings would fabricate a history that never existed.
    snapshot_by_day: dict[str, RiskScore] = {}
    for snapshot in sorted(snapshots, key=lambda item: item.computed_at):
        snapshot_by_day[_day(snapshot.computed_at)] = snapshot

    points: list[TrendPoint] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        snapshot = snapshot_by_day.get(key)
        points.append(
            TrendPoint(
                date=key,
                assets=per_day_assets.get(key, 0),
                findings=snapshot.finding_count if snapshot else 0,
                risk_score=round(snapshot.score, 1) if snapshot else 0.0,
                critical=snapshot.critical_count if snapshot else 0,
                high=snapshot.high_count if snapshot else 0,
            )
        )
    return points


async def build_dashboard(
    session: AsyncSession,
    *,
    company: Company,
    accessible_companies: list[Company],
    include_comparison: bool,
) -> DashboardOut:
    now = _utcnow()
    since_7d = now - timedelta(days=7)

    asset_rows = (
        await session.execute(
            select(
                Asset.id,
                Asset.asset_type,
                Asset.status,
                Asset.source,
                Asset.criticality,
                Asset.exposure,
                Asset.risk_score,
                Asset.first_seen,
                Asset.retired_at,
                Asset.last_changed_at,
            ).where(Asset.company_id == company.id)
        )
    ).all()

    findings = (
        await session.execute(
            select(Finding).where(Finding.company_id == company.id, Finding.status.in_(list(OPEN_FINDING_STATUSES)))
        )
    ).scalars().all()

    severity = SeverityCounts(
        critical=sum(1 for f in findings if f.severity == Severity.CRITICAL.value),
        high=sum(1 for f in findings if f.severity == Severity.HIGH.value),
        medium=sum(1 for f in findings if f.severity == Severity.MEDIUM.value),
        low=sum(1 for f in findings if f.severity == Severity.LOW.value),
        informational=sum(1 for f in findings if f.severity == Severity.INFORMATIONAL.value),
    )

    vuln_severity = await _severity_breakdown(session, Vulnerability, company.id, UNRESOLVED_VULN_STATUSES)

    type_counts = Counter(row.asset_type for row in asset_rows if row.status != AssetStatus.RETIRED.value)
    observed = sum(1 for row in asset_rows if row.source in OBSERVED_SOURCES)
    simulated = sum(1 for row in asset_rows if row.source == "seed")

    service_rows = (
        await session.execute(
            select(
                ExposedService.port,
                ExposedService.protocol_category,
                ExposedService.is_risky,
                ExposedService.is_expected,
                ExposedService.is_encrypted,
            ).where(ExposedService.company_id == company.id, ExposedService.state == "open")
        )
    ).all()
    category_counts = Counter((row.protocol_category or "other") for row in service_rows)

    cert_rows = (
        await session.execute(
            select(Certificate.status, Certificate.days_remaining, Certificate.hostname_matches).where(
                Certificate.company_id == company.id
            )
        )
    ).all()
    cert_status = Counter(row.status for row in cert_rows)
    closest = min((row.days_remaining for row in cert_rows if row.days_remaining is not None and row.days_remaining >= 0), default=None)

    snapshot = await _latest_snapshot(session, company.id)
    computed_now = aggregate_company_risk([row.risk_score for row in asset_rows if row.risk_score])

    snapshots = (
        await session.execute(
            select(RiskScore)
            .where(RiskScore.company_id == company.id, RiskScore.scope == "company", RiskScore.computed_at >= now - timedelta(days=30))
            .order_by(RiskScore.computed_at)
        )
    ).scalars().all()

    # --- recent activity ---------------------------------------------------
    event_rows = (
        await session.execute(
            select(AssetEvent, Asset.name)
            .join(Asset, Asset.id == AssetEvent.asset_id)
            .where(AssetEvent.company_id == company.id)
            .order_by(AssetEvent.occurred_at.desc())
            .limit(10)
        )
    ).all()
    change_rows = (
        await session.execute(
            select(ConfigurationChange, Asset.name)
            .outerjoin(Asset, Asset.id == ConfigurationChange.asset_id)
            .where(ConfigurationChange.company_id == company.id)
            .order_by(ConfigurationChange.occurred_at.desc())
            .limit(6)
        )
    ).all()
    alert_rows = (
        await session.execute(
            select(Alert, Asset.name)
            .outerjoin(Asset, Asset.id == Alert.asset_id)
            .where(Alert.company_id == company.id)
            .order_by(Alert.occurred_at.desc())
            .limit(6)
        )
    ).all()

    recent_events = [
        RecentEvent(
            id=event.id,
            kind=event.event_type,
            title=event.summary,
            detail=None,
            severity=event.severity,
            asset_id=event.asset_id,
            asset_name=name,
            occurred_at=event.occurred_at,
            source=event.source,
        )
        for event, name in event_rows
    ]
    recent_changes = [
        RecentEvent(
            id=change.id,
            kind=change.change_type,
            title=change.summary,
            detail=f"{change.field}: {change.old_value or '—'} → {change.new_value or '—'}",
            severity=change.severity,
            asset_id=change.asset_id,
            asset_name=name,
            occurred_at=change.occurred_at,
            source=change.source,
        )
        for change, name in change_rows
    ]
    recent_alerts = [
        RecentEvent(
            id=alert.id,
            kind=alert.alert_type,
            title=alert.title,
            detail=alert.message,
            severity=alert.severity,
            asset_id=alert.asset_id,
            asset_name=name,
            occurred_at=alert.occurred_at,
            source=alert.source,
        )
        for alert, name in alert_rows
    ]
    merged = sorted(recent_events + recent_changes, key=lambda e: e.occurred_at, reverse=True)[:12]

    top_findings = sorted(findings, key=lambda f: f.risk_score, reverse=True)[:5]
    asset_names: dict[str, str] = {}
    if top_findings:
        asset_names = dict(
            (
                await session.execute(select(Asset.id, Asset.name).where(Asset.id.in_([f.asset_id for f in top_findings])))
            ).all()
        )
    top_risk_models: list[FindingOut] = []
    for finding in top_findings:
        if not finding.risk_score:
            assessed = assess_finding(
                severity=finding.severity,
                exposure=finding.exposure or "unknown",
                criticality="unknown",
                confidence=finding.confidence,
                cvss=finding.cvss_base_score,
            )
            finding.risk_score = assessed.score
        top_risk_models.append(finding_out(finding, asset_name=asset_names.get(finding.asset_id)))

    scans_7d = (
        await session.execute(select(func.count()).select_from(Scan).where(Scan.company_id == company.id, Scan.created_at >= since_7d))
    ).scalar_one()
    last_scan_at = (
        await session.execute(select(func.max(Scan.finished_at)).where(Scan.company_id == company.id))
    ).scalar_one()
    changes_7d = (
        await session.execute(
            select(func.count()).select_from(ConfigurationChange).where(ConfigurationChange.company_id == company.id, ConfigurationChange.occurred_at >= since_7d)
        )
    ).scalar_one()
    alerts_new = (
        await session.execute(
            select(func.count()).select_from(Alert).where(Alert.company_id == company.id, Alert.status == AlertStatus.NEW.value)
        )
    ).scalar_one()
    vulns_open = (
        await session.execute(
            select(func.count()).select_from(Vulnerability).where(Vulnerability.company_id == company.id, Vulnerability.status.in_(UNRESOLVED_VULN_STATUSES))
        )
    ).scalar_one()

    metrics = DashboardMetrics(
        total_assets=sum(1 for row in asset_rows if row.status != AssetStatus.RETIRED.value),
        assets_new_7d=sum(1 for row in asset_rows if row.first_seen and row.first_seen >= since_7d),
        assets_changed_7d=sum(1 for row in asset_rows if row.last_changed_at and row.last_changed_at >= since_7d),
        assets_retired=sum(1 for row in asset_rows if row.status == AssetStatus.RETIRED.value),
        domains=type_counts.get(AssetType.DOMAIN.value, 0),
        subdomains=type_counts.get(AssetType.SUBDOMAIN.value, 0),
        ip_addresses=type_counts.get(AssetType.IP_ADDRESS.value, 0),
        api_endpoints=type_counts.get(AssetType.API_ENDPOINT.value, 0),
        cloud_resources=type_counts.get(AssetType.CLOUD_RESOURCE.value, 0),
        web_applications=type_counts.get(AssetType.WEB_APPLICATION.value, 0),
        services_total=len(service_rows),
        certificates_total=len(cert_rows),
        findings_open=len(findings),
        vulnerabilities_open=vulns_open,
        changes_7d=changes_7d,
        alerts_new=alerts_new,
        scans_7d=scans_7d,
        last_scan_at=last_scan_at,
    )

    service_snapshot = ServiceSnapshot(
        total=len(service_rows),
        risky=sum(1 for row in service_rows if row.is_risky),
        unexpected=sum(1 for row in service_rows if not row.is_expected),
        unencrypted=sum(1 for row in service_rows if not row.is_encrypted),
        management_interfaces=sum(1 for row in service_rows if row.port in {22, 3389, 5900, 5985, 5986} or row.protocol_category == "management"),
        by_category=[{"category": key, "count": count} for key, count in category_counts.most_common()],
    )

    certificate_snapshot = CertificateSnapshot(
        total=len(cert_rows),
        valid=cert_status.get(CertificateStatus.VALID.value, 0),
        expiring_soon=cert_status.get(CertificateStatus.EXPIRING_SOON.value, 0),
        expired=cert_status.get(CertificateStatus.EXPIRED.value, 0),
        hostname_mismatch=sum(1 for row in cert_rows if not row.hostname_matches),
        closest_expiry_days=closest,
    )

    comparison: list[CompanyComparison] = []
    if include_comparison:
        for sibling in accessible_companies:
            sibling_counts = await _severity_breakdown(session, Finding, sibling.id, list(OPEN_FINDING_STATUSES))
            comparison.append(
                CompanyComparison(
                    company_id=sibling.id,
                    name=sibling.name,
                    slug=sibling.slug,
                    asset_count=sibling.asset_count,
                    open_findings=sibling_counts.total,
                    risk_score=sibling.risk_score,
                    critical_findings=sibling_counts.critical,
                )
            )

    note_parts = []
    if simulated:
        note_parts.append(f"{simulated} assets are sample demonstration fixtures (source=seed)")
    if observed:
        note_parts.append(f"{observed} assets were observed by a discovery run")
    if not note_parts:
        note_parts.append("No assets registered yet")
    note = "; ".join(note_parts) + ". Simulated rows are labelled in the interface and are never presented as live scan results."

    return DashboardOut(
        company_id=company.id,
        company_name=company.name,
        generated_at=now,
        metrics=metrics,
        risk=_risk_summary(snapshot, computed_now, severity, len(findings)),
        findings_by_severity=severity,
        vulnerabilities_by_severity=vuln_severity,
        asset_mix=[
            AssetTypeCount(asset_type=key, label=ASSET_TYPE_LABELS.get(key, key), count=count)
            for key, count in sorted(type_counts.items(), key=lambda kv: kv[1], reverse=True)
        ],
        service_snapshot=service_snapshot,
        certificate_snapshot=certificate_snapshot,
        trend=_trend(asset_rows=asset_rows, findings=findings, snapshots=snapshots, now=now),
        recent_events=merged,
        recent_changes=recent_changes,
        recent_alerts=recent_alerts,
        top_risks=top_risk_models,
        companies=comparison,
        data_provenance_note=note,
    )
