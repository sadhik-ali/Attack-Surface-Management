"""Tenant root: companies, authorization records and scan policies.

`AuthorizationRecord` is the legal gate for the whole product. Nothing in the
discovery engine will probe a target unless an approved record covers it, which
is enforced in code (see `app.discovery.gate`) and not left to operator
discipline.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column, json_type, utcnow, UTCDateTime
from app.models.enums import (
    AuthorizationScopeType,
    AuthorizationStatus,
    CompanyStatus,
    Industry,
    VerificationMethod,
)


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str] = mapped_column(enum_column(Industry), default=Industry.OTHER, nullable=False)
    website: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(enum_column(CompanyStatus), default=CompanyStatus.ACTIVE, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(320))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    # Declared primary domains. Registration here does NOT authorize scanning;
    # it only records what the customer says they own.
    root_domains: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    tags: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    asset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Demonstrates tenant isolation: assets, findings, users and reports for one
    # company are never visible from another unless `cross_company:read`.
    is_demo_tenant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    memberships = relationship("CompanyMembership", back_populates="company", cascade="all, delete-orphan")
    authorizations = relationship("AuthorizationRecord", back_populates="company", cascade="all, delete-orphan")
    scan_policy = relationship("ScanPolicy", back_populates="company", uselist=False, cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company {self.slug} id={self.id[:8]}>"


class AuthorizationRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Documented proof that the customer is authorized to assess a target.

    `scope_type` + `value` define the permitted scan scope. A scan may only run
    against targets that fall inside an `approved` and unexpired record.
    """

    __tablename__ = "authorization_records"
    __table_args__ = (
        UniqueConstraint("company_id", "scope_type", "value", name="uq_auth_company_scope"),
        Index("ix_auth_company_status", "company_id", "status"),
    )

    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_type: Mapped[str] = mapped_column(enum_column(AuthorizationScopeType), nullable=False)
    value: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(enum_column(AuthorizationStatus), default=AuthorizationStatus.PENDING, nullable=False)
    method: Mapped[str | None] = mapped_column(enum_column(VerificationMethod))
    evidence: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    verified_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    requested_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    allow_active_probing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_ports_per_target: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)

    company = relationship("Company", back_populates="authorizations")

    @property
    def is_live(self) -> bool:
        return self.status == AuthorizationStatus.APPROVED.value and (
            self.expires_at is None or self.expires_at > utcnow()
        )

    __mapper_args__ = {"polymorphic_identity": "authorization_record"}


class ScanPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-tenant safety limits for discovery runs."""

    __tablename__ = "scan_policies"
    __table_args__ = (UniqueConstraint("company_id", name="uq_scan_policy_company"),)

    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    max_concurrency: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    requests_per_second: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    allowed_ports: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    max_targets_per_run: Mapped[int] = mapped_column(Integer, default=250, nullable=False)
    respect_robots: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    safe_mode: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="Passive checks only; never opens sockets to targets."
    )
    business_hours_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    company = relationship("Company", back_populates="scan_policy")
