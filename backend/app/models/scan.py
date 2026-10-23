"""Scan orchestration records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, enum_column, json_type, UTCDateTime
from app.models.enums import ScanStatus, ScanTrigger, ScanType


class Scan(TenantMixin, Base):
    __tablename__ = "scans"
    __table_args__ = (
        Index("ix_scan_company_status", "company_id", "status"),
        Index("ix_scan_company_started", "company_id", "started_at"),
    )

    name: Mapped[str | None] = mapped_column(String(200))
    scan_type: Mapped[str] = mapped_column(enum_column(ScanType), nullable=False)
    status: Mapped[str] = mapped_column(enum_column(ScanStatus), default=ScanStatus.QUEUED, nullable=False)
    trigger: Mapped[str] = mapped_column(enum_column(ScanTrigger), default=ScanTrigger.MANUAL, nullable=False)

    requested_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    requested_by_email: Mapped[str | None] = mapped_column(String(320))

    # The authorization that permitted this run. Nullable only so historical
    # manual/API-import rows can be represented; every engine-run scan sets it.
    authorization_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("authorization_records.id", ondelete="SET NULL"), index=True
    )
    # Frozen copy of the effective policy at request time, so a later policy
    # edit cannot change what a completed scan claims it respected.
    policy_snapshot: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)

    targets: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    options: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    job_id: Mapped[str | None] = mapped_column(String(120), index=True)

    targets_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    targets_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    targets_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assets_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    services_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    certificates_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    findings_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    result_summary: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Whether this run reached the network at all. Reporting must never present
    # a simulated run as a live scan, so the distinction is stored, not inferred.
    produced_live_data: Mapped[bool] = mapped_column(default=False, nullable=False)

    events = relationship("ScanEvent", back_populates="scan", cascade="all, delete-orphan")

    @property
    def progress_percent(self) -> int:
        if not self.targets_total:
            return 100 if self.status == ScanStatus.COMPLETED.value else 0
        return min(100, round((self.targets_completed / self.targets_total) * 100))


class ScanEvent(TenantMixin, Base):
    """Append-only progress/log stream for a scan run."""

    __tablename__ = "scan_events"
    __table_args__ = (Index("ix_scan_event_scan_time", "scan_id", "created_at"),)

    scan_id: Mapped[str] = mapped_column(String(36), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    stage: Mapped[str | None] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(json_type())
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)

    scan = relationship("Scan", back_populates="events")
