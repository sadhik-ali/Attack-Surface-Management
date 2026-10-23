"""Platform administration schemas: integrations and enum metadata."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import EnumOption, ORMModel


class IntegrationOut(ORMModel):
    id: str | None = None
    name: str
    kind: str
    status: str
    built_in: bool
    verified: bool
    enabled: bool
    capability: str | None = None
    description: str | None = None
    secret_keys: list[str] = []
    last_run_at: datetime | None = None
    last_error: str | None = None
    implemented: bool = True


class IntegrationUpdateRequest(BaseModel):
    enabled: bool | None = None
    config: dict | None = None
    secret_keys: list[str] | None = Field(default=None, max_length=20)


class EnumMetaOut(BaseModel):
    asset_types: list[EnumOption]
    asset_statuses: list[EnumOption]
    criticalities: list[EnumOption]
    exposures: list[EnumOption]
    severities: list[EnumOption]
    finding_types: list[EnumOption]
    finding_statuses: list[EnumOption]
    vulnerability_statuses: list[EnumOption]
    certificate_statuses: list[EnumOption]
    change_types: list[EnumOption]
    scan_types: list[EnumOption]
    scan_statuses: list[EnumOption]
    alert_types: list[EnumOption]
    alert_statuses: list[EnumOption]
    sources: list[EnumOption]
    remediation_statuses: list[EnumOption]


class RetentionOut(BaseModel):
    scan_result_retention_days: int
    audit_log_retention_days: int


class PlatformSettingsOut(BaseModel):
    app_name: str
    app_env: str
    api_prefix: str
    discovery_enabled: bool
    discovery_offline: bool
    job_backend: str
    demo_mode: bool
    certificate_expiry_warning_days: int
    certificate_expiry_critical_days: int
    rate_limit_enabled: bool
    rate_limit_requests_per_minute: int
    retention: RetentionOut
    supported_integrations: list[str]
