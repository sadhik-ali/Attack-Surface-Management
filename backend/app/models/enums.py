"""Enumerations shared by the ORM, the API and the UI.

All of them inherit from `str` so they serialise as plain strings, survive as
SQLite TEXT columns, and can be compared against raw values coming from
discovery tools without an import cycle.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class RoleCode(StrEnum):
    SUPER_ADMIN = "super_admin"
    COMPANY_ADMIN = "company_admin"
    SECURITY_ANALYST = "security_analyst"
    READ_ONLY_AUDITOR = "read_only_auditor"


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class Industry(StrEnum):
    TECHNOLOGY = "technology"
    FINANCIAL_SERVICES = "financial_services"
    HEALTHCARE = "healthcare"
    RETAIL = "retail"
    MANUFACTURING = "manufacturing"
    PUBLIC_SECTOR = "public_sector"
    ENERGY = "energy"
    EDUCATION = "education"
    LOGISTICS = "logistics"
    OTHER = "other"


class AuthorizationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AuthorizationScopeType(StrEnum):
    DOMAIN = "domain"
    WILDCARD_DOMAIN = "wildcard_domain"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    CIDR = "cidr"
    URL = "url"


class VerificationMethod(StrEnum):
    DNS_TXT = "dns_txt"
    HTTP_FILE = "http_file"
    WHOIS_CONTACT = "whois_contact"
    CLOUD_ACCOUNT = "cloud_account"
    SIGNED_STATEMENT = "signed_statement"
    MANUAL_REVIEW = "manual_review"


class AssetType(StrEnum):
    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    IP_ADDRESS = "ip_address"
    WEB_APPLICATION = "web_application"
    API_ENDPOINT = "api_endpoint"
    CLOUD_RESOURCE = "cloud_resource"
    NETWORK_SERVICE = "network_service"


class AssetStatus(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    CHANGED = "changed"
    RETIRED = "retired"


class CriticalityTier(StrEnum):
    BUSINESS_CRITICAL = "business_critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ExposureClass(StrEnum):
    INTERNET_FACING = "internet_facing"
    PARTNER_FACING = "partner_facing"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class RecordSource(StrEnum):
    """Where a row came from. Drives the "simulated vs observed" labelling.

    `seed` rows are demonstration fixtures and MUST be presented as such;
    `passive_*` / `active_*` rows are observations made by the discovery
    engine against a network.
    """

    MANUAL = "manual"
    CSV_IMPORT = "csv_import"
    SEED = "seed"
    PASSIVE_DNS = "passive_dns"
    PASSIVE_CT_LOG = "passive_ct_log"
    ACTIVE_TLS_PROBE = "active_tls_probe"
    ACTIVE_HTTP_PROBE = "active_http_probe"
    ACTIVE_PORT_PROBE = "active_port_probe"
    CLOUD_INVENTORY = "cloud_inventory"
    API_IMPORT = "api_import"


#: Sources that represent a real observation of live infrastructure.
OBSERVED_SOURCES: frozenset[str] = frozenset(
    {
        RecordSource.PASSIVE_DNS.value,
        RecordSource.PASSIVE_CT_LOG.value,
        RecordSource.ACTIVE_TLS_PROBE.value,
        RecordSource.ACTIVE_HTTP_PROBE.value,
        RecordSource.ACTIVE_PORT_PROBE.value,
        RecordSource.CLOUD_INVENTORY.value,
    }
)


class ServiceState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    FILTERED = "filtered"
    UNRESPONSIVE = "unresponsive"


class IPVersion(StrEnum):
    V4 = "ipv4"
    V6 = "ipv6"


class CloudProvider(StrEnum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    ALIBABA = "alibaba"
    OTHER = "other"


class CertificateStatus(StrEnum):
    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    HOSTNAME_MISMATCH = "hostname_mismatch"
    SELF_SIGNED = "self_signed"
    WEAK_SIGNATURE = "weak_signature"
    NOT_OBSERVED = "not_observed"


class ScanType(StrEnum):
    PASSIVE_DNS = "passive_dns"
    CERTIFICATE_TRANSPARENCY = "certificate_transparency"
    TLS_CERTIFICATE = "tls_certificate"
    HTTP_FINGERPRINT = "http_fingerprint"
    PORT_EXPOSURE = "port_exposure"
    CLOUD_INVENTORY = "cloud_inventory"
    FULL_RECON = "full_recon"


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    API = "api"


class Severity(StrEnum):
    """Finding severity. `informational` is deliberately a distinct level."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


#: Used everywhere a severity must be turned into a number.
SEVERITY_WEIGHT: dict[str, int] = {
    Severity.CRITICAL.value: 10,
    Severity.HIGH.value: 7,
    Severity.MEDIUM.value: 4,
    Severity.LOW.value: 2,
    Severity.INFORMATIONAL.value: 1,
}

SEVERITY_ORDER: list[str] = [
    Severity.CRITICAL.value,
    Severity.HIGH.value,
    Severity.MEDIUM.value,
    Severity.LOW.value,
    Severity.INFORMATIONAL.value,
]


class RiskClassification(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class FindingType(StrEnum):
    VULNERABILITY = "vulnerability"
    EXPOSED_SERVICE = "exposed_service"
    MISCONFIGURATION = "misconfiguration"
    CERTIFICATE = "certificate"
    RISKY_ENDPOINT = "risky_endpoint"
    DATA_EXPOSURE = "data_exposure"
    OUTDATED_SOFTWARE = "outdated_software"
    DNS_CHANGE = "dns_change"


class FindingStatus(StrEnum):
    OPEN = "open"
    TRIAGED = "triaged"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REMEDIATED = "remediated"
    ACCEPTED_RISK = "accepted_risk"
    FALSE_POSITIVE = "false_positive"
    DUPLICATE = "duplicate"


OPEN_FINDING_STATUSES: frozenset[str] = frozenset(
    {
        FindingStatus.OPEN.value,
        FindingStatus.TRIAGED.value,
        FindingStatus.ASSIGNED.value,
        FindingStatus.IN_PROGRESS.value,
    }
)


class Confidence(StrEnum):
    """Distinguishes a verified observation from an inferred suspicion."""

    CONFIRMED = "confirmed"
    POTENTIAL = "potential"


class VulnerabilityStatus(StrEnum):
    UNRESOLVED = "unresolved"
    TRIAGED = "triaged"
    IN_REMEDIATION = "in_remediation"
    FIXED = "fixed"
    ACCEPTED_RISK = "accepted_risk"
    NOT_EXPLOITABLE = "not_exploitable"


class ChangeType(StrEnum):
    DNS_RECORD = "dns_record"
    IP_MAPPING = "ip_mapping"
    EXPOSED_PORT = "exposed_port"
    ASSET_CONFIGURATION = "asset_configuration"
    CERTIFICATE_ROTATION = "certificate_rotation"
    CLOUD_CONFIGURATION = "cloud_configuration"
    NEW_ASSET = "new_asset"
    REMOVED_ASSET = "removed_asset"
    SERVICE_VERSION = "service_version"


class AssetEventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    RETIRED = "retired"
    SCAN_OBSERVED = "scan_observed"
    FINDING_OPENED = "finding_opened"
    FINDING_CLOSED = "finding_closed"
    CERTIFICATE_OBSERVED = "certificate_observed"
    SERVICE_OBSERVED = "service_observed"
    CONFIGURATION_CHANGED = "configuration_changed"
    ASSIGNMENT_CHANGED = "assignment_changed"


class AlertType(StrEnum):
    NEW_ASSET = "new_asset"
    ASSET_REMOVED = "asset_removed"
    CERTIFICATE_EXPIRING = "certificate_expiring"
    CERTIFICATE_EXPIRED = "certificate_expired"
    NEW_EXPOSED_SERVICE = "new_exposed_service"
    RISKY_CONFIGURATION_CHANGE = "risky_configuration_change"
    CRITICAL_VULNERABILITY = "critical_vulnerability"
    RISKY_ENDPOINT = "risky_endpoint"
    SCAN_FAILED = "scan_failed"


class AlertStatus(StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"


class RemediationStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    WONT_FIX = "wont_fix"


class TaskPriority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IntegrationKind(StrEnum):
    DNS = "dns"
    CERTIFICATE_TRANSPARENCY = "certificate_transparency"
    TLS_PROBE = "tls_probe"
    HTTP_PROBE = "http_probe"
    PORT_SCANNER = "port_scanner"
    CLOUD_AWS = "cloud_aws"
    CLOUD_AZURE = "cloud_azure"
    CLOUD_GCP = "cloud_gcp"
    VULNERABILITY_FEED = "vulnerability_feed"
    NOTIFICATION_WEBHOOK = "notification_webhook"


class IntegrationStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    READY = "ready"
    ENABLED = "enabled"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class ReportFormat(StrEnum):
    CSV = "csv"
    PDF = "pdf"


class ReportStatus(StrEnum):
    REQUESTED = "requested"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditAction(StrEnum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    ACCESS_DENIED = "access_denied"
    PASSWORD_CHANGE = "password_change"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DISABLED = "user_disabled"
    COMPANY_CREATED = "company_created"
    COMPANY_UPDATED = "company_updated"
    MEMBERSHIP_GRANTED = "membership_granted"
    MEMBERSHIP_REVOKED = "membership_revoked"
    ASSET_CREATED = "asset_created"
    ASSET_UPDATED = "asset_updated"
    ASSET_IMPORTED = "asset_imported"
    ASSET_DELETED = "asset_deleted"
    AUTHORIZATION_CREATED = "authorization_created"
    AUTHORIZATION_APPROVED = "authorization_approved"
    AUTHORIZATION_REJECTED = "authorization_rejected"
    SCAN_REQUESTED = "scan_requested"
    SCAN_CANCELLED = "scan_cancelled"
    SCAN_COMPLETED = "scan_completed"
    SCAN_DENIED = "scan_denied"
    FINDING_UPDATED = "finding_updated"
    VULNERABILITY_UPDATED = "vulnerability_updated"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    REPORT_EXPORTED = "report_exported"
    INTEGRATION_UPDATED = "integration_updated"
    SETTINGS_UPDATED = "settings_updated"


def classify(score: float) -> str:
    """Map a 0-10 composite risk score onto its severity band."""
    if score >= 9.0:
        return RiskClassification.CRITICAL.value
    if score >= 7.0:
        return RiskClassification.HIGH.value
    if score >= 4.0:
        return RiskClassification.MEDIUM.value
    if score >= 1.5:
        return RiskClassification.LOW.value
    return RiskClassification.INFORMATIONAL.value
