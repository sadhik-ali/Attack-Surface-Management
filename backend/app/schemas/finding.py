"""Vulnerability, finding and remediation schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, ProvenanceInfo


class VulnerabilityOut(ORMModel):
    id: str
    company_id: str
    asset_id: str
    asset_name: str | None = None
    cve_id: str
    title: str
    description: str | None = None
    severity: str
    cvss_base_score: float | None = None
    cvss_vector: str | None = None
    exploitability: str | None = None
    in_ransomware_catalog: bool
    affected_product: str | None = None
    affected_version: str | None = None
    fixed_version: str | None = None
    references: list = []
    confidence: str
    status: str
    remediation_note: str | None = None
    recommendation: str | None = None
    assignee_id: str | None = None
    assignee_name: str | None = None
    discovered_at: datetime | None = None
    resolved_at: datetime | None = None
    due_date: datetime | None = None
    source: str
    provenance: ProvenanceInfo | None = None


class VulnerabilityUpdateRequest(BaseModel):
    status: str | None = None
    severity: str | None = None
    confidence: str | None = None
    assignee_id: str | None = None
    remediation_note: str | None = Field(default=None, max_length=4000)
    due_date: datetime | None = None


class FindingOut(ORMModel):
    id: str
    company_id: str
    asset_id: str
    asset_name: str | None = None
    finding_type: str
    title: str
    description: str | None = None
    evidence: str | None = None
    severity: str
    confidence: str
    status: str
    risk_score: float
    score_factors: dict = {}
    cvss_base_score: float | None = None
    exposure: str | None = None
    business_impact: str | None = None
    recommendation: str | None = None
    remediation_notes: str | None = None
    assignee_id: str | None = None
    assignee_name: str | None = None
    evidence_count: int = 1
    source: str
    provenance: ProvenanceInfo | None = None
    discovered_at: datetime
    last_verified_at: datetime | None = None
    remediated_at: datetime | None = None
    due_date: datetime | None = None
    sla_breached: bool
    task_count: int = 0


class FindingUpdateRequest(BaseModel):
    status: str | None = None
    assignee_id: str | None = None
    severity: str | None = None
    recommendation: str | None = Field(default=None, max_length=4000)
    remediation_notes: str | None = Field(default=None, max_length=4000)
    due_date: datetime | None = None


class FindingNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=4000)


class RemediationTaskOut(ORMModel):
    id: str
    finding_id: str
    asset_id: str | None = None
    title: str
    description: str | None = None
    priority: str
    status: str
    assignee_id: str | None = None
    assignee_name: str | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None
    progress_percent: int
    created_at: datetime


class RemediationTaskCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    priority: str = "medium"
    assignee_id: str | None = None
    due_date: datetime | None = None


class RemediationTaskUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assignee_id: str | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    verification_note: str | None = Field(default=None, max_length=4000)


class SeverityBreakdown(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    informational: int = 0
    total: int = 0
