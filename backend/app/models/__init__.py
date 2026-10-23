"""ORM model registry.

Importing this module registers every mapper with `Base.metadata`, which is what
`create_schema`, Alembic autogeneration and the string-based relationships all
depend on. Keep it exhaustive: a model missing here silently disappears from the
schema instead of raising.
"""

from __future__ import annotations

from app.models.alert import Alert, Notification
from app.models.asset import ApiEndpoint, Asset, AssetEvent, CloudResource, Domain, ExposedService, IPAddress
from app.models.certificate import Certificate
from app.models.enums import (
    OBSERVED_SOURCES,
    OPEN_FINDING_STATUSES,
    SEVERITY_ORDER,
    SEVERITY_WEIGHT,
    AlertStatus,
    AlertType,
    AssetEventType,
    AssetStatus,
    AssetType,
    AuditAction,
    AuditOutcome,
    AuthorizationScopeType,
    AuthorizationStatus,
    ChangeType,
    CertificateStatus,
    CloudProvider,
    CompanyStatus,
    Confidence,
    CriticalityTier,
    ExposureClass,
    FindingStatus,
    FindingType,
    Industry,
    IntegrationKind,
    IntegrationStatus,
    IPVersion,
    NotificationChannel,
    RecordSource,
    RemediationStatus,
    ReportFormat,
    ReportStatus,
    RiskClassification,
    RoleCode,
    ScanStatus,
    ScanTrigger,
    ScanType,
    ServiceState,
    Severity,
    TaskPriority,
    VerificationMethod,
    VulnerabilityStatus,
)
from app.models.identity import AlertPreference, AuditLog, CompanyMembership, Role, User, clear_login_failures, register_login_failure
from app.models.integration import Integration, Report
from app.models.risk import RISK_MODEL_VERSION, ConfigurationChange, RiskScore, classify
from app.models.scan import Scan, ScanEvent
from app.models.tenant import AuthorizationRecord, Company, ScanPolicy
from app.models.vulnerability import Finding, RemediationTask, Vulnerability

__all__ = [
    # tenant
    "Company",
    "AuthorizationRecord",
    "ScanPolicy",
    # identity
    "Role",
    "User",
    "CompanyMembership",
    "AlertPreference",
    "AuditLog",
    "register_login_failure",
    "clear_login_failures",
    # assets
    "Asset",
    "Domain",
    "IPAddress",
    "ApiEndpoint",
    "CloudResource",
    "ExposedService",
    "AssetEvent",
    # certificates
    "Certificate",
    # scans
    "Scan",
    "ScanEvent",
    # vulnerability / findings
    "Vulnerability",
    "Finding",
    "RemediationTask",
    # risk
    "RiskScore",
    "ConfigurationChange",
    "classify",
    "RISK_MODEL_VERSION",
    # alerting
    "Alert",
    "Notification",
    # integrations / reports
    "Integration",
    "Report",
    # enums
    "AlertStatus",
    "AlertType",
    "AssetEventType",
    "AssetStatus",
    "AssetType",
    "AuditAction",
    "AuditOutcome",
    "AuthorizationScopeType",
    "AuthorizationStatus",
    "ChangeType",
    "CertificateStatus",
    "CloudProvider",
    "CompanyStatus",
    "Confidence",
    "CriticalityTier",
    "ExposureClass",
    "FindingStatus",
    "FindingType",
    "Industry",
    "IntegrationKind",
    "IntegrationStatus",
    "IPVersion",
    "NotificationChannel",
    "OBSERVED_SOURCES",
    "OPEN_FINDING_STATUSES",
    "RecordSource",
    "RemediationStatus",
    "ReportFormat",
    "ReportStatus",
    "RiskClassification",
    "RoleCode",
    "ScanStatus",
    "ScanTrigger",
    "ScanType",
    "SEVERITY_ORDER",
    "SEVERITY_WEIGHT",
    "ServiceState",
    "Severity",
    "TaskPriority",
    "VerificationMethod",
    "VulnerabilityStatus",
]
