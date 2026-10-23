"""Risk scores and configuration change history."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, enum_column, json_type, UTCDateTime
from app.models.enums import ChangeType, RecordSource, RiskClassification, Severity, classify

RISK_MODEL_VERSION = "2026.10"


class RiskScore(TenantMixin, Base):
    """Computed risk snapshot.

    Rows are appended per computation rather than updated in place, which is
    what makes the dashboard's risk *trend* chart real data instead of a
    re-labelled current value.
    """

    __tablename__ = "risk_scores"
    __table_args__ = (
        Index("ix_risk_company_computed", "company_id", "computed_at"),
        Index("ix_risk_scope", "scope", "object_id"),
    )

    #: "asset" | "company" | "platform"
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    #: Asset id for scope=asset, company id for scope=company.
    object_id: Mapped[str | None] = mapped_column(String(36), index=True)
    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), index=True)

    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    classification: Mapped[str] = mapped_column(
        enum_column(RiskClassification), default=RiskClassification.INFORMATIONAL, nullable=False, index=True
    )
    #: Individual weighted contributions: severity / exploitability / exposure /
    #: criticality / vulnerability. Kept so the UI can explain the number.
    factors: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    driver_summary: Mapped[str | None] = mapped_column(Text)
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), default=RISK_MODEL_VERSION, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    previous_score: Mapped[float | None] = mapped_column(Float)
    delta: Mapped[float | None] = mapped_column(Float)


class ConfigurationChange(TenantMixin, Base):
    """A detected mutation of an asset's observable configuration."""

    __tablename__ = "configuration_changes"
    __table_args__ = (
        Index("ix_change_company_time", "company_id", "occurred_at"),
        Index("ix_change_asset_time", "asset_id", "occurred_at"),
    )

    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scans.id", ondelete="SET NULL"), index=True)
    domain_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("domains.id", ondelete="SET NULL"))

    change_type: Mapped[str] = mapped_column(enum_column(ChangeType), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(120), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)

    severity: Mapped[str] = mapped_column(enum_column(Severity), default=Severity.INFORMATIONAL, nullable=False, index=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_expected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Unplanned DNS/IP movement is the classic pre-compromise signal, so it is
    #: surfaced as its own flag rather than buried in `detail`.
    is_unplanned_exposure: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    detail: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.PASSIVE_DNS, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    acknowledged_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))

    asset = relationship("Asset", back_populates="changes")
