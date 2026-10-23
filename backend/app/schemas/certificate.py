"""Certificate monitoring schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class CertificateOut(ORMModel):
    id: str
    company_id: str
    asset_id: str | None = None
    scan_id: str | None = None
    host: str
    port: int
    server_name_indication: str | None = None
    serial_number: str | None = None
    fingerprint_sha256: str | None = None
    subject_common_name: str | None = None
    subject_organization: str | None = None
    issuer_common_name: str | None = None
    issuer_organization: str | None = None
    issuer_country: str | None = None
    subject_alternative_names: list[str] = []
    san_wildcard: bool
    not_before: datetime | None = None
    not_after: datetime | None = None
    days_remaining: int | None = None
    status: str
    is_expired: bool
    is_self_signed: bool
    hostname_matches: bool
    is_wildcard: bool
    key_algorithm: str | None = None
    key_size: int | None = None
    signature_algorithm: str | None = None
    tls_version: str | None = None
    certificate_chain_length: int | None = None
    ocsp_url: str | None = None
    weak_key: bool
    deprecated_signature: bool
    error: str | None = None
    source: str
    observed_at: datetime | None = None
    asset_name: str | None = None
    expires_label: str | None = None


class CertificateHealth(BaseModel):
    total: int
    valid: int
    expiring_soon: int
    expired: int
    hostname_mismatch: int
    self_signed: int
    weak_crypto: int
    not_observed: int
    closest_expiry_days: int | None = None
    #: Buckets for the expiry timeline: 7d / 30d / 90d / beyond.
    expiry_buckets: list[dict] = []
    issuers: list[dict] = []
