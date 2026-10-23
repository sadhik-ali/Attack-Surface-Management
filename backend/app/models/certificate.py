"""SSL/TLS certificate inventory."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column, json_type, UTCDateTime
from app.models.enums import CertificateStatus, RecordSource


class Certificate(TenantMixin, Base):
    """One certificate as observed on a host:port.

    A certificate is stored per observation rather than per fingerprint: the
    same leaf certificate deployed on five hosts is five monitored positions,
    each with its own hostname-mismatch and expiry story.
    """

    __tablename__ = "certificates"
    __table_args__ = (
        Index("ix_cert_company_status", "company_id", "status"),
        Index("ix_cert_company_not_after", "company_id", "not_after"),
    )

    asset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scans.id", ondelete="SET NULL"))

    host: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    port: Mapped[int] = mapped_column(Integer, default=443, nullable=False)
    server_name_indication: Mapped[str | None] = mapped_column(String(300))

    serial_number: Mapped[str | None] = mapped_column(String(120))
    fingerprint_sha256: Mapped[str | None] = mapped_column(String(120), index=True)
    subject_common_name: Mapped[str | None] = mapped_column(String(300))
    subject_organization: Mapped[str | None] = mapped_column(String(300))
    issuer_common_name: Mapped[str | None] = mapped_column(String(300))
    issuer_organization: Mapped[str | None] = mapped_column(String(300))
    issuer_country: Mapped[str | None] = mapped_column(String(2))

    subject_alternative_names: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    san_wildcard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    not_before: Mapped[datetime | None] = mapped_column(UTCDateTime())
    not_after: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    days_remaining: Mapped[int | None] = mapped_column(Integer, index=True)

    status: Mapped[str] = mapped_column(enum_column(CertificateStatus), default=CertificateStatus.NOT_OBSERVED, nullable=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_self_signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hostname_matches: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_wildcard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    key_algorithm: Mapped[str | None] = mapped_column(String(40))
    key_size: Mapped[int | None] = mapped_column(Integer)
    signature_algorithm: Mapped[str | None] = mapped_column(String(80))
    tls_version: Mapped[str | None] = mapped_column(String(20))
    protocol_version: Mapped[str | None] = mapped_column(String(40))
    certificate_chain_length: Mapped[int | None] = mapped_column(Integer)
    ocsp_url: Mapped[str | None] = mapped_column(String(600))
    issuer_url: Mapped[str | None] = mapped_column(String(600))

    weak_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deprecated_signature: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    error: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.MANUAL, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)

    @property
    def expires_label(self) -> str:
        if self.not_after is None:
            return "unknown"
        if self.days_remaining is None:
            return self.not_after.strftime("%Y-%m-%d")
        if self.days_remaining < 0:
            return f"expired {abs(self.days_remaining)} days ago"
        return f"{self.days_remaining} days"

    asset = relationship("Asset", back_populates="certificates")
