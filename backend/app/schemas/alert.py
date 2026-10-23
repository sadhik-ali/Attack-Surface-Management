"""Alert and notification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AlertOut(ORMModel):
    id: str
    company_id: str
    alert_type: str
    severity: str
    status: str
    title: str
    message: str
    recommendation: str | None = None
    asset_id: str | None = None
    asset_name: str | None = None
    finding_id: str | None = None
    certificate_id: str | None = None
    change_id: str | None = None
    scan_id: str | None = None
    payload: dict = {}
    channels: list[str] = []
    source: str
    occurred_at: datetime
    last_occurred_at: datetime | None = None
    occurrence_count: int
    acknowledged_at: datetime | None = None
    acknowledged_by_id: str | None = None
    acknowledged_by_name: str | None = None
    dismissed_reason: str | None = None
    resolved_at: datetime | None = None


class AlertAcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class AlertDismissRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class NotificationOut(ORMModel):
    id: str
    alert_id: str
    company_id: str | None = None
    title: str
    message: str | None = None
    severity: str
    channel: str
    read_at: datetime | None = None
    created_at: datetime


class AlertPreferenceOut(ORMModel):
    min_severity: str
    channels: list[str]
    muted_types: list[str]
    daily_digest: bool


class AlertPreferenceUpdateRequest(BaseModel):
    min_severity: str | None = None
    channels: list[str] | None = None
    muted_types: list[str] | None = None
    daily_digest: bool | None = None


class AlertCounts(BaseModel):
    new: int = 0
    acknowledged: int = 0
    critical: int = 0
    high: int = 0
    unread_notifications: int = 0
