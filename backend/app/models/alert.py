"""Alerts and per-user notifications."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column, json_type, UTCDateTime
from app.models.enums import AlertStatus, AlertType, RecordSource, Severity


class Alert(TenantMixin, Base):
    """A generated security notification.

    `dedupe_key` is what stops a nightly certificate sweep from producing 400
    identical alerts for one expiring cert; the same underlying condition maps
    to the same key and reopens the existing alert instead.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("company_id", "dedupe_key", name="uq_alert_dedupe"),
        Index("ix_alert_company_status_severity", "company_id", "status", "severity"),
        Index("ix_alert_company_created", "company_id", "created_at"),
    )

    alert_type: Mapped[str] = mapped_column(enum_column(AlertType), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(enum_column(Severity), nullable=False, index=True)
    status: Mapped[str] = mapped_column(enum_column(AlertStatus), default=AlertStatus.NEW, nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(400), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text)

    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    certificate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("certificates.id", ondelete="SET NULL"))
    change_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("configuration_changes.id", ondelete="SET NULL"))
    scan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scans.id", ondelete="SET NULL"))

    payload: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    channels: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.SEED, nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    acknowledged_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    dismissed_reason: Mapped[str | None] = mapped_column(String(300))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    occurrence_count: Mapped[int] = mapped_column(default=1, nullable=False)
    last_occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    notifications = relationship("Notification", back_populates="alert", cascade="all, delete-orphan")
    asset = relationship("Asset")

    @property
    def is_active(self) -> bool:
        return self.status in {AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value}


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user's copy of an alert: read state is personal, the alert is shared."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "alert_id", name="uq_notification_user_alert"),
        Index("ix_notification_user_read", "user_id", "read_at"),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(enum_column(Severity), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="in_app", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    alert = relationship("Alert", back_populates="notifications")
    user = relationship("User")
