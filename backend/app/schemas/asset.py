"""Asset inventory schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, ProvenanceInfo


class DomainDetailOut(ORMModel):
    fqdn: str
    root_domain: str
    host_label: str | None = None
    is_subdomain: bool
    is_wildcard: bool
    registrar: str | None = None
    nameservers: list[str] = []
    dns_records: list[dict] = []
    resolves_to: list[str] = []
    web_server: str | None = None
    http_status: int | None = None
    http_title: str | None = None
    technologies: list[str] = []
    dns_resolved_at: datetime | None = None


class IPDetailOut(ORMModel):
    address: str
    version: str
    is_private: bool
    reverse_dns: str | None = None
    geo_country: str | None = None
    geo_country_name: str | None = None
    geo_city: str | None = None
    asn: str | None = None
    asn_organization: str | None = None
    provider_hint: str | None = None
    is_cloud_elastic_ip: bool


class ApiDetailOut(ORMModel):
    url: str
    method: str
    path: str | None = None
    api_format: str | None = None
    summary: str | None = None
    auth_type: str | None = None
    requires_auth: bool
    unauthenticated_access: bool
    is_deprecated: bool
    is_documented: bool
    version: str | None = None
    last_status_code: int | None = None
    last_latency_ms: int | None = None
    response_media_type: str | None = None


class CloudDetailOut(ORMModel):
    provider: str
    account_id: str | None = None
    account_alias: str | None = None
    region: str | None = None
    resource_type: str | None = None
    external_id: str
    public_access: bool
    public_acl: bool
    encrypted: bool
    logging_enabled: bool
    security_groups: list = []
    observed_at: datetime | None = None


class ServiceOut(ORMModel):
    id: str
    asset_id: str
    host: str | None = None
    port: int
    transport: str
    service_name: str | None = None
    product: str | None = None
    version: str | None = None
    operating_system: str | None = None
    state: str
    protocol_category: str | None = None
    is_encrypted: bool
    is_expected: bool
    is_risky: bool
    risk_level: str | None = None
    recommendation: str | None = None
    banner: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    source: str


class CertificateSummaryOut(ORMModel):
    id: str
    host: str
    port: int
    subject_common_name: str | None = None
    issuer_common_name: str | None = None
    issuer_organization: str | None = None
    not_after: datetime | None = None
    days_remaining: int | None = None
    status: str
    is_expired: bool
    hostname_matches: bool
    observed_at: datetime | None = None
    source: str


class AssetOut(ORMModel):
    id: str
    company_id: str
    name: str
    asset_type: str
    status: str
    criticality: str
    exposure: str
    description: str | None = None
    owner: str | None = None
    technical_contact: str | None = None
    environment: str | None = None
    url: str | None = None
    tags: list[str] = []
    source: str
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    last_changed_at: datetime | None = None
    risk_score: float
    risk_classification: str | None = None
    open_findings: int
    critical_findings: int
    high_findings: int
    created_at: datetime
    updated_at: datetime
    provenance: ProvenanceInfo | None = None
    domain: DomainDetailOut | None = None
    ip: IPDetailOut | None = None
    api: ApiDetailOut | None = None
    cloud: CloudDetailOut | None = None
    service_count: int = 0


class AssetEventOut(ORMModel):
    id: str
    asset_id: str
    event_type: str
    summary: str
    detail: dict | None = None
    severity: str | None = None
    source: str
    occurred_at: datetime


class AssetDetailOut(AssetOut):
    services: list[ServiceOut] = []
    certificates: list[CertificateSummaryOut] = []
    findings_by_severity: dict[str, int] = {}
    events: list[AssetEventOut] = []
    change_count: int = 0


class AssetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    asset_type: str
    criticality: str = "unknown"
    exposure: str = "unknown"
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=200)
    technical_contact: str | None = Field(default=None, max_length=320)
    environment: str | None = Field(default=None, max_length=40)
    url: str | None = Field(default=None, max_length=600)
    tags: list[str] = []
    criticality_note: str | None = Field(default=None, max_length=500)
    # Type-specific inputs
    address: str | None = Field(default=None, max_length=45)
    path: str | None = Field(default=None, max_length=500)
    method: str | None = Field(default=None, max_length=10)
    provider: str | None = Field(default=None, max_length=40)
    external_id: str | None = Field(default=None, max_length=300)
    resource_type: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def _trim(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Asset name is required")
        return value


class AssetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    criticality: str | None = None
    exposure: str | None = None
    status: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=200)
    technical_contact: str | None = Field(default=None, max_length=320)
    environment: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = None


class CsvImportError(BaseModel):
    row: int
    message: str


class CsvImportResult(BaseModel):
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: list[CsvImportError] = []
    dry_run: bool


class DomainOut(ORMModel):
    id: str
    asset_id: str
    fqdn: str
    root_domain: str
    host_label: str | None = None
    is_subdomain: bool
    is_wildcard: bool
    resolves_to: list[str] = []
    http_status: int | None = None
    technologies: list[str] = []
    source: str
    asset_name: str | None = None
    risk_score: float = 0.0
    criticality: str = "unknown"
    last_seen: datetime | None = None


class IPOut(ORMModel):
    id: str
    asset_id: str
    address: str
    version: str
    is_private: bool
    asn: str | None = None
    asn_organization: str | None = None
    geo_country_name: str | None = None
    provider_hint: str | None = None
    reverse_dns: str | None = None
    asset_name: str | None = None
    service_count: int = 0
    risk_score: float = 0.0
    last_seen: datetime | None = None


class ApiEndpointOut(ORMModel):
    id: str
    asset_id: str
    url: str
    method: str
    api_format: str | None = None
    auth_type: str | None = None
    requires_auth: bool
    unauthenticated_access: bool
    is_deprecated: bool
    last_status_code: int | None = None
    asset_name: str | None = None
    risk_score: float = 0.0


class CloudResourceOut(ORMModel):
    id: str
    asset_id: str
    provider: str
    account_alias: str | None = None
    region: str | None = None
    resource_type: str | None = None
    external_id: str
    public_access: bool
    encrypted: bool
    source: str
    asset_name: str | None = None
    risk_score: float = 0.0
