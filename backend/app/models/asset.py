"""Asset inventory.

`Asset` is the canonical registry row every other inventory object hangs off:
it carries the tenant, owner, criticality, exposure and lifecycle status that
the dashboard aggregates. The typed tables (`Domain`, `IPAddress`, ...) hold
only the attributes specific to that asset class.

Every typed row is also a tenant-owned row in its own right. Duplicating
`company_id` onto children is intentional — it lets a query filter a child table
directly without a join back through `assets`, and a child that could belong to
a different company than its parent would be a tenant-isolation hole.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column, json_type, UTCDateTime
from app.models.enums import (
    AssetEventType,
    AssetStatus,
    AssetType,
    CloudProvider,
    CriticalityTier,
    ExposureClass,
    IPVersion,
    RecordSource,
    ServiceState,


)


class Asset(TenantMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("company_id", "asset_type", "normalized_identifier", name="uq_asset_identity"),
        Index("ix_asset_company_status", "company_id", "status"),
        Index("ix_asset_company_type", "company_id", "asset_type"),
        Index("ix_asset_company_risk", "company_id", "risk_score"),
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Canonical, case-folded identity used to deduplicate discoveries.
    normalized_identifier: Mapped[str] = mapped_column(String(300), nullable=False)
    asset_type: Mapped[str] = mapped_column(enum_column(AssetType), nullable=False)
    status: Mapped[str] = mapped_column(enum_column(AssetStatus), default=AssetStatus.NEW, nullable=False)
    criticality: Mapped[str] = mapped_column(enum_column(CriticalityTier), default=CriticalityTier.UNKNOWN, nullable=False)
    exposure: Mapped[str] = mapped_column(enum_column(ExposureClass), default=ExposureClass.UNKNOWN, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(200), comment="Business owner or team")
    technical_contact: Mapped[str | None] = mapped_column(String(320))
    environment: Mapped[str | None] = mapped_column(String(40), comment="production / staging / development")
    url: Mapped[str | None] = mapped_column(String(600))
    tags: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    attributes: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)

    # --- provenance --------------------------------------------------------
    # `source` is what the UI renders as a "sample data" vs "observed" badge.
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.MANUAL, nullable=False)
    first_seen: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    retired_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    observation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- risk roll-up (denormalised for list views) ------------------------
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_classification: Mapped[str | None] = mapped_column(String(20))
    open_findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_risk_computed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # --- relationships -----------------------------------------------------
    domain = relationship("Domain", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    ip = relationship("IPAddress", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    api = relationship("ApiEndpoint", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    cloud = relationship("CloudResource", back_populates="asset", uselist=False, cascade="all, delete-orphan")
    services = relationship("ExposedService", back_populates="asset", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="asset", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="asset", cascade="all, delete-orphan")
    vulnerabilities = relationship("Vulnerability", back_populates="asset", cascade="all, delete-orphan")
    events = relationship("AssetEvent", back_populates="asset", cascade="all, delete-orphan")
    changes = relationship("ConfigurationChange", back_populates="asset", cascade="all, delete-orphan")

    company = relationship("Company", back_populates="assets")

    @property
    def is_observed(self) -> bool:
        from app.models.enums import OBSERVED_SOURCES

        return self.source in OBSERVED_SOURCES


class Domain(TenantMixin, Base):
    __tablename__ = "domains"
    __table_args__ = (
        UniqueConstraint("company_id", "fqdn", name="uq_domain_fqdn"),
        Index("ix_domain_company_root", "company_id", "root_domain"),
    )

    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    fqdn: Mapped[str] = mapped_column(String(300), nullable=False)
    root_domain: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    host_label: Mapped[str | None] = mapped_column(String(120))
    is_subdomain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_wildcard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_domain_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("domains.id", ondelete="SET NULL"))
    registrar: Mapped[str | None] = mapped_column(String(200))
    registrant_organization: Mapped[str | None] = mapped_column(String(300))
    nameservers: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    # Last resolved answer set: [{"type":"A","value":"1.2.3.4","ttl":300}, ...]
    dns_records: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    dns_resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    resolves_to: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    web_server: Mapped[str | None] = mapped_column(String(200))
    http_status: Mapped[int | None] = mapped_column(Integer)
    http_title: Mapped[str | None] = mapped_column(String(400))
    technologies: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    certificate_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("certificates.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.MANUAL, nullable=False)

    asset = relationship("Asset", back_populates="domain")


class IPAddress(TenantMixin, Base):
    __tablename__ = "ip_addresses"
    __table_args__ = (UniqueConstraint("company_id", "address", name="uq_ip_company_address"),)

    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    version: Mapped[str] = mapped_column(enum_column(IPVersion), default=IPVersion.V4, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reverse_dns: Mapped[str | None] = mapped_column(String(300))
    geo_country: Mapped[str | None] = mapped_column(String(2))
    geo_country_name: Mapped[str | None] = mapped_column(String(120))
    geo_city: Mapped[str | None] = mapped_column(String(120))
    asn: Mapped[str | None] = mapped_column(String(20))
    asn_organization: Mapped[str | None] = mapped_column(String(300))
    provider_hint: Mapped[str | None] = mapped_column(String(120), comment="Hosting provider inferred from ASN/PTR")
    is_cloud_elastic_ip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.MANUAL, nullable=False)

    asset = relationship("Asset", back_populates="ip")
    services = relationship("ExposedService", back_populates="ip", cascade="all, delete-orphan")


class ApiEndpoint(TenantMixin, Base):
    __tablename__ = "api_endpoints"
    __table_args__ = (UniqueConstraint("company_id", "method", "url_hash", name="uq_api_identity"),)

    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    url: Mapped[str] = mapped_column(String(700), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    path: Mapped[str | None] = mapped_column(String(500))
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    api_format: Mapped[str | None] = mapped_column(String(40), comment="rest / graphql / grpc / soap / webhook")
    summary: Mapped[str | None] = mapped_column(Text)
    auth_type: Mapped[str | None] = mapped_column(String(40), comment="none / apikey / bearer / cookie / basic")
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unauthenticated_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_documented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[str | None] = mapped_column(String(60))
    owner: Mapped[str | None] = mapped_column(String(200))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer)
    response_media_type: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.MANUAL, nullable=False)

    asset = relationship("Asset", back_populates="api")


class CloudResource(TenantMixin, Base):
    __tablename__ = "cloud_resources"
    __table_args__ = (
        UniqueConstraint("company_id", "provider", "external_id", name="uq_cloud_external_id"),
        Index("ix_cloud_company_provider", "company_id", "provider"),
    )

    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(enum_column(CloudProvider), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(120))
    account_alias: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(80))
    zone: Mapped[str | None] = mapped_column(String(80))
    resource_type: Mapped[str | None] = mapped_column(String(120), comment="s3-bucket / ec2-instance / vm / bucket")
    external_id: Mapped[str] = mapped_column(String(300), nullable=False)
    public_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    public_acl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    logging_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    imdsv2_required: Mapped[bool | None] = mapped_column(Boolean)
    security_groups: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    resource_attributes: Mapped[dict] = mapped_column(json_type(), default=dict, nullable=False)
    # Cloud inventory is not implemented against real APIs; rows produced by the
    # generator are marked `seed` so the UI can label them as simulated.
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.SEED, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    asset = relationship("Asset", back_populates="cloud")


class ExposedService(TenantMixin, Base):
    """A listening port observed on an asset, with its banner and version."""

    __tablename__ = "exposed_services"
    __table_args__ = (
        UniqueConstraint("company_id", "asset_id", "port", "transport", name="uq_service_endpoint"),
        Index("ix_service_company_risk", "company_id", "risk_level"),
    )

    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ip_addresses.id", ondelete="CASCADE"), index=True)
    host: Mapped[str | None] = mapped_column(String(300))
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    transport: Mapped[str] = mapped_column(String(10), default="tcp", nullable=False)
    service_name: Mapped[str | None] = mapped_column(String(120))
    product: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[str | None] = mapped_column(String(200))
    operating_system: Mapped[str | None] = mapped_column(String(200))
    banner: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(enum_column(ServiceState), default=ServiceState.OPEN, nullable=False)
    protocol_category: Mapped[str | None] = mapped_column(String(60), comment="http / ssh / database / management")
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_expected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_risky: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(20), index=True)
    recommendation: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime())
    gone_since: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.MANUAL, nullable=False)

    asset = relationship("Asset", back_populates="services")
    ip = relationship("IPAddress", back_populates="services")


class AssetEvent(TenantMixin, Base):
    """Timeline feeding the asset detail page."""

    __tablename__ = "asset_events"
    __table_args__ = (Index("ix_asset_event_asset_time", "asset_id", "occurred_at"),)

    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    scan_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scans.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(enum_column(AssetEventType), nullable=False)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    detail: Mapped[dict | None] = mapped_column(json_type())
    severity: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(enum_column(RecordSource), default=RecordSource.MANUAL, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))

    asset = relationship("Asset", back_populates="events")
