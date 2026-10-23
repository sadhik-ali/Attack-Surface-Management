"""Dashboard, risk and configuration-change schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel, SeverityCounts
from app.schemas.finding import FindingOut


class RiskFactor(BaseModel):
    key: str
    label: str
    weight: float
    contribution: float
    description: str | None = None


class RiskSummary(BaseModel):
    score: float
    classification: str
    previous_score: float | None = None
    delta: float | None = None
    model_version: str
    computed_at: datetime | None = None
    factors: list[RiskFactor] = []
    driver_summary: str | None = None
    open_findings: int = 0
    severity_counts: SeverityCounts = SeverityCounts()


class AssetTypeCount(BaseModel):
    asset_type: str
    label: str
    count: int


class TrendPoint(BaseModel):
    date: str
    assets: int
    findings: int
    risk_score: float
    critical: int = 0
    high: int = 0


class CompanyComparison(BaseModel):
    company_id: str
    name: str
    slug: str
    asset_count: int
    open_findings: int
    risk_score: float
    critical_findings: int


class RecentEvent(BaseModel):
    id: str
    kind: str
    title: str
    detail: str | None = None
    severity: str | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    occurred_at: datetime
    source: str


class CertificateSnapshot(BaseModel):
    total: int
    valid: int
    expiring_soon: int
    expired: int
    hostname_mismatch: int
    closest_expiry_days: int | None = None


class ServiceSnapshot(BaseModel):
    total: int
    risky: int
    unexpected: int
    unencrypted: int
    management_interfaces: int
    by_category: list[dict] = []


class DashboardMetrics(BaseModel):
    total_assets: int
    assets_new_7d: int
    assets_changed_7d: int
    assets_retired: int
    domains: int
    subdomains: int
    ip_addresses: int
    api_endpoints: int
    cloud_resources: int
    web_applications: int
    services_total: int
    certificates_total: int
    findings_open: int
    vulnerabilities_open: int
    changes_7d: int
    alerts_new: int
    scans_7d: int
    last_scan_at: datetime | None = None


class DashboardOut(BaseModel):
    company_id: str
    company_name: str
    generated_at: datetime
    metrics: DashboardMetrics
    risk: RiskSummary
    findings_by_severity: SeverityCounts
    vulnerabilities_by_severity: SeverityCounts
    asset_mix: list[AssetTypeCount]
    service_snapshot: ServiceSnapshot
    certificate_snapshot: CertificateSnapshot
    trend: list[TrendPoint]
    recent_events: list[RecentEvent]
    recent_changes: list[RecentEvent]
    recent_alerts: list[RecentEvent]
    top_risks: list[FindingOut]
    companies: list[CompanyComparison] = []
    data_provenance_note: str


class ConfigurationChangeOut(ORMModel):
    id: str
    company_id: str
    asset_id: str | None = None
    asset_name: str | None = None
    scan_id: str | None = None
    change_type: str
    field: str
    old_value: str | None = None
    new_value: str | None = None
    summary: str
    severity: str
    is_suspicious: bool
    is_expected: bool
    is_unplanned_exposure: bool
    detail: dict = {}
    source: str
    occurred_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by_id: str | None = None


class ChangeAcknowledgeRequest(BaseModel):
    note: str | None = None
