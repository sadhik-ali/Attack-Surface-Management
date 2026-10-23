"""Integration configuration and generated reports.

Secret material is never stored on these rows: `secret_keys` lists the *names*
of configured environment/secret-store entries so the UI can show "AWS_ACCESS_KEY_ID
is configured" without ever holding, returning or logging the value.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column, json_type, UTCDateTime
from app.models.enums import IntegrationKind, IntegrationStatus, RecordSource, ReportFormat, ReportStatus


class Integration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "integrations"
    __table_args__ = (Index("ix_integration_company_kind", "company_id", "kind", unique=True),)

    #: Null means a platform-wide integration available to every tenant.
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(enum_column(IntegrationKind), nullable=False)
    status: Mapped[str] = mapped_column(enum_column(IntegrationStatus), default=IntegrationStatus.UNCONFIGURED, nullable=False)
    #: Built into the app (DNS, crt.sh, TLS probe) or external/not yet wired.
    built_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: False until an operator supplies working credentials.
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Only real, implemented capabilities are advertised to the UI this way.
    capability: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    secret_keys: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))

    @property
    def has_secrets(self) -> bool:
        return bool(self.secret_keys)


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_report_company_created", "company_id", "created_at"),)

    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    #: dashboard | asset_inventory | findings | vulnerabilities | certificates | risk
    template: Mapped[str] = mapped_column(String(60), nullable=False)
    format: Mapped[str] = mapped_column(enum_column(ReportFormat), nullable=False)
    status: Mapped[str] = mapped_column(enum_column(ReportStatus), default=ReportStatus.REQUESTED, nullable=False)
    scope: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    artifact_filename: Mapped[str | None] = mapped_column(String(300))
    generated_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    generated_by_email: Mapped[str | None] = mapped_column(String(320))
    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_message: Mapped[str | None] = mapped_column(Text)
    #: CSV/PDF is generated synchronously from real rows; that provenance is
    #: recorded so a downloaded file can always be traced to its filter set.
    source: Mapped[str] = mapped_column(String(40), default=RecordSource.MANUAL, nullable=False)
