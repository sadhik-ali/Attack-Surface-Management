"""Company, authorization and scan-policy schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel, SeverityCounts


class CompanySummary(ORMModel):
    id: str
    name: str
    slug: str
    industry: str
    status: str
    website: str | None = None
    asset_count: int
    risk_score: float
    is_demo_tenant: bool


class CompanyOut(CompanySummary):
    description: str | None = None
    contact_email: str | None = None
    contact_name: str | None = None
    root_domains: list[str] = []
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    open_findings: int = 0
    severity_counts: SeverityCounts = SeverityCounts()
    authorized_scope_count: int = 0
    last_scan_at: datetime | None = None


class CompanyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str | None = Field(default=None, max_length=2000)
    industry: str = "other"
    website: str | None = Field(default=None, max_length=300)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_name: str | None = Field(default=None, max_length=200)
    root_domains: list[str] = []
    tags: list[str] = []


class CompanyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    industry: str | None = None
    website: str | None = Field(default=None, max_length=300)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_name: str | None = Field(default=None, max_length=200)
    status: str | None = None
    root_domains: list[str] | None = None
    tags: list[str] | None = None


class AuthorizationOut(ORMModel):
    id: str
    company_id: str
    scope_type: str
    value: str
    status: str
    method: str | None = None
    evidence: str | None = None
    notes: str | None = None
    verified_at: datetime | None = None
    verified_by_id: str | None = None
    expires_at: datetime | None = None
    allow_active_probing: bool
    max_ports_per_target: int
    created_at: datetime
    is_live: bool = False


class AuthorizationCreateRequest(BaseModel):
    scope_type: str
    value: str = Field(min_length=1, max_length=300)
    method: str | None = None
    evidence: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None
    allow_active_probing: bool = False
    max_ports_per_target: int = Field(default=100, ge=1, le=1000)

    @field_validator("value")
    @classmethod
    def _normalise(cls, value: str) -> str:
        return value.strip().lower().rstrip(".")


class AuthorizationDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    notes: str | None = Field(default=None, max_length=2000)


class ScanPolicyOut(ORMModel):
    id: str
    company_id: str
    max_concurrency: int
    requests_per_second: float
    timeout_seconds: int
    allowed_ports: list[int]
    max_targets_per_run: int
    respect_robots: bool
    safe_mode: bool
    business_hours_only: bool


class ScanPolicyUpdateRequest(BaseModel):
    max_concurrency: int | None = Field(default=None, ge=1, le=32)
    requests_per_second: float | None = Field(default=None, gt=0, le=50)
    timeout_seconds: int | None = Field(default=None, ge=30, le=3600)
    allowed_ports: list[int] | None = None
    max_targets_per_run: int | None = Field(default=None, ge=1, le=1000)
    respect_robots: bool | None = None
    safe_mode: bool | None = None
    business_hours_only: bool | None = None
