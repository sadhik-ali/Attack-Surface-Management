"""Scan request, history and progress schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


class ScanCreateRequest(BaseModel):
    scan_type: str
    targets: list[str] = Field(default_factory=list, max_length=250)
    authorization_record_id: str | None = None
    name: str | None = Field(default=None, max_length=200)
    include_subdomains: bool = True
    ports: list[int] = Field(default_factory=list, max_length=100)
    # The caller must confirm scope on every run; the value is stored in the
    # audit trail so consent is attributable, not implied.
    confirm_authorized: bool = False

    @field_validator("targets")
    @classmethod
    def _clean_targets(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip().lower()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned


class ScanEventOut(ORMModel):
    id: str
    level: str
    stage: str | None = None
    message: str
    detail: dict | None = None
    occurred_at: datetime


class ScanOut(ORMModel):
    id: str
    company_id: str
    name: str | None = None
    scan_type: str
    status: str
    trigger: str
    requested_by_id: str | None = None
    requested_by_email: str | None = None
    authorization_record_id: str | None = None
    targets: list[str] = []
    targets_total: int
    targets_completed: int
    targets_failed: int
    assets_discovered: int
    assets_new: int
    assets_changed: int
    assets_removed: int
    services_found: int
    certificates_found: int
    findings_created: int
    changes_detected: int
    progress_percent: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    error_message: str | None = None
    result_summary: dict = {}
    policy_snapshot: dict = {}
    produced_live_data: bool
    created_at: datetime


class ScanDetailOut(ScanOut):
    events: list[ScanEventOut] = []


class ScanCapabilityOut(BaseModel):
    scan_type: str
    label: str
    description: str
    implemented: bool
    required_authorization: bool
    intrusive: bool
    availability_note: str | None = None


class ScanScheduleOut(ORMModel):
    id: str
    scan_type: str
    cron: str
    enabled: bool
    next_run_at: datetime | None = None
