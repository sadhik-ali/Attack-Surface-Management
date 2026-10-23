"""Demonstration fixtures for the ASM platform.

Every row created here is sample data labelled ``source=seed``. No scan
described by this module reached a network, and no seeded value should be read
as a live observation. Hostnames use reserved ``.example`` domains only.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ROLE_DEFINITIONS
from app.core.security import hash_password
from app.db.session import create_schema, dispose_engine, session_scope
from app.models import (
    Alert,
    AlertPreference,
    ApiEndpoint,
    Asset,
    AssetEvent,
    AuditLog,
    AuthorizationRecord,
    Certificate,
    CloudResource,
    Company,
    CompanyMembership,
    ConfigurationChange,
    Domain,
    ExposedService,
    Finding,
    IPAddress,
    Integration,
    Notification,
    RemediationTask,
    RiskScore,
    Role,
    Scan,
    ScanEvent,
    ScanPolicy,
    User,
    Vulnerability,
)
from app.models.enums import (
    AlertStatus,
    AlertType,
    AssetEventType,
    AssetStatus,
    AssetType,
    AuditAction,
    AuditOutcome,
    AuthorizationScopeType,
    AuthorizationStatus,
    CertificateStatus,
    ChangeType,
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
    RecordSource,
    RemediationStatus,
    RoleCode,
    ScanStatus,
    ScanTrigger,
    ScanType,
    ServiceState,
    Severity,
    TaskPriority,
    VerificationMethod,
    VulnerabilityStatus,
    classify,
)
from app.models.risk import RISK_MODEL_VERSION
from app.services.risk import aggregate_asset_risk, aggregate_company_risk, assess_finding, severity_from_cvss

PASSWORD = "AsmDemo!2026"
SEED = RecordSource.SEED.value
PORTS = (22, 80, 443, 3306, 5432, 6379, 8080, 8443, 9200, 27017, 3389)
DB_PORTS = {3306, 5432, 6379, 9200, 27017}
MGMT_PORTS = {22, 3389}
TEAMS = ("Platform Engineering", "Security Operations", "Web Platform", "Data Engineering", "Identity & Access", "Infrastructure")
SERVICE_CATALOG: dict[int, tuple[str, str, str, str, bool]] = {
    22: ("ssh", "OpenSSH", "9.6p1 Ubuntu-3ubuntu13", "ssh", True),
    80: ("http", "nginx", "1.24.0", "http", False),
    443: ("https", "nginx", "1.25.3", "http", True),
    3306: ("mysql", "MySQL", "8.0.36", "database", False),
    5432: ("postgresql", "PostgreSQL", "16.2", "database", False),
    6379: ("redis", "Redis", "7.2.4", "database", False),
    8080: ("http-alt", "Apache Tomcat", "10.1.18", "http", False),
    8443: ("https-alt", "Microsoft IIS", "10.0", "http", True),
    9200: ("elasticsearch", "Elasticsearch", "8.12.2", "database", False),
    27017: ("mongodb", "MongoDB", "7.0.6", "database", False),
    3389: ("rdp", "Microsoft Terminal Services", "10.0", "management", True),
}
RECOMMENDATIONS = {
    FindingType.VULNERABILITY.value: "Apply the vendor patch and confirm the affected service version.",
    FindingType.EXPOSED_SERVICE.value: "Restrict the port with firewall rules and require authenticated access.",
    FindingType.MISCONFIGURATION.value: "Apply the hardening baseline and add a regression check.",
    FindingType.CERTIFICATE.value: "Renew the certificate and automate expiry monitoring.",
    FindingType.RISKY_ENDPOINT.value: "Require authentication, enforce object-level authorization and rate limit the endpoint.",
    FindingType.DATA_EXPOSURE.value: "Remove public access and audit the objects for sensitive data.",
    FindingType.OUTDATED_SOFTWARE.value: "Upgrade to a supported release and track versions continuously.",
    FindingType.DNS_CHANGE.value: "Remove the dangling record or reclaim the target before it is used.",
}
SERVICE_RECOMMENDATIONS = {
    "database": "Bind this database port to application subnets and require authenticated, encrypted connections.",
    "management": "Remove public access; require VPN or bastion access with MFA for management protocols.",
    "ssh": "Restrict SSH to bastion hosts, disable password authentication and enforce key-based access.",
    "http": "Keep the service patched and serve it over HTTPS with a valid certificate.",
}

COMPANY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "slug": "northwind",
        "name": "Northwind Technologies",
        "industry": Industry.TECHNOLOGY.value,
        "domain": "northwind.example",
        "website": "https://northwind.example",
        "contact_name": "Priya Nair",
        "contact_email": "security@northwind.example",
        "description": "SaaS product engineering company with a public API platform and partner integrations.",
        "tags": ["technology", "saas", "demo"],
        "pending_scope": "northwind-labs.example",
        "subdomains": ("www", "api", "portal", "app", "mail", "vpn", "admin", "staging", "dev", "cdn", "static", "docs", "support", "status", "gitlab", "jenkins", "reports", "sso"),
        "apps": (("accounts", "Customer Portal", CriticalityTier.BUSINESS_CRITICAL.value), ("partners", "Partner Console", CriticalityTier.HIGH.value)),
        "asns": (("AS16509", "Amazon.com, Inc.", "AWS"), ("AS13335", "Cloudflare, Inc.", "Cloudflare")),
        "geo": ("US", "United States", "Seattle"),
        "unauth_api": 0,
        "clouds": (("aws", "prod-assets", "s3-bucket", "us-east-1", True), ("azure", "app-vm-01", "virtual-machine", "westeurope", False), ("gcp", "data-lake", "gcs-bucket", "us-central1", False)),
    },
    {
        "slug": "meridian-health",
        "name": "Meridian Health Group",
        "industry": Industry.HEALTHCARE.value,
        "domain": "meridianhealth.example",
        "website": "https://meridianhealth.example",
        "contact_name": "Dr. Elena Vasquez",
        "contact_email": "security@meridianhealth.example",
        "description": "Regional healthcare group operating patient portals, clinical APIs and imaging services.",
        "tags": ["healthcare", "hipaa", "demo"],
        "pending_scope": "meridian-labs.example",
        "subdomains": ("www", "api", "portal", "app", "mail", "vpn", "admin", "staging", "dev", "cdn", "secure", "docs", "support", "status", "gitlab", "jenkins", "imaging", "sso"),
        "apps": (("mychart", "Patient Portal", CriticalityTier.BUSINESS_CRITICAL.value), ("providers", "Provider Console", CriticalityTier.HIGH.value)),
        "asns": (("AS8075", "Microsoft Corporation", "Azure"), ("AS13335", "Cloudflare, Inc.", "Cloudflare")),
        "geo": ("US", "United States", "Chicago"),
        "unauth_api": 0,
        "clouds": (("aws", "prod-assets", "s3-bucket", "us-east-2", False), ("azure", "clinical-vm-01", "virtual-machine", "eastus", True), ("gcp", "imaging-archive", "gcs-bucket", "us-central1", False)),
    },
    {
        "slug": "atlas-financial",
        "name": "Atlas Financial",
        "industry": Industry.FINANCIAL_SERVICES.value,
        "domain": "atlasfin.example",
        "website": "https://atlasfin.example",
        "contact_name": "Marcus Chen",
        "contact_email": "security@atlasfin.example",
        "description": "Digital wealth management firm with treasury, payments and advisor-facing services.",
        "tags": ["financial-services", "pci", "demo"],
        "pending_scope": "atlas-labs.example",
        "subdomains": ("www", "api", "portal", "app", "mail", "vpn", "admin", "staging", "dev", "cdn", "static", "docs", "support", "status", "gitlab", "jenkins", "treasury", "sso"),
        "apps": (("wealth", "Wealth Portal", CriticalityTier.BUSINESS_CRITICAL.value), ("advisors", "Advisor Console", CriticalityTier.HIGH.value)),
        "asns": (("AS15169", "Google LLC", "GCP"), ("AS13335", "Cloudflare, Inc.", "Cloudflare")),
        "geo": ("US", "United States", "New York"),
        "unauth_api": None,
        "clouds": (("aws", "prod-assets", "s3-bucket", "us-east-1", False), ("azure", "trading-vm-01", "virtual-machine", "westus2", True), ("gcp", "analytics-lake", "gcs-bucket", "us-east4", False)),
    },
)

USER_SPECS: tuple[dict[str, Any], ...] = (
    {"email": "platform@asm.example", "name": "Platform Administrator", "title": "Platform Owner", "role": RoleCode.SUPER_ADMIN.value, "memberships": (), "active": True, "scope": "All companies", "color": "#7c3aed"},
    {"email": "admin@northwind.example", "name": "Dana Whitfield", "title": "Director of Security", "role": RoleCode.COMPANY_ADMIN.value, "memberships": (("northwind", RoleCode.COMPANY_ADMIN.value),), "active": True, "scope": "Northwind Technologies", "color": "#0f766e"},
    {"email": "analyst@northwind.example", "name": "Ravi Menon", "title": "Senior Security Analyst", "role": RoleCode.SECURITY_ANALYST.value, "memberships": (("northwind", RoleCode.SECURITY_ANALYST.value), ("meridian-health", RoleCode.READ_ONLY_AUDITOR.value)), "active": True, "scope": "Northwind Technologies + Meridian Health (read-only)", "color": "#2563eb"},
    {"email": "auditor@meridian.example", "name": "Lena Ortiz", "title": "Compliance Auditor", "role": RoleCode.READ_ONLY_AUDITOR.value, "memberships": (("meridian-health", RoleCode.READ_ONLY_AUDITOR.value),), "active": True, "scope": "Meridian Health Group", "color": "#b45309"},
    {"email": "analyst@atlas.example", "name": "Tomas Berg", "title": "Security Analyst", "role": RoleCode.SECURITY_ANALYST.value, "memberships": (("atlas-financial", RoleCode.SECURITY_ANALYST.value),), "active": True, "scope": "Atlas Financial", "color": "#be123c"},
    {"email": "former@northwind.example", "name": "Chris Doyle", "title": "Former Contractor", "role": RoleCode.READ_ONLY_AUDITOR.value, "memberships": (("northwind", RoleCode.READ_ONLY_AUDITOR.value),), "active": False, "scope": "Northwind Technologies (disabled)", "color": "#64748b"},
)
DEMO_SLUGS = tuple(spec["slug"] for spec in COMPANY_SPECS)
DEMO_EMAILS = tuple(spec["email"] for spec in USER_SPECS)

CERT_PLANS: dict[str, tuple[tuple[str, int, str], ...]] = {
    "northwind": (("expired", -12, "www"), ("hostname_mismatch", 64, "api"), ("valid", 210, "@"), ("self_signed", 120, "admin"), ("valid", 330, "mail")),
    "meridian-health": (("expiring", 18, "www"), ("valid", 150, "@"), ("valid", 240, "api"), ("self_signed", 120, "admin"), ("valid", 90, "portal")),
    "atlas-financial": (("expiring", 6, "www"), ("valid", 95, "api"), ("valid", 180, "@"), ("self_signed", 120, "admin"), ("valid", 300, "mail")),
}
SCAN_PLANS = (
    {"name": "Weekly passive DNS sweep", "type": ScanType.PASSIVE_DNS.value, "status": ScanStatus.COMPLETED.value, "trigger": ScanTrigger.SCHEDULED.value, "days": 78, "duration": 64, "total": 1, "ok": 1, "failed": 0, "found": 18, "new": 4, "changed": 0, "services": 0, "certs": 0, "findings": 0, "changes": 3, "error": None},
    {"name": "Certificate transparency delta", "type": ScanType.CERTIFICATE_TRANSPARENCY.value, "status": ScanStatus.COMPLETED.value, "trigger": ScanTrigger.SCHEDULED.value, "days": 46, "duration": 88, "total": 1, "ok": 1, "failed": 0, "found": 22, "new": 3, "changed": 1, "services": 0, "certs": 5, "findings": 1, "changes": 1, "error": None},
    {"name": "TLS certificate review", "type": ScanType.TLS_CERTIFICATE.value, "status": ScanStatus.COMPLETED_WITH_ERRORS.value, "trigger": ScanTrigger.MANUAL.value, "days": 21, "duration": 118, "total": 8, "ok": 7, "failed": 1, "found": 6, "new": 1, "changed": 0, "services": 0, "certs": 4, "findings": 2, "changes": 1, "error": "1 host timed out during the TLS handshake"},
    {"name": "Full surface review", "type": ScanType.FULL_RECON.value, "status": ScanStatus.FAILED.value, "trigger": ScanTrigger.MANUAL.value, "days": 6, "duration": 33, "total": 12, "ok": 4, "failed": 8, "found": 9, "new": 2, "changed": 1, "services": 3, "certs": 1, "findings": 0, "changes": 2, "error": "Probe budget exhausted after repeated connection timeouts"},
    {"name": "Scheduled full re-discovery", "type": ScanType.FULL_RECON.value, "status": ScanStatus.QUEUED.value, "trigger": ScanTrigger.SCHEDULED.value, "days": 0, "duration": 0, "total": 1, "ok": 0, "failed": 0, "found": 0, "new": 0, "changed": 0, "services": 0, "certs": 0, "findings": 0, "changes": 0, "error": None},
)
VULN_TEMPLATES = (
    ("CVE-2021-44228", "Apache Log4j2 remote code execution (Log4Shell)", 10.0, "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", "weaponized", "Apache Log4j2", "2.14.1", "2.17.1", "api", True, "Upgrade Log4j2 to 2.17.1 or later and rotate credentials reachable from the process."),
    ("CVE-2023-44487", "HTTP/2 rapid reset denial of service", 7.5, "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H", "proof_of_concept", "nginx", "1.24.0", "1.25.3", "www", False, "Upgrade nginx and enforce connection and request limits at the edge."),
    ("CVE-2022-22965", "Spring Framework remote code execution (Spring4Shell)", 9.8, "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", "weaponized", "Spring Framework", "5.3.17", "5.3.18", "web", False, "Upgrade Spring Framework and remove the vulnerable data-binding configuration."),
    ("CVE-2024-6387", "OpenSSH regreSSHion unauthenticated remote code execution", 8.1, "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H", "proof_of_concept", "OpenSSH", "9.6p1", "9.7p1", "ip", False, "Upgrade OpenSSH to 9.7p1 or later and restrict the daemon to bastion access."),
)
VULN_STATUS_PLANS = (
    (VulnerabilityStatus.UNRESOLVED.value, VulnerabilityStatus.TRIAGED.value, VulnerabilityStatus.IN_REMEDIATION.value, VulnerabilityStatus.FIXED.value),
    (VulnerabilityStatus.UNRESOLVED.value, VulnerabilityStatus.TRIAGED.value, VulnerabilityStatus.IN_REMEDIATION.value, VulnerabilityStatus.ACCEPTED_RISK.value),
    (VulnerabilityStatus.UNRESOLVED.value, VulnerabilityStatus.TRIAGED.value, VulnerabilityStatus.FIXED.value, VulnerabilityStatus.NOT_EXPLOITABLE.value),
)
FINDING_TEMPLATES: tuple[dict[str, Any], ...] = (
    {"title": "Log4Shell in internet-facing API gateway", "type": FindingType.VULNERABILITY.value, "severity": Severity.CRITICAL.value, "status": FindingStatus.OPEN.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.API_ENDPOINT.value, "index": 0, "cvss": 10.0, "exploit": True, "vuln": 0, "cert": None, "service": None, "change": None, "task": False},
    {"title": "Administrative API reachable without network restriction", "type": FindingType.RISKY_ENDPOINT.value, "severity": Severity.CRITICAL.value, "status": FindingStatus.ASSIGNED.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.API_ENDPOINT.value, "index": 1, "cvss": 9.1, "exploit": False, "vuln": None, "cert": None, "service": None, "change": None, "task": True},
    {"title": "TLS certificate for primary web host requires renewal", "type": FindingType.CERTIFICATE.value, "severity": Severity.HIGH.value, "status": FindingStatus.OPEN.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.SUBDOMAIN.value, "index": 0, "cvss": None, "exploit": False, "vuln": None, "cert": 0, "service": None, "change": None, "task": False},
    {"title": "Database service exposed to the internet", "type": FindingType.EXPOSED_SERVICE.value, "severity": Severity.CRITICAL.value, "status": FindingStatus.IN_PROGRESS.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.NETWORK_SERVICE.value, "index": 0, "cvss": None, "exploit": True, "vuln": None, "cert": None, "service": "risky", "change": None, "task": True},
    {"title": "Missing HTTP security headers on customer portal", "type": FindingType.MISCONFIGURATION.value, "severity": Severity.LOW.value, "status": FindingStatus.OPEN.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.WEB_APPLICATION.value, "index": 0, "cvss": None, "exploit": False, "vuln": None, "cert": None, "service": None, "change": None, "task": False},
    {"title": "Outdated nginx build exposed to HTTP/2 rapid reset", "type": FindingType.OUTDATED_SOFTWARE.value, "severity": Severity.HIGH.value, "status": FindingStatus.TRIAGED.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.SUBDOMAIN.value, "index": 0, "cvss": 7.5, "exploit": True, "vuln": 1, "cert": None, "service": "nginx", "change": None, "task": True},
    {"title": "Public cloud bucket permits anonymous listing", "type": FindingType.DATA_EXPOSURE.value, "severity": Severity.HIGH.value, "status": FindingStatus.OPEN.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.CLOUD_RESOURCE.value, "index": 0, "cvss": None, "exploit": False, "vuln": None, "cert": None, "service": None, "change": None, "task": False},
    {"title": "Default credentials accepted by Jenkins login", "type": FindingType.MISCONFIGURATION.value, "severity": Severity.CRITICAL.value, "status": FindingStatus.ASSIGNED.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.SUBDOMAIN.value, "index": 15, "cvss": 9.8, "exploit": True, "vuln": None, "cert": None, "service": None, "change": None, "task": True},
    {"title": "Dangling CNAME record enables subdomain takeover", "type": FindingType.DNS_CHANGE.value, "severity": Severity.HIGH.value, "status": FindingStatus.OPEN.value, "confidence": Confidence.POTENTIAL.value, "asset": AssetType.SUBDOMAIN.value, "index": 9, "cvss": 8.1, "exploit": True, "vuln": None, "cert": None, "service": None, "change": 7, "task": False},
    {"title": "Legacy TLS 1.0 still enabled on API host", "type": FindingType.CERTIFICATE.value, "severity": Severity.MEDIUM.value, "status": FindingStatus.OPEN.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.SUBDOMAIN.value, "index": 1, "cvss": None, "exploit": False, "vuln": None, "cert": 1, "service": "nginx", "change": None, "task": False},
    {"title": "Directory listing enabled on a public host", "type": FindingType.MISCONFIGURATION.value, "severity": Severity.INFORMATIONAL.value, "status": FindingStatus.FALSE_POSITIVE.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.SUBDOMAIN.value, "index": 10, "cvss": None, "exploit": False, "vuln": None, "cert": None, "service": None, "change": None, "task": False},
    {"title": "Spring4Shell exposure in partner console", "type": FindingType.VULNERABILITY.value, "severity": Severity.HIGH.value, "status": FindingStatus.REMEDIATED.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.WEB_APPLICATION.value, "index": 1, "cvss": 9.8, "exploit": True, "vuln": 2, "cert": None, "service": None, "change": None, "task": True},
    {"title": "GraphQL introspection enabled in production", "type": FindingType.RISKY_ENDPOINT.value, "severity": Severity.MEDIUM.value, "status": FindingStatus.ACCEPTED_RISK.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.API_ENDPOINT.value, "index": 2, "cvss": None, "exploit": False, "vuln": None, "cert": None, "service": None, "change": None, "task": False},
    {"title": "Self-signed certificate on administrative host", "type": FindingType.CERTIFICATE.value, "severity": Severity.LOW.value, "status": FindingStatus.OPEN.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.SUBDOMAIN.value, "index": 6, "cvss": None, "exploit": False, "vuln": None, "cert": 3, "service": None, "change": None, "task": False},
    {"title": "Outdated OpenSSH daemon on bastion IP", "type": FindingType.OUTDATED_SOFTWARE.value, "severity": Severity.HIGH.value, "status": FindingStatus.IN_PROGRESS.value, "confidence": Confidence.CONFIRMED.value, "asset": AssetType.IP_ADDRESS.value, "index": 0, "cvss": 8.1, "exploit": True, "vuln": 3, "cert": None, "service": "ssh", "change": None, "task": True},
)
CHANGE_PLANS = (
    (ChangeType.DNS_RECORD.value, Severity.HIGH.value, True, False, False),
    (ChangeType.CERTIFICATE_ROTATION.value, Severity.LOW.value, False, False, True),
    (ChangeType.EXPOSED_PORT.value, Severity.CRITICAL.value, False, True, False),
    (ChangeType.ASSET_CONFIGURATION.value, Severity.MEDIUM.value, False, False, False),
    (ChangeType.SERVICE_VERSION.value, Severity.LOW.value, False, False, True),
    (ChangeType.NEW_ASSET.value, Severity.INFORMATIONAL.value, False, False, False),
    (ChangeType.IP_MAPPING.value, Severity.MEDIUM.value, False, False, False),
    (ChangeType.DNS_RECORD.value, Severity.LOW.value, False, False, True),
    (ChangeType.EXPOSED_PORT.value, Severity.HIGH.value, False, False, True),
    (ChangeType.CERTIFICATE_ROTATION.value, Severity.LOW.value, False, False, False),
    (ChangeType.ASSET_CONFIGURATION.value, Severity.MEDIUM.value, False, False, False),
    (ChangeType.SERVICE_VERSION.value, Severity.INFORMATIONAL.value, False, False, False),
)
ALERT_TEMPLATES = (
    (AlertType.NEW_ASSET.value, Severity.MEDIUM.value, AlertStatus.NEW.value, "New asset appeared in {company}", "{new_asset} was added to the inventory by the latest sample discovery run.", "Verify ownership, the responsible team and whether the asset should be internet-facing."),
    (AlertType.NEW_EXPOSED_SERVICE.value, Severity.HIGH.value, AlertStatus.NEW.value, "New exposed service on {svc_host}", "{svc_product} {svc_version} is listening on TCP {svc_port} and is marked {svc_expectation}.", "Confirm the business need for this port and restrict it to trusted networks."),
    (AlertType.CRITICAL_VULNERABILITY.value, Severity.CRITICAL.value, AlertStatus.NEW.value, "Critical vulnerability: {crit_title}", "{crit_title} affects {crit_asset} and has a risk score of {crit_score}.", "Patch the affected component and validate the fix with an authorized follow-up scan."),
    (AlertType.CERTIFICATE_EXPIRED.value, Severity.HIGH.value, AlertStatus.ACKNOWLEDGED.value, "Certificate expiry on {cert_host}", "The monitored certificate for {cert_host} is {cert_state}.", "Renew or replace the certificate and confirm the full chain is served."),
    (AlertType.CERTIFICATE_EXPIRING.value, Severity.HIGH.value, AlertStatus.ACKNOWLEDGED.value, "Certificate expiry approaching for {soon_host}", "The certificate for {soon_host} has {soon_days} days remaining in the monitoring window.", "Schedule renewal before the expiry threshold and automate the next rotation."),
    (AlertType.RISKY_CONFIGURATION_CHANGE.value, Severity.HIGH.value, AlertStatus.NEW.value, "Suspicious DNS change on {change_asset}", "The A record for {change_asset} now points at {change_new} in {change_asn}; the previous answer was outside the approved ASN.", "Confirm the change ticket and validate DNS ownership before the TTL expires."),
    (AlertType.SCAN_FAILED.value, Severity.MEDIUM.value, AlertStatus.NEW.value, "Scan failed: {scan_name}", "The sample scan stopped after {scan_failed} of {scan_total} targets: {scan_error}.", "Review the timeout budget and re-run within policy limits."),
    (AlertType.RISKY_ENDPOINT.value, Severity.HIGH.value, AlertStatus.DISMISSED.value, "API endpoint exposes excessive data", "{api_url} returns more fields than the console needs and is reachable with {api_auth}.", "Reduce the response schema and enforce object-level authorization."),
    (AlertType.ASSET_REMOVED.value, Severity.MEDIUM.value, AlertStatus.RESOLVED.value, "Asset retired: {retired_name}", "{retired_name} has not been observed since the retirement window and was marked retired.", "Confirm DNS cleanup and remove residual firewall rules."),
    (AlertType.NEW_EXPOSED_SERVICE.value, Severity.HIGH.value, AlertStatus.NEW.value, "Management service exposed on {svc2_host}", "TCP {svc2_port} exposes {svc2_product}, a management interface that should not be internet-facing.", "Close the port, require VPN access and add the host to the management allowlist."),
    (AlertType.RISKY_CONFIGURATION_CHANGE.value, Severity.HIGH.value, AlertStatus.RESOLVED.value, "Unplanned port exposure on {unplanned_asset}", "A new listener appeared on {unplanned_asset} without a matching change request.", "Validate the listener, remove it if unowned and document the approved exception."),
)
INTEGRATION_SPECS = (
    (IntegrationKind.DNS.value, "System DNS resolver", IntegrationStatus.ENABLED.value, True, True, "dns_resolution", "Recursive DNS lookups via the system resolver for A, AAAA, CNAME, MX, NS and TXT records.", {"resolver": "system", "record_types": ["A", "AAAA", "CNAME", "MX", "NS", "TXT"], "timeout_seconds": 4.0}),
    (IntegrationKind.CERTIFICATE_TRANSPARENCY.value, "crt.sh certificate transparency", IntegrationStatus.ENABLED.value, True, True, "ct_log_search", "Read-only crt.sh query that enumerates names observed in certificate transparency logs for a root domain.", {"provider": "crt.sh", "endpoint": "https://crt.sh/", "rate_limit_per_minute": 10, "timeout_seconds": 15}),
    (IntegrationKind.TLS_PROBE.value, "TLS certificate probe", IntegrationStatus.ENABLED.value, True, True, "tls_certificate_probe", "One bounded TLS handshake per host:port to capture the presented certificate, SANs and negotiated version.", {"port": 443, "sni": True, "timeout_seconds": 6.0, "captures_chain": True}),
    (IntegrationKind.HTTP_PROBE.value, "HTTP fingerprint probe", IntegrationStatus.ENABLED.value, True, True, "http_fingerprint", "HEAD/GET request that records status, server header, title and a small technology fingerprint. Body capped at 200 KB.", {"methods": ["GET", "HEAD"], "follow_redirects": True, "max_body_bytes": 200000, "timeout_seconds": 8.0}),
    (IntegrationKind.PORT_SCANNER.value, "TCP connect check", IntegrationStatus.DISABLED.value, True, True, "tcp_connect_check", "Only a safe TCP connect presence check is implemented: no nmap, no payloads, no banner grabbing and no version probing.", {"mode": "tcp_connect", "ports": list(PORTS), "timeout_seconds": 2.0, "service_detection": False, "nmap": False}),
    (IntegrationKind.CLOUD_AWS.value, "AWS cloud inventory", IntegrationStatus.UNCONFIGURED.value, False, False, None, "Not implemented: cloud inventory is not wired up. Requires read-only IAM credentials; no AWS SDK client exists in this build.", {}),
    (IntegrationKind.CLOUD_AZURE.value, "Azure cloud inventory", IntegrationStatus.UNCONFIGURED.value, False, False, None, "Not implemented: requires an Entra service principal with Reader scope. No Azure SDK client exists in this build.", {}),
    (IntegrationKind.CLOUD_GCP.value, "GCP cloud inventory", IntegrationStatus.UNCONFIGURED.value, False, False, None, "Not implemented: requires a read-only service account. No GCP API client exists in this build.", {}),
    (IntegrationKind.VULNERABILITY_FEED.value, "Vulnerability enrichment feed", IntegrationStatus.UNCONFIGURED.value, False, False, None, "Not implemented: CVE enrichment requires an authenticated NVD or GHSA feed and an API key. Seeded vulnerabilities use enrichment_source='demo'.", {}),
    (IntegrationKind.NOTIFICATION_WEBHOOK.value, "Outbound notification webhook", IntegrationStatus.UNCONFIGURED.value, False, False, None, "Not implemented: outbound webhook delivery requires an endpoint URL and a signing secret. No secret is stored by this seed.", {}),
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_asset(company: Company, spec: dict[str, Any], name: str, asset_type: str, criticality: str, exposure: str, environment: str, owner: str, tags: list[str], first_seen: datetime, last_seen: datetime, rng: random.Random, *, status: str = AssetStatus.ACTIVE.value, url: str | None = None) -> Asset:
    return Asset(
        company_id=company.id,
        name=name,
        normalized_identifier=f"{asset_type}:{name.lower()}",
        asset_type=asset_type,
        status=status,
        criticality=criticality,
        exposure=exposure,
        description=f"Seeded {asset_type.replace('_', ' ')} in the {environment} environment.",
        owner=owner,
        technical_contact=spec["contact_email"],
        environment=environment,
        url=url,
        tags=tags,
        attributes={"demo": True},
        source=SEED,
        first_seen=first_seen,
        last_seen=last_seen,
        observation_count=rng.randint(4, 42),
    )


def _first_last(rng: random.Random, now: datetime) -> tuple[datetime, datetime]:
    first = now - timedelta(days=rng.randint(30, 120), hours=rng.randint(0, 20))
    last = now - timedelta(days=rng.randint(0, 3), hours=rng.randint(0, 20))
    return first, last


def _http_profile(label: str) -> tuple[int, str, str, list[str]]:
    profiles = {
        "admin": (401, "nginx", "Administrator sign-in", ["nginx", "next.js"]),
        "vpn": (302, "Apache", "Remote access", ["apache", "openvpn"]),
        "jenkins": (403, "Jetty", "Sign in [Jenkins]", ["java", "jenkins"]),
        "backup": (503, "nginx", "Service unavailable", ["nginx"]),
        "api": (200, "nginx", "API gateway", ["nginx", "node.js"]),
        "cdn": (200, "Cloudflare", "Edge network", ["cloudflare"]),
        "static": (200, "nginx", "Static assets", ["nginx"]),
        "docs": (200, "nginx", "Documentation", ["nginx", "docusaurus"]),
        "gitlab": (200, "nginx", "GitLab", ["nginx", "gitlab"]),
        "portal": (200, "nginx", "Customer portal", ["nginx", "react"]),
        "mail": (200, "nginx", "Webmail", ["nginx", "roundcube"]),
    }
    return profiles.get(label, (200, "nginx", "Welcome", ["nginx"]))


API_ROUTES = {
    "northwind": (("GET", "/v2/accounts", "rest", "bearer", 200), ("POST", "/v2/invoices", "rest", "bearer", 201), ("GET", "/graphql", "graphql", "apikey", 200)),
    "meridian-health": (("GET", "/fhir/Patient", "rest", "apikey", 200), ("POST", "/v2/appointments", "rest", "bearer", 201), ("GET", "/graphql", "graphql", "apikey", 200)),
    "atlas-financial": (("GET", "/v2/accounts", "rest", "bearer", 200), ("POST", "/v2/transfers", "rest", "bearer", 201), ("GET", "/graphql", "graphql", "apikey", 200)),
}


async def _seed_assets(session: AsyncSession, company: Company, spec: dict[str, Any], cidx: int, rng: random.Random, now: datetime) -> dict[str, Any]:
    domain = spec["domain"]
    assets: list[Asset] = []
    first, last = _first_last(rng, now)
    root = _new_asset(company, spec, domain, AssetType.DOMAIN.value, CriticalityTier.HIGH.value, ExposureClass.INTERNET_FACING.value, "production", "Web Platform", ["root-domain", "production"], first, last, rng, url=f"https://{domain}")
    assets.append(root)

    sub_assets: list[Asset] = []
    critical_labels = {"portal", "secure", "treasury", "payments"}
    high_labels = {"www", "api", "app", "vpn", "admin", "sso"}
    for idx, label in enumerate(spec["subdomains"]):
        fqdn = f"{label}.{domain}"
        environment = "staging" if label == "staging" else "development" if label == "dev" else "production"
        exposure = ExposureClass.INTERNAL.value if label == "reports" else ExposureClass.INTERNET_FACING.value
        criticality = CriticalityTier.BUSINESS_CRITICAL.value if label in critical_labels else CriticalityTier.HIGH.value if label in high_labels else CriticalityTier.MEDIUM.value if idx % 3 else CriticalityTier.UNKNOWN.value
        first, last = _first_last(rng, now)
        asset = _new_asset(company, spec, fqdn, AssetType.SUBDOMAIN.value, criticality, exposure, environment, TEAMS[idx % len(TEAMS)], [label, environment, "external" if exposure == ExposureClass.INTERNET_FACING.value else "internal"], first, last, rng, status=AssetStatus.CHANGED.value if label in {"jenkins", "staging"} else AssetStatus.ACTIVE.value, url=f"https://{fqdn}")
        if asset.status == AssetStatus.CHANGED.value:
            asset.last_changed_at = last - timedelta(days=2)
        sub_assets.append(asset)
        assets.append(asset)

    web_assets: list[Asset] = []
    for idx, (label, title, criticality) in enumerate(spec["apps"]):
        fqdn = f"{label}.{domain}"
        first, last = _first_last(rng, now)
        asset = _new_asset(company, spec, fqdn, AssetType.WEB_APPLICATION.value, criticality, ExposureClass.PARTNER_FACING.value if idx else ExposureClass.INTERNET_FACING.value, "production", "Web Platform", ["web_application", title.lower().replace(" ", "-")], first, last, rng, url=f"https://{fqdn}")
        web_assets.append(asset)
        assets.append(asset)

    nets = (("203.0.113", 10), ("198.51.100", 20), ("192.0.2", 30), ("203.0.113", 110))
    addresses = [f"{net}.{base + cidx * 4 + i}" for i, (net, base) in enumerate(nets)]
    ip_assets: list[Asset] = []
    for idx, address in enumerate(addresses):
        first, last = _first_last(rng, now)
        asset = _new_asset(company, spec, address, AssetType.IP_ADDRESS.value, (CriticalityTier.HIGH.value, CriticalityTier.MEDIUM.value, CriticalityTier.UNKNOWN.value, CriticalityTier.MEDIUM.value)[idx], ExposureClass.INTERNET_FACING.value, "production", "Infrastructure", ["ip", "external"], first, last, rng)
        ip_assets.append(asset)
        assets.append(asset)

    api_assets: list[Asset] = []
    api_routes = API_ROUTES[spec["slug"]]
    for idx, (method, path, api_format, auth_type, status) in enumerate(api_routes):
        url = f"https://api.{domain}{path}"
        first, last = _first_last(rng, now)
        asset = _new_asset(company, spec, f"{method} {url}", AssetType.API_ENDPOINT.value, CriticalityTier.HIGH.value if idx == 0 else CriticalityTier.MEDIUM.value, ExposureClass.INTERNET_FACING.value, "production", "API Platform", ["api", "production"], first, last, rng, url=url)
        api_assets.append(asset)
        assets.append(asset)

    cloud_assets: list[Asset] = []
    provider_accounts = {"aws": ("123456789012", f"{spec['slug']}-prod"), "azure": ("00000000-0000-0000-0000-000000000000", f"{spec['slug']}-prod"), "gcp": (f"{spec['slug']}-demo-project", f"{spec['slug']}-prod")}
    for idx, (provider, suffix, resource_type, region, public) in enumerate(spec["clouds"]):
        name = f"{spec['slug']}-{suffix}"
        first, last = _first_last(rng, now)
        asset = _new_asset(company, spec, name, AssetType.CLOUD_RESOURCE.value, CriticalityTier.HIGH.value if public else CriticalityTier.MEDIUM.value, ExposureClass.INTERNET_FACING.value if public else ExposureClass.INTERNAL.value, "production", "Cloud Platform", ["cloud", provider], first, last, rng)
        cloud_assets.append(asset)
        assets.append(asset)
        asset.attributes.update({"provider": provider, "region": region, "resource_type": resource_type, "external_id": name})

    first, last = _first_last(rng, now)
    network_asset = _new_asset(company, spec, f"{domain}:9200", AssetType.NETWORK_SERVICE.value, CriticalityTier.HIGH.value, ExposureClass.INTERNET_FACING.value, "production", "Infrastructure", ["service", "elasticsearch"], first, last, rng, url=f"https://{domain}:9200")
    network_asset.attributes.update({"port": 9200, "protocol": "tcp"})
    assets.append(network_asset)

    first = now - timedelta(days=118)
    last = now - timedelta(days=14)
    retired = _new_asset(company, spec, f"legacy.{domain}", AssetType.SUBDOMAIN.value, CriticalityTier.UNKNOWN.value, ExposureClass.UNKNOWN.value, "production", "Infrastructure", ["legacy", "retired"], first, last, rng, status=AssetStatus.RETIRED.value)
    retired.retired_at = now - timedelta(days=12)
    retired.last_changed_at = retired.retired_at
    retired.observation_count = 4
    assets.append(retired)

    session.add_all(assets)
    await session.flush()

    ip_rows: list[IPAddress] = []
    for idx, (asset, address) in enumerate(zip(ip_assets, addresses)):
        asn, org, provider = spec["asns"][idx % len(spec["asns"])]
        ip_rows.append(IPAddress(company_id=company.id, asset_id=asset.id, address=address, version=IPVersion.V4.value, is_private=False, reverse_dns=f"host-{address.replace('.', '-')}.example", geo_country=spec["geo"][0], geo_country_name=spec["geo"][1], geo_city=spec["geo"][2], asn=asn, asn_organization=org, provider_hint=provider, is_cloud_elastic_ip=idx < 2, source=SEED))
    session.add_all(ip_rows)
    await session.flush()

    domains: dict[str, Domain] = {}
    root_domain = Domain(company_id=company.id, asset_id=root.id, fqdn=domain, root_domain=domain, host_label=None, is_subdomain=False, is_wildcard=False, registrar="Example Registrar, Inc.", registrant_organization=company.name, nameservers=["ns1.example", "ns2.example"], dns_records=[{"type": "A", "value": addresses[0], "ttl": 300}, {"type": "MX", "value": f"mail.{domain}", "ttl": 3600}, {"type": "TXT", "value": "v=spf1 include:_spf.example -all", "ttl": 3600}], dns_resolved_at=root.last_seen, resolves_to=[addresses[0]], web_server="nginx", http_status=200, http_title=company.name, technologies=["nginx", "react"], source=SEED)
    domains[domain] = root_domain
    session.add(root_domain)
    await session.flush()

    domain_rows: list[Domain] = []
    for idx, (label, asset) in enumerate(zip(spec["subdomains"], sub_assets)):
        fqdn = f"{label}.{domain}"
        status, server, title, technologies = _http_profile(label)
        resolved = [addresses[idx % 4]] if label not in {"cdn", "static"} else [addresses[idx % 4], addresses[(idx + 1) % 4]]
        records = [{"type": "CNAME", "value": "edge.example", "ttl": 300}] if label in {"cdn", "static"} else [{"type": "A", "value": value, "ttl": 300} for value in resolved]
        if label == "mail":
            records.append({"type": "MX", "value": f"mail.{domain}", "ttl": 3600})
        if label in {"docs", "status"}:
            records.append({"type": "TXT", "value": "v=spf1 include:_spf.example -all", "ttl": 3600})
        domain_rows.append(Domain(company_id=company.id, asset_id=asset.id, fqdn=fqdn, root_domain=domain, host_label=label, is_subdomain=True, is_wildcard=False, parent_domain_id=root_domain.id, registrar="Example Registrar, Inc.", registrant_organization=company.name, nameservers=["ns1.example", "ns2.example"], dns_records=records, dns_resolved_at=asset.last_seen, resolves_to=resolved, web_server=server, http_status=status, http_title=title, technologies=technologies, source=SEED))
    for idx, (label, title, _) in enumerate(spec["apps"]):
        fqdn = f"{label}.{domain}"
        asset = web_assets[idx]
        domain_rows.append(Domain(company_id=company.id, asset_id=asset.id, fqdn=fqdn, root_domain=domain, host_label=label, is_subdomain=True, is_wildcard=False, parent_domain_id=root_domain.id, registrar="Example Registrar, Inc.", registrant_organization=company.name, nameservers=["ns1.example", "ns2.example"], dns_records=[{"type": "A", "value": addresses[idx % 4], "ttl": 300}], dns_resolved_at=asset.last_seen, resolves_to=[addresses[idx % 4]], web_server="nginx", http_status=200, http_title=title, technologies=["nginx", "react"], source=SEED))
    domain_rows.append(Domain(company_id=company.id, asset_id=retired.id, fqdn=retired.name, root_domain=domain, host_label="legacy", is_subdomain=True, is_wildcard=False, parent_domain_id=root_domain.id, registrar="Example Registrar, Inc.", registrant_organization=company.name, nameservers=["ns1.example", "ns2.example"], dns_records=[], dns_resolved_at=retired.last_seen, resolves_to=[], web_server="nginx", http_status=404, http_title="Not found", technologies=[], source=SEED))
    session.add_all(domain_rows)
    await session.flush()
    for row in domain_rows:
        domains[row.fqdn] = row

    api_rows: list[ApiEndpoint] = []
    for idx, (asset, (method, path, api_format, auth_type, status)) in enumerate(zip(api_assets, api_routes)):
        unauth = spec["unauth_api"] == idx
        url = f"https://api.{domain}{path}"
        api_rows.append(ApiEndpoint(company_id=company.id, asset_id=asset.id, url=url, method=method, path=path, url_hash=_sha(f"{method}:{url}"), api_format=api_format, summary=f"Demonstration {api_format} endpoint used by {company.name}.", auth_type="none" if unauth else auth_type, requires_auth=not unauth, unauthenticated_access=unauth, is_deprecated=idx == 2, is_documented=idx == 0, version="v2" if idx < 2 else None, owner="API Platform", last_status_code=200 if unauth else status, last_latency_ms=rng.randint(65, 480), response_media_type="application/json", source=SEED))
    session.add_all(api_rows)
    await session.flush()

    cloud_rows: list[CloudResource] = []
    for idx, (asset, (provider, suffix, resource_type, region, public)) in enumerate(zip(cloud_assets, spec["clouds"])):
        account_id, account_alias = provider_accounts[provider]
        external_id = f"arn:aws:s3:::{asset.name}" if provider == "aws" else f"/subscriptions/{account_id}/resourceGroups/rg-{spec['slug']}/providers/Microsoft.Compute/virtualMachines/{asset.name}" if provider == "azure" else f"projects/{account_id}/buckets/{asset.name}"
        groups = ["sg-web-public", "sg-app-internal"] if public else ["sg-private", "sg-monitoring"]
        cloud_rows.append(CloudResource(company_id=company.id, asset_id=asset.id, provider=provider, account_id=account_id, account_alias=account_alias, region=region, zone=f"{region}-a", resource_type=resource_type, external_id=external_id, public_access=public, public_acl=public, encrypted=not (idx == 1 and cidx == 1), logging_enabled=idx != 1, imdsv2_required=True if provider == "aws" else None, security_groups=groups, resource_attributes={"demo": True, "owner": "Cloud Platform"}, source=SEED, observed_at=asset.last_seen))
    session.add_all(cloud_rows)
    await session.flush()

    return {"assets": assets, "active": [a for a in assets if a.status != AssetStatus.RETIRED.value], "sub_assets": sub_assets, "web_assets": web_assets, "ip_assets": ip_assets, "ip_rows": ip_rows, "api_assets": api_assets, "cloud_assets": cloud_assets, "network": network_asset, "retired": retired, "domains": domains, "root_domain": root_domain, "addresses": addresses, "domain_asset_ids": {d.asset_id: d.id for d in domains.values()}}


async def _seed_services(session: AsyncSession, company: Company, bundle: dict[str, Any], rng: random.Random, now: datetime) -> list[ExposedService]:
    host_by_ip: dict[str, str] = {}
    for fqdn, domain_row in bundle["domains"].items():
        for address in domain_row.resolves_to:
            host_by_ip.setdefault(address, fqdn)

    services: list[ExposedService] = []
    forced_ports = (5432, 3389, 6379, 27017)
    for idx, (asset, ip_row) in enumerate(zip(bundle["ip_assets"], bundle["ip_rows"])):
        ports = rng.sample(list(PORTS), rng.randint(3, 6))
        forced = forced_ports[idx]
        if forced not in ports:
            ports[-1] = forced
        if idx == 0 and 22 not in ports:
            ports.append(22)
        for j, port in enumerate(sorted(set(ports))):
            service_name, product, version, category, encrypted = SERVICE_CATALOG[port]
            closed = idx == 3 and j == len(ports) - 1
            risky = port in DB_PORTS or port in MGMT_PORTS
            risk_level = Severity.CRITICAL.value if port in DB_PORTS else Severity.HIGH.value if port in MGMT_PORTS else Severity.MEDIUM.value if port in {8080, 8443} else Severity.LOW.value
            seen = now - timedelta(days=rng.randint(40, 110), hours=rng.randint(0, 20))
            if closed:
                state, last_seen, gone_since, risky, risk_level = ServiceState.CLOSED.value, now - timedelta(days=18), now - timedelta(days=9), False, Severity.INFORMATIONAL.value
            else:
                state, last_seen, gone_since = ServiceState.OPEN.value, now - timedelta(days=rng.randint(0, 3), hours=rng.randint(0, 20)), None
            services.append(ExposedService(company_id=company.id, asset_id=asset.id, ip_address_id=ip_row.id, host=host_by_ip.get(ip_row.address, ip_row.address), port=port, transport="tcp", service_name=service_name, product=product, version=version, operating_system="Windows Server 2022" if port == 3389 else "Ubuntu 22.04 LTS", banner=f"{product}/{version}", state=state, protocol_category=category, is_encrypted=encrypted, is_expected=port in {80, 443, 8443}, is_risky=risky, risk_level=risk_level, recommendation="Confirm the service is decommissioned and remove associated firewall rules." if closed else SERVICE_RECOMMENDATIONS[category], first_seen=seen, last_seen=last_seen, gone_since=gone_since, source=SEED))

    network_ports = [9200] + rng.sample([p for p in PORTS if p != 9200], 3)
    for port in network_ports:
        service_name, product, version, category, encrypted = SERVICE_CATALOG[port]
        risky = port in DB_PORTS or port in MGMT_PORTS
        services.append(ExposedService(company_id=company.id, asset_id=bundle["network"].id, ip_address_id=bundle["ip_rows"][0].id, host=bundle["root_domain"].fqdn, port=port, transport="tcp", service_name=service_name, product=product, version=version, operating_system="Ubuntu 22.04 LTS", banner=f"{product}/{version}", state=ServiceState.OPEN.value, protocol_category=category, is_encrypted=encrypted, is_expected=False, is_risky=risky, risk_level=Severity.CRITICAL.value if port in DB_PORTS else Severity.HIGH.value if port in MGMT_PORTS else Severity.MEDIUM.value, recommendation=SERVICE_RECOMMENDATIONS[category], first_seen=now - timedelta(days=rng.randint(35, 100)), last_seen=now - timedelta(days=rng.randint(0, 3)), source=SEED))

    session.add_all(services)
    await session.flush()
    return services


async def _seed_scans(session: AsyncSession, company: Company, spec: dict[str, Any], authorization_id: str, requester: User, rng: random.Random, now: datetime) -> list[Scan]:
    policy = {
        "max_concurrency": 6,
        "requests_per_second": 3.0,
        "timeout_seconds": 300,
        "allowed_ports": list(PORTS),
        "max_targets_per_run": 250,
        "respect_robots": True,
        "safe_mode": False,
        "business_hours_only": spec["industry"] == Industry.HEALTHCARE.value,
    }
    scans: list[Scan] = []
    for idx, plan in enumerate(SCAN_PLANS):
        queued = plan["status"] == ScanStatus.QUEUED.value
        started = None if queued else now - timedelta(days=plan["days"], hours=rng.randint(0, 5))
        finished = None if queued else started + timedelta(seconds=plan["duration"])
        created = now - timedelta(minutes=12) if queued else started
        scan = Scan(
            company_id=company.id,
            name=plan["name"],
            scan_type=plan["type"],
            status=plan["status"],
            trigger=plan["trigger"],
            requested_by_id=requester.id,
            requested_by_email=requester.email,
            authorization_record_id=authorization_id,
            policy_snapshot=policy,
            targets=[spec["domain"]],
            options={"include_subdomains": True, "ports": list(PORTS) if plan["type"] == ScanType.FULL_RECON.value else []},
            created_at=created,
            updated_at=finished or created,
            started_at=started,
            finished_at=finished,
            duration_seconds=None if queued else plan["duration"],
            job_id=f"demo-{spec['slug']}-{idx + 1}",
            targets_total=plan["total"],
            targets_completed=plan["ok"],
            targets_failed=plan["failed"],
            assets_discovered=plan["found"],
            assets_new=plan["new"],
            assets_changed=plan["changed"],
            assets_removed=0,
            services_found=plan["services"],
            certificates_found=plan["certs"],
            findings_created=plan["findings"],
            changes_detected=plan["changes"],
            result_summary={"mode": "sample", "note": "Seeded demonstration run; this scan produced no network traffic."},
            error_message=plan["error"],
            produced_live_data=False,
        )
        scans.append(scan)
    session.add_all(scans)
    await session.flush()

    for scan in scans:
        base = scan.started_at or scan.created_at
        failed = scan.status == ScanStatus.FAILED.value
        erroring = scan.status == ScanStatus.COMPLETED_WITH_ERRORS.value
        messages = [
            ("info", "scope", "Authorized scope loaded from the approved demonstration record", None),
            ("info", "discover", f"{scan.targets_total} target(s) queued under the tenant scan policy", None),
            ("warn" if erroring else "info", "probe", f"Observed {scan.assets_discovered} assets and {scan.services_found} services in sample data", {"errors": scan.targets_failed}),
            ("error" if failed else "warn" if erroring else "info", "summary", scan.error_message or "Sample run completed; no live data was produced", {"demo": True}),
        ]
        if scan.status == ScanStatus.QUEUED.value:
            messages = [("info", "queue", "Scan queued; waiting for an available worker", None), ("info", "queue", "Authorization and policy snapshot validated", None), ("info", "queue", "Awaiting worker capacity", None)]
        for i, (level, stage, message, detail) in enumerate(messages):
            occurred = base + timedelta(minutes=i * (3 if scan.status == ScanStatus.QUEUED.value else max(1, (scan.duration_seconds or 30) // 4)))
            session.add(ScanEvent(company_id=company.id, scan_id=scan.id, level=level, stage=stage, message=message, detail=detail, occurred_at=occurred, created_at=occurred))
    await session.flush()
    return scans


async def _seed_certificates(session: AsyncSession, company: Company, spec: dict[str, Any], bundle: dict[str, Any], scans: list[Scan], rng: random.Random, now: datetime) -> list[Certificate]:
    tls_scan = next((scan for scan in scans if scan.scan_type == ScanType.TLS_CERTIFICATE.value), scans[0])
    certificates: list[Certificate] = []
    for idx, (kind, days, label) in enumerate(CERT_PLANS[spec["slug"]]):
        host = spec["domain"] if label == "@" else f"{label}.{spec['domain']}"
        domain_row = bundle["domains"].get(host)
        asset_id = domain_row.asset_id if domain_row else bundle["root_domain"].asset_id
        expired = kind == "expired"
        mismatch = kind == "hostname_mismatch"
        self_signed = kind == "self_signed"
        status = CertificateStatus.EXPIRED.value if expired else CertificateStatus.HOSTNAME_MISMATCH.value if mismatch else CertificateStatus.SELF_SIGNED.value if self_signed else CertificateStatus.EXPIRING_SOON.value if days <= 30 else CertificateStatus.VALID.value
        subject_cn = f"legacy.{spec['domain']}" if mismatch else host
        sans = [subject_cn, f"www.{spec['domain']}"] if mismatch else [host]
        if idx == 2:
            sans.append(f"*.{spec['domain']}")
        key_kind = "RSA" if idx % 2 == 0 else "ECDSA"
        serial = _sha(f"serial:{spec['slug']}:{host}:{idx}")[:32].upper()
        certificates.append(Certificate(
            company_id=company.id,
            asset_id=asset_id,
            scan_id=tls_scan.id,
            host=host,
            port=443,
            server_name_indication=host,
            serial_number=serial,
            fingerprint_sha256=_sha(f"fingerprint:{spec['slug']}:{host}:{idx}"),
            subject_common_name=subject_cn,
            subject_organization=company.name,
            issuer_common_name="Self-signed (demo)" if self_signed else "Example Public CA G3",
            issuer_organization=company.name if self_signed else "Example Trust Services",
            issuer_country="US",
            subject_alternative_names=sans,
            san_wildcard=any(value.startswith("*.") for value in sans),
            not_before=now - timedelta(days=400 if expired else rng.choice((90, 365))),
            not_after=now + timedelta(days=days),
            days_remaining=days,
            status=status,
            is_expired=expired,
            is_self_signed=self_signed,
            hostname_matches=not mismatch,
            is_wildcard=any(value.startswith("*.") for value in sans),
            key_algorithm=key_kind,
            key_size=256 if key_kind == "ECDSA" else 2048,
            signature_algorithm="ecdsa-with-SHA256" if key_kind == "ECDSA" else "sha256WithRSAEncryption",
            tls_version="TLSv1.3",
            protocol_version="TLS 1.3",
            certificate_chain_length=1 if self_signed else 3,
            ocsp_url="http://ocsp.example",
            issuer_url="http://ca.example",
            error="Certificate expired" if expired else f"Hostname mismatch for {host}" if mismatch else None,
            source=SEED,
            observed_at=now - timedelta(days=rng.randint(0, 2), hours=rng.randint(0, 23)),
        ))
    session.add_all(certificates)
    await session.flush()
    for cert in certificates:
        domain_row = bundle["domains"].get(cert.host)
        if domain_row is not None:
            domain_row.certificate_id = cert.id
    await session.flush()
    return certificates


async def _seed_vulnerabilities(session: AsyncSession, company: Company, spec: dict[str, Any], cidx: int, bundle: dict[str, Any], services: list[ExposedService], writable: User, rng: random.Random, now: datetime) -> list[Vulnerability]:
    targets = {"api": bundle["api_assets"][0], "www": bundle["sub_assets"][0], "web": bundle["web_assets"][1], "ip": bundle["ip_assets"][0]}
    nginx_service = next((svc for svc in services if svc.product == "nginx" and svc.asset_id == targets["www"].id), None)
    vulnerabilities: list[Vulnerability] = []
    for idx, (cve, title, cvss, vector, exploitability, product, version, fixed, target, ransom, recommendation) in enumerate(VULN_TEMPLATES):
        status = VULN_STATUS_PLANS[cidx][idx]
        resolved = status in {VulnerabilityStatus.FIXED.value, VulnerabilityStatus.ACCEPTED_RISK.value, VulnerabilityStatus.NOT_EXPLOITABLE.value}
        vulnerabilities.append(Vulnerability(
            company_id=company.id,
            asset_id=targets[target].id,
            service_id=nginx_service.id if idx == 1 and nginx_service else None,
            cve_id=cve,
            title=title,
            description=f"{title}. This illustrative record is seeded sample data, not a live vulnerability confirmation.",
            severity=severity_from_cvss(cvss),
            cvss_base_score=cvss,
            cvss_vector=vector,
            exploitability=exploitability,
            in_ransomware_catalog=bool(ransom and cidx == 0),
            modified_at=now - timedelta(days=15),
            affected_product=product,
            affected_version=version,
            fixed_version=fixed,
            references=[f"https://nvd.nist.gov/vuln/detail/{cve}"],
            confidence=Confidence.POTENTIAL.value if cve == "CVE-2023-44487" else Confidence.CONFIRMED.value,
            status=status,
            remediation_note="Patch scheduled with the platform team; verification pending." if resolved else None,
            recommendation=recommendation,
            assignee_id=writable.id,
            discovered_at=now - timedelta(days=(92, 71, 54, 38)[idx]),
            resolved_at=now - timedelta(days=9) if resolved else None,
            due_date=now + timedelta(days=(7, 21, 14, 30)[idx]),
            source=SEED,
            enrichment_source="demo",
        ))
    session.add_all(vulnerabilities)
    await session.flush()
    return vulnerabilities


async def _seed_changes(session: AsyncSession, company: Company, spec: dict[str, Any], bundle: dict[str, Any], certificates: list[Certificate], services: list[ExposedService], scans: list[Scan], writable: User, rng: random.Random, now: datetime) -> list[ConfigurationChange]:
    domain_assets = [bundle["assets"][0]] + bundle["sub_assets"]
    days = sorted(rng.sample(range(1, 46), len(CHANGE_PLANS)), reverse=True)
    changes: list[ConfigurationChange] = []
    for idx, (change_type, severity, suspicious, unplanned, acknowledged) in enumerate(CHANGE_PLANS):
        if idx == 7 and change_type == ChangeType.DNS_RECORD.value:
            asset = next(item for item in bundle["sub_assets"] if item.name.startswith("cdn."))
        elif change_type in {ChangeType.DNS_RECORD.value, ChangeType.IP_MAPPING.value}:
            asset = domain_assets[idx % len(domain_assets)]
        elif change_type == ChangeType.EXPOSED_PORT.value:
            asset = bundle["sub_assets"][3] if unplanned else bundle["network"]
        elif change_type == ChangeType.CERTIFICATE_ROTATION.value:
            asset = bundle["sub_assets"][idx % len(bundle["sub_assets"])]
        elif change_type == ChangeType.NEW_ASSET.value:
            asset = bundle["sub_assets"][13]
        elif change_type == ChangeType.SERVICE_VERSION.value:
            asset = bundle["sub_assets"][0]
        else:
            asset = bundle["active"][idx % len(bundle["active"])]

        if change_type == ChangeType.DNS_RECORD.value:
            old_value = f"203.0.113.{200 + idx}"
            new_value = (bundle["domains"].get(asset.name).resolves_to or bundle["addresses"])[0] if asset.name in bundle["domains"] else bundle["addresses"][idx % 4]
            field = "A"
            summary = f"A record for {asset.name} moved to a different hosting network"
            detail = {"old_asn": "AS13335", "new_asn": spec["asns"][0][0], "old_address": old_value, "new_address": new_value}
        elif change_type == ChangeType.IP_MAPPING.value:
            old_value = bundle["addresses"][(idx + 1) % 4]
            new_value = bundle["addresses"][idx % 4]
            field = "resolves_to"
            summary = f"IP mapping for {asset.name} changed to {new_value}"
            detail = {"provider_before": "Cloudflare", "provider_after": spec["asns"][0][2]}
        elif change_type == ChangeType.EXPOSED_PORT.value:
            port = 3389 if unplanned else 8443
            old_value, new_value, field = "closed", "open", f"tcp/{port}"
            summary = f"New inbound port {port} opened on {asset.name}"
            detail = {"port": port, "transport": "tcp", "expected": False}
        elif change_type == ChangeType.CERTIFICATE_ROTATION.value:
            cert = next((c for c in certificates if c.host == asset.name), certificates[idx % len(certificates)])
            old_value, new_value, field = _sha(f"previous:{spec['slug']}:{asset.name}")[:32].upper(), cert.serial_number, "certificate"
            summary = f"TLS certificate rotated on {asset.name}"
            detail = {"issuer": cert.issuer_organization, "days_remaining": cert.days_remaining}
        elif change_type == ChangeType.ASSET_CONFIGURATION.value:
            old_value, new_value, field = "TLSv1.0,TLSv1.1", "TLSv1.2,TLSv1.3", "tls_policy"
            summary = f"TLS policy tightened on {asset.name}"
            detail = {"previous_policy": ["TLSv1.0", "TLSv1.1"], "current_policy": ["TLSv1.2", "TLSv1.3"]}
        elif change_type == ChangeType.NEW_ASSET.value:
            old_value, new_value, field = None, asset.name, "asset"
            summary = f"New subdomain {asset.name} appeared in certificate transparency"
            detail = {"discovery": "certificate_transparency", "reviewed": False}
        else:
            old_value, new_value, field = "1.24.0", "1.25.3", "nginx"
            summary = f"nginx upgraded on {asset.name} from 1.24.0 to 1.25.3"
            detail = {"previous_version": "1.24.0", "current_version": "1.25.3"}

        occurred = now - timedelta(days=days[idx], hours=rng.randint(0, 20))
        changes.append(ConfigurationChange(
            company_id=company.id,
            asset_id=asset.id,
            scan_id=scans[idx % len(scans)].id,
            domain_id=bundle["domain_asset_ids"].get(asset.id),
            change_type=change_type,
            field=field,
            old_value=old_value,
            new_value=new_value,
            summary=summary,
            severity=severity,
            is_suspicious=suspicious,
            is_expected=not (suspicious or unplanned),
            is_unplanned_exposure=unplanned,
            detail=detail,
            source=SEED,
            occurred_at=occurred,
            acknowledged_at=occurred + timedelta(days=1) if acknowledged else None,
            acknowledged_by_id=writable.id if acknowledged else None,
        ))
    session.add_all(changes)
    await session.flush()
    return changes


async def _seed_findings(session: AsyncSession, company: Company, platform: User, writable: User, bundle: dict[str, Any], vulnerabilities: list[Vulnerability], certificates: list[Certificate], services: list[ExposedService], changes: list[ConfigurationChange], scans: list[Scan], rng: random.Random, now: datetime) -> tuple[list[Finding], list[RemediationTask]]:
    by_type: dict[str, list[Asset]] = {
        AssetType.API_ENDPOINT.value: bundle["api_assets"],
        AssetType.SUBDOMAIN.value: bundle["sub_assets"],
        AssetType.WEB_APPLICATION.value: bundle["web_assets"],
        AssetType.CLOUD_RESOURCE.value: bundle["cloud_assets"],
        AssetType.IP_ADDRESS.value: bundle["ip_assets"],
        AssetType.NETWORK_SERVICE.value: [bundle["network"]],
    }
    risky_service = next((svc for svc in services if svc.is_risky and svc.state == ServiceState.OPEN.value), services[0])
    nginx_service = next((svc for svc in services if svc.product == "nginx" and svc.state == ServiceState.OPEN.value), services[0])
    ssh_service = next((svc for svc in services if svc.port == 22 and svc.state == ServiceState.OPEN.value and svc.asset_id == bundle["ip_assets"][0].id), None)
    service_links = {"risky": risky_service, "nginx": nginx_service, "ssh": ssh_service}
    days = sorted(rng.sample(range(3, 91), len(FINDING_TEMPLATES)), reverse=True)
    findings: list[Finding] = []
    for idx, template in enumerate(FINDING_TEMPLATES):
        candidates = by_type[template["asset"]]
        asset = candidates[template["index"] % len(candidates)]
        assessed = assess_finding(severity=template["severity"], asset_type=asset.asset_type, exposure=asset.exposure, criticality=asset.criticality, confidence=template["confidence"], cvss=template["cvss"], has_known_exploit=bool(template["exploit"]))
        status = template["status"]
        open_like = status in {FindingStatus.OPEN.value, FindingStatus.TRIAGED.value, FindingStatus.ASSIGNED.value, FindingStatus.IN_PROGRESS.value}
        closed_at = None if open_like else now - timedelta(days=5)
        due = None
        sla = False
        if idx in {0, 1, 3, 7, 15}:
            due = now - timedelta(days=5) if idx in {0, 3} else now + timedelta(days=7 if idx == 1 else 14)
            sla = idx in {0, 3}
        finding = Finding(
            company_id=company.id,
            asset_id=asset.id,
            fingerprint=_sha(f"{company.id}|{asset.id}|{template['title']}"),
            finding_type=template["type"],
            title=template["title"],
            description=f"{template['title']} was identified on {asset.name} in seeded demonstration data.",
            evidence=f"Sample evidence for {asset.name}; this row was not produced by a live probe.",
            severity=template["severity"],
            confidence=template["confidence"],
            status=status,
            risk_score=assessed.score,
            score_factors=assessed.factors_dict(),
            cvss_base_score=template["cvss"],
            cvss_vector=None,
            exposure=asset.exposure,
            business_impact="high" if template["severity"] in {Severity.CRITICAL.value, Severity.HIGH.value} else "medium",
            ease_of_remediation="easy" if template["type"] == FindingType.MISCONFIGURATION.value else "moderate",
            recommendation=RECOMMENDATIONS[template["type"]],
            remediation_notes="Work tracked with the owning team; sample data only." if status in {FindingStatus.IN_PROGRESS.value, FindingStatus.REMEDIATED.value, FindingStatus.ACCEPTED_RISK.value} else None,
            assignee_id=writable.id if status in {FindingStatus.ASSIGNED.value, FindingStatus.IN_PROGRESS.value, FindingStatus.TRIAGED.value} else None,
            reporter_id=platform.id,
            triaged_by_id=writable.id if status in {FindingStatus.TRIAGED.value, FindingStatus.ASSIGNED.value, FindingStatus.IN_PROGRESS.value} else None,
            vulnerability_id=vulnerabilities[template["vuln"]].id if template["vuln"] is not None else None,
            service_id=service_links[template["service"]].id if template["service"] and service_links[template["service"]] else None,
            certificate_id=certificates[template["cert"]].id if template["cert"] is not None else None,
            change_id=changes[template["change"]].id if template["change"] is not None else None,
            scan_id=scans[0].id,
            source=SEED,
            discovered_at=now - timedelta(days=days[idx], hours=rng.randint(0, 20)),
            last_verified_at=now - timedelta(days=1) if open_like else None,
            remediated_at=now - timedelta(days=6) if status == FindingStatus.REMEDIATED.value else None,
            closed_at=closed_at,
            due_date=due,
            sla_breached=sla,
            reopen_count=1 if idx == 8 else 0,
        )
        findings.append(finding)
    session.add_all(findings)
    await session.flush()

    tasks: list[RemediationTask] = []
    for template, finding in zip(FINDING_TEMPLATES, findings):
        if not template["task"]:
            continue
        task_status = RemediationStatus.IN_PROGRESS.value if finding.status == FindingStatus.IN_PROGRESS.value else RemediationStatus.VERIFIED.value if finding.status == FindingStatus.REMEDIATED.value else RemediationStatus.OPEN.value
        progress = 100 if finding.status == FindingStatus.REMEDIATED.value else 55 if finding.status == FindingStatus.IN_PROGRESS.value else 15 if finding.status == FindingStatus.TRIAGED.value else 10
        priority = TaskPriority.URGENT.value if finding.severity == Severity.CRITICAL.value else TaskPriority.HIGH.value if finding.severity == Severity.HIGH.value else TaskPriority.MEDIUM.value
        tasks.append(RemediationTask(
            company_id=company.id,
            finding_id=finding.id,
            asset_id=finding.asset_id,
            title=f"Remediate: {finding.title}"[:300],
            description=f"Owner action for finding {finding.id[:8]} ({finding.title}). Seeded demonstration task.",
            priority=priority,
            status=task_status,
            assignee_id=finding.assignee_id or writable.id,
            created_by_id=writable.id,
            due_date=finding.due_date or now + timedelta(days=14),
            completed_at=now - timedelta(days=4) if task_status == RemediationStatus.VERIFIED.value else None,
            verification_note="Verified in the demonstration dataset." if task_status == RemediationStatus.VERIFIED.value else None,
            progress_percent=progress,
        ))
    session.add_all(tasks)
    await session.flush()
    return findings, tasks


async def _seed_asset_events(session: AsyncSession, company: Company, bundle: dict[str, Any], certificates: list[Certificate], findings: list[Finding], changes: list[ConfigurationChange], scans: list[Scan], now: datetime) -> None:
    events: list[AssetEvent] = []
    scan = next((item for item in scans if item.status == ScanStatus.COMPLETED.value), scans[0])
    for idx, asset in enumerate(bundle["assets"]):
        events.append(AssetEvent(company_id=company.id, asset_id=asset.id, event_type=AssetEventType.CREATED.value, summary=f"Asset registered in demonstration data ({asset.asset_type})", detail={"demo": True}, severity=None, source=SEED, occurred_at=asset.first_seen or now, created_at=asset.first_seen or now))
        if asset.status != AssetStatus.RETIRED.value and idx % 2 == 0:
            events.append(AssetEvent(company_id=company.id, asset_id=asset.id, scan_id=scan.id, event_type=AssetEventType.SCAN_OBSERVED.value, summary="Asset observed during a sample discovery run", detail={"demo": True, "produced_live_data": False}, severity=None, source=SEED, occurred_at=asset.last_seen or now, created_at=asset.last_seen or now))
    for cert in certificates:
        events.append(AssetEvent(company_id=company.id, asset_id=cert.asset_id, scan_id=cert.scan_id, event_type=AssetEventType.CERTIFICATE_OBSERVED.value, summary=f"Certificate observed for {cert.host}", detail={"certificate_id": cert.id, "status": cert.status, "demo": True}, severity=Severity.INFORMATIONAL.value, source=SEED, occurred_at=cert.observed_at or now, created_at=cert.observed_at or now))
    for finding in findings:
        events.append(AssetEvent(company_id=company.id, asset_id=finding.asset_id, scan_id=finding.scan_id, event_type=AssetEventType.FINDING_OPENED.value, summary=f"{finding.severity.title()} finding opened: {finding.title}"[:400], detail={"finding_id": finding.id, "finding_type": finding.finding_type, "demo": True}, severity=finding.severity, source=SEED, occurred_at=finding.discovered_at, created_at=finding.discovered_at))
    for change in changes:
        events.append(AssetEvent(company_id=company.id, asset_id=change.asset_id, scan_id=change.scan_id, event_type=AssetEventType.CONFIGURATION_CHANGED.value, summary=change.summary[:400], detail={"change_id": change.id, "change_type": change.change_type, "demo": True}, severity=change.severity, source=SEED, occurred_at=change.occurred_at, created_at=change.occurred_at))
    session.add_all(events)
    await session.flush()


async def _seed_alerts(session: AsyncSession, company: Company, spec: dict[str, Any], bundle: dict[str, Any], findings: list[Finding], certificates: list[Certificate], changes: list[ConfigurationChange], scans: list[Scan], tenant_users: list[User], writable: User, rng: random.Random, now: datetime) -> None:
    active_assets = bundle["active"]
    asset_names = {item.id: item.name for item in active_assets} | {bundle["retired"].id: bundle["retired"].name}
    new_asset = max(active_assets, key=lambda item: item.first_seen or now)
    risky_services = [svc for svc in bundle["services"] if svc.is_risky and svc.state == ServiceState.OPEN.value]
    svc = risky_services[0]
    svc2 = next((item for item in risky_services if item.port in MGMT_PORTS), risky_services[-1])
    critical_findings = [finding for finding in findings if finding.severity == Severity.CRITICAL.value]
    crit = critical_findings[0]
    cert_expired = min(certificates, key=lambda item: item.days_remaining or 0)
    cert_soon = min((item for item in certificates if (item.days_remaining or 0) >= 0), key=lambda item: item.days_remaining or 0)
    suspicious_change = next(item for item in changes if item.is_suspicious)
    unplanned_change = next(item for item in changes if item.is_unplanned_exposure)
    failed_scan = next(item for item in scans if item.status == ScanStatus.FAILED.value)
    risky_finding = next(item for item in findings if item.finding_type == FindingType.RISKY_ENDPOINT.value)
    api_asset = bundle["api_assets"][1]
    days = sorted(rng.sample(range(1, 31), len(ALERT_TEMPLATES)))
    alerts: list[Alert] = []
    for idx, (alert_type, severity, template_status, title_template, message_template, recommendation) in enumerate(ALERT_TEMPLATES):
        expired_days = abs(cert_expired.days_remaining or 0)
        if alert_type == AlertType.CERTIFICATE_EXPIRED.value and not cert_expired.is_expired:
            status = AlertStatus.RESOLVED.value
            title = f"Historical certificate expiry recorded for {cert_expired.host}"
            cert_state = f"within its renewal window ({cert_expired.days_remaining} days remaining)"
        else:
            status = template_status
            title = title_template
            cert_state = f"expired {expired_days} days ago"
        values = {
            "company": company.name,
            "new_asset": new_asset.name,
            "svc_host": svc.host,
            "svc_product": svc.product,
            "svc_version": svc.version,
            "svc_port": svc.port,
            "svc_expectation": "unexpected for this host" if not svc.is_expected else "expected for this host",
            "crit_title": crit.title,
            "crit_asset": asset_names.get(crit.asset_id, "an exposed asset"),
            "crit_score": crit.risk_score,
            "cert_host": cert_expired.host,
            "cert_state": cert_state,
            "soon_host": cert_soon.host,
            "soon_days": cert_soon.days_remaining,
            "change_asset": asset_names.get(suspicious_change.asset_id, suspicious_change.field),
            "change_new": suspicious_change.new_value,
            "change_asn": suspicious_change.detail.get("new_asn", "an unknown ASN"),
            "scan_name": failed_scan.name,
            "scan_failed": failed_scan.targets_completed,
            "scan_total": failed_scan.targets_total,
            "scan_error": failed_scan.error_message,
            "api_url": api_asset.url,
            "api_auth": "no authentication" if spec["unauth_api"] is not None else "an authenticated session",
            "retired_name": bundle["retired"].name,
            "svc2_host": svc2.host,
            "svc2_port": svc2.port,
            "svc2_product": svc2.product,
            "unplanned_asset": next((item.name for item in active_assets if item.id == unplanned_change.asset_id), unplanned_change.field),
        }
        occurred = now - timedelta(days=days[idx], hours=rng.randint(0, 20), minutes=rng.randint(0, 59))
        asset_id = {0: new_asset.id, 1: svc.asset_id, 2: crit.asset_id, 3: cert_expired.asset_id, 4: cert_soon.asset_id, 5: suspicious_change.asset_id, 7: api_asset.id, 8: bundle["retired"].id, 9: svc2.asset_id, 10: unplanned_change.asset_id}.get(idx)
        alert = Alert(
            company_id=company.id,
            alert_type=alert_type,
            severity=severity,
            status=status,
            title=title.format(**values)[:400],
            message=message_template.format(**values),
            recommendation=recommendation,
            dedupe_key=f"{spec['slug']}:{alert_type}:{idx}",
            asset_id=asset_id,
            finding_id=crit.id if idx == 2 else risky_finding.id if idx == 7 else None,
            certificate_id=cert_expired.id if idx == 3 else cert_soon.id if idx == 4 else None,
            change_id=suspicious_change.id if idx == 5 else unplanned_change.id if idx == 10 else None,
            scan_id=failed_scan.id if idx == 6 else None,
            payload={"demo": True, "alert_type": alert_type, "source": "seed"},
            channels=["in_app"],
            source=SEED,
            occurred_at=occurred,
            acknowledged_at=occurred + timedelta(hours=2) if status == AlertStatus.ACKNOWLEDGED.value else None,
            acknowledged_by_id=writable.id if status == AlertStatus.ACKNOWLEDGED.value else None,
            dismissed_reason="Expected certificate rotation was already scheduled." if status == AlertStatus.DISMISSED.value else None,
            resolved_at=occurred + timedelta(hours=8) if status == AlertStatus.RESOLVED.value else None,
            occurrence_count=rng.randint(1, 4),
            last_occurred_at=occurred + timedelta(hours=rng.randint(1, 8)),
        )
        alerts.append(alert)
    session.add_all(alerts)
    await session.flush()

    for alert_index, alert in enumerate(sorted(alerts, key=lambda item: item.occurred_at, reverse=True)[:6]):
        for user_index, user in enumerate(tenant_users):
            read_at = alert.occurred_at + timedelta(hours=5) if (alert_index + user_index) % 2 == 0 else None
            session.add(Notification(user_id=user.id, alert_id=alert.id, company_id=company.id, title=alert.title, message=alert.message, severity=alert.severity, channel="in_app", read_at=read_at, created_at=alert.occurred_at + timedelta(minutes=2)))
    await session.flush()


async def _seed_audit(session: AsyncSession, platform: User, companies: list[Company], writables: dict[str, User], tenant_users: dict[str, list[User]], rng: random.Random, now: datetime) -> None:
    rows: list[AuditLog] = []
    for idx, company in enumerate(companies):
        writer = writables[company.slug]
        actor = tenant_users[company.slug][0]
        plan = [
            (actor, AuditAction.LOGIN.value, "session", "Console sign-in"),
            (writer, AuditAction.ASSET_IMPORTED.value, "asset", "CSV asset import (12 rows)"),
            (writer, AuditAction.SCAN_REQUESTED.value, "scan", "Sample discovery run requested"),
            (platform, AuditAction.AUTHORIZATION_APPROVED.value, "authorization_record", "Root domain authorization approved"),
        ]
        for row_idx, (user, action, object_type, label) in enumerate(plan):
            created = now - timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 20))
            rows.append(AuditLog(company_id=company.id, actor_id=user.id, actor_email=user.email, actor_role=user.role_code, action=action, outcome=AuditOutcome.SUCCESS.value, object_type=object_type, object_id=None, object_label=label, ip_address=f"192.0.2.{20 + idx}", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ASM-Console/1.0", request_id=f"demo-{company.slug}-{row_idx}", detail={"demo": True}, redacted=True, created_at=created, updated_at=created))
    created = now - timedelta(days=1, hours=3)
    rows.append(AuditLog(company_id=None, actor_id=platform.id, actor_email=platform.email, actor_role=platform.role_code, action=AuditAction.LOGIN.value, outcome=AuditOutcome.SUCCESS.value, object_type="session", object_label="Platform console sign-in", ip_address="192.0.2.10", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ASM-Console/1.0", request_id="demo-platform-login", detail={"demo": True}, redacted=True, created_at=created, updated_at=created))
    session.add_all(rows)
    await session.flush()


async def _seed_integrations(session: AsyncSession, platform: User, now: datetime) -> None:
    existing = {row.kind: row for row in (await session.execute(select(Integration).where(Integration.company_id.is_(None)))).scalars().all()}
    for kind, name, status, built_in, verified, capability, description, config in INTEGRATION_SPECS:
        row = existing.get(kind)
        if row is None:
            row = Integration(company_id=None, kind=kind)
            session.add(row)
        row.name = name
        row.status = status
        row.built_in = built_in
        row.verified = verified
        row.enabled = status in {IntegrationStatus.ENABLED.value, IntegrationStatus.READY.value}
        row.capability = capability
        row.description = description
        row.config = config
        row.secret_keys = []
        row.last_run_at = now - timedelta(hours=2) if row.enabled else None
        row.last_error = None
        row.created_by_id = platform.id
    await session.flush()


async def _recompute(session: AsyncSession, companies: list[Company], now: datetime) -> None:
    for company in companies:
        assets = (await session.execute(select(Asset).where(Asset.company_id == company.id))).scalars().all()
        open_findings = (await session.execute(select(Finding).where(Finding.company_id == company.id, Finding.status.in_([FindingStatus.OPEN.value, FindingStatus.TRIAGED.value, FindingStatus.ASSIGNED.value, FindingStatus.IN_PROGRESS.value])))).scalars().all()
        by_asset: dict[str, list[Finding]] = {}
        for finding in open_findings:
            by_asset.setdefault(finding.asset_id, []).append(finding)
        for asset in assets:
            rows = by_asset.get(asset.id, [])
            asset.risk_score = aggregate_asset_risk([row.risk_score for row in rows])
            asset.risk_classification = classify(asset.risk_score)
            asset.open_findings = len(rows)
            asset.critical_findings = sum(1 for row in rows if row.severity == Severity.CRITICAL.value)
            asset.high_findings = sum(1 for row in rows if row.severity == Severity.HIGH.value)
            asset.last_risk_computed_at = now
        active = [asset for asset in assets if asset.status != AssetStatus.RETIRED.value]
        company.risk_score = aggregate_company_risk([asset.risk_score for asset in active])
        company.asset_count = len(active)
    await session.flush()


async def _seed_risk_history(session: AsyncSession, companies: list[Company], rng: random.Random, now: datetime) -> None:
    rows: list[RiskScore] = []
    for company in companies:
        assets = (await session.execute(select(Asset).where(Asset.company_id == company.id))).scalars().all()
        open_findings = (await session.execute(select(Finding).where(Finding.company_id == company.id, Finding.status.in_([FindingStatus.OPEN.value, FindingStatus.TRIAGED.value, FindingStatus.ASSIGNED.value, FindingStatus.IN_PROGRESS.value])))).scalars().all()
        internet_assets = sum(1 for asset in assets if asset.exposure == ExposureClass.INTERNET_FACING.value and asset.status != AssetStatus.RETIRED.value)
        scores = [company.risk_score]
        for _ in range(29):
            scores.append(max(0.0, min(10.0, scores[-1] + rng.uniform(-0.35, 0.35))))
        scores.reverse()
        for offset, score in enumerate(scores):
            day = now - timedelta(days=29 - offset)
            count = sum(1 for finding in open_findings if finding.discovered_at.date() <= day.date())
            critical = sum(1 for finding in open_findings if finding.severity == Severity.CRITICAL.value and finding.discovered_at.date() <= day.date())
            high = sum(1 for finding in open_findings if finding.severity == Severity.HIGH.value and finding.discovered_at.date() <= day.date())
            previous = scores[offset - 1] if offset else max(0.0, min(10.0, score - rng.uniform(-0.2, 0.2)))
            rounded = round(score, 1)
            rows.append(RiskScore(company_id=company.id, scope="company", object_id=company.id, score=rounded, classification=classify(rounded), factors={"finding_pressure": {"label": "Open finding pressure", "weight": 0.5, "contribution": round(count * 0.35, 1)}, "critical_exposure": {"label": "Critical exposure", "weight": 0.3, "contribution": round(critical * 0.9, 1)}, "internet_surface": {"label": "Internet-facing assets", "weight": 0.2, "contribution": round(internet_assets / 10, 1)}}, driver_summary=f"{count} open findings ({critical} critical, {high} high) across {company.asset_count} assets; seeded trend.", finding_count=count, critical_count=critical, high_count=high, model_version=RISK_MODEL_VERSION, computed_at=day, previous_score=round(previous, 1), delta=round(rounded - previous, 1)))
        for asset in assets:
            asset_findings = [finding for finding in open_findings if finding.asset_id == asset.id]
            rows.append(RiskScore(company_id=company.id, scope="asset", object_id=asset.id, asset_id=asset.id, score=asset.risk_score, classification=classify(asset.risk_score), factors={"asset_risk": {"label": "Open finding blend", "weight": 1.0, "contribution": asset.risk_score}}, driver_summary=f"{len(asset_findings)} open findings on {asset.name}; current sample snapshot.", finding_count=len(asset_findings), critical_count=sum(1 for finding in asset_findings if finding.severity == Severity.CRITICAL.value), high_count=sum(1 for finding in asset_findings if finding.severity == Severity.HIGH.value), model_version=RISK_MODEL_VERSION, computed_at=now))
    session.add_all(rows)
    await session.flush()


SAMPLE_LINE = "All seeded rows are labelled source=seed and are sample data, not live scan results."


async def _ensure_roles(session: AsyncSession) -> None:
    existing = {row.code: row for row in (await session.execute(select(Role))).scalars().all()}
    for code, definition in ROLE_DEFINITIONS.items():
        role = existing.get(code)
        if role is None:
            role = Role(code=code)
            session.add(role)
            existing[code] = role
        role.name = definition["name"]
        role.description = definition["description"]
        role.permissions = list(definition["permissions"])
        role.is_system = bool(definition["is_system"])
        role.tenant_scoped = bool(definition["tenant_scoped"])
    await session.flush()


async def _reset_demo(session: AsyncSession) -> int:
    company_ids = list((await session.execute(select(Company.id).where(Company.slug.in_(DEMO_SLUGS)))).scalars().all())
    await session.execute(delete(AuditLog).where(or_(AuditLog.company_id.in_(company_ids), AuditLog.actor_email.in_(DEMO_EMAILS))))
    if company_ids:
        await session.execute(delete(Company).where(Company.id.in_(company_ids)))
    await session.execute(delete(User).where(User.email.in_(DEMO_EMAILS)))
    await session.flush()
    return len(company_ids)


async def _seed(session: AsyncSession, company_count: int, rng: random.Random, now: datetime) -> list[dict[str, Any]]:
    await _ensure_roles(session)
    users: list[User] = []
    for spec in USER_SPECS:
        user = User(
            email=spec["email"],
            full_name=spec["name"],
            job_title=spec["title"],
            hashed_password=hash_password(PASSWORD),
            role_code=spec["role"],
            is_active=spec["active"],
            must_change_password=False,
            last_login_at=now - timedelta(days=rng.randint(0, 5)) if spec["active"] else None,
            avatar_color=spec["color"],
            timezone="UTC",
        )
        session.add(user)
        users.append(user)
    await session.flush()
    platform = users[0]

    specs = COMPANY_SPECS[:company_count]
    companies: list[Company] = []
    company_by_slug: dict[str, Company] = {}
    for spec in specs:
        company = Company(
            name=spec["name"],
            slug=spec["slug"],
            description=spec["description"],
            industry=spec["industry"],
            website=spec["website"],
            status=CompanyStatus.ACTIVE.value,
            contact_email=spec["contact_email"],
            contact_name=spec["contact_name"],
            root_domains=[spec["domain"]],
            tags=list(spec["tags"]),
            is_demo_tenant=True,
        )
        session.add(company)
        companies.append(company)
        company_by_slug[spec["slug"]] = company
    await session.flush()

    membership_roles: dict[tuple[str, str], str] = {}
    for spec, user in zip(USER_SPECS, users):
        for slug, role_code in spec["memberships"]:
            company = company_by_slug.get(slug)
            if company is None:
                continue
            session.add(CompanyMembership(company_id=company.id, user_id=user.id, role_code=role_code, is_active=spec["active"], granted_by_id=platform.id))
            membership_roles[(user.email, slug)] = role_code
    await session.flush()

    session.add(AlertPreference(user_id=platform.id, company_id=None, min_severity=Severity.INFORMATIONAL.value, channels=["in_app", "email"], muted_types=[], daily_digest=True))
    for spec, user in zip(USER_SPECS, users):
        for slug, role_code in spec["memberships"]:
            company = company_by_slug.get(slug)
            if company is None:
                continue
            min_severity = Severity.HIGH.value if role_code == RoleCode.READ_ONLY_AUDITOR.value else Severity.MEDIUM.value if role_code == RoleCode.SECURITY_ANALYST.value else Severity.LOW.value
            session.add(AlertPreference(user_id=user.id, company_id=company.id, min_severity=min_severity, channels=["in_app"], muted_types=["new_asset"] if role_code == RoleCode.READ_ONLY_AUDITOR.value else [], daily_digest=role_code != RoleCode.SECURITY_ANALYST.value))

    tenant_users: dict[str, list[User]] = {spec["slug"]: [] for spec in specs}
    for spec, user in zip(USER_SPECS, users):
        if not spec["active"]:
            continue
        for slug, _ in spec["memberships"]:
            if slug in tenant_users:
                tenant_users[slug].append(user)
    rank = {RoleCode.COMPANY_ADMIN.value: 0, RoleCode.SECURITY_ANALYST.value: 1, RoleCode.READ_ONLY_AUDITOR.value: 2}
    for slug in tenant_users:
        tenant_users[slug].sort(key=lambda user: rank.get(membership_roles.get((user.email, slug), ""), 9))

    for spec in specs:
        company = company_by_slug[spec["slug"]]
        session.add(ScanPolicy(company_id=company.id, max_concurrency=6, requests_per_second=3.0, timeout_seconds=300, allowed_ports=list(PORTS), max_targets_per_run=250, respect_robots=True, safe_mode=False, business_hours_only=spec["industry"] == Industry.HEALTHCARE.value))
    await session.flush()

    authorizations: dict[str, AuthorizationRecord] = {}
    writables: dict[str, User] = {}
    for spec in specs:
        company = company_by_slug[spec["slug"]]
        members = tenant_users[spec["slug"]]
        writable = members[0] if members and membership_roles.get((members[0].email, spec["slug"])) in {RoleCode.COMPANY_ADMIN.value, RoleCode.SECURITY_ANALYST.value} else platform
        writables[spec["slug"]] = writable
        approved = AuthorizationRecord(company_id=company.id, scope_type=AuthorizationScopeType.DOMAIN.value, value=spec["domain"], status=AuthorizationStatus.APPROVED.value, method=VerificationMethod.DNS_TXT.value, evidence=f"Sample DNS TXT token verified for {spec['domain']}; demonstration record only.", notes="Seeded authorization for demo fixtures. No live ownership proof was performed.", verified_at=now - timedelta(days=90), verified_by_id=platform.id, requested_by_id=writable.id, expires_at=now + timedelta(days=275), allow_active_probing=True, max_ports_per_target=100, source="manual")
        pending = AuthorizationRecord(company_id=company.id, scope_type=AuthorizationScopeType.DOMAIN.value, value=spec["pending_scope"], status=AuthorizationStatus.PENDING.value, method=VerificationMethod.DNS_TXT.value, evidence="Awaiting publication of the demo DNS TXT token.", notes="Never scanned: approval is still pending.", requested_by_id=writable.id, allow_active_probing=False, max_ports_per_target=100, source="manual")
        wildcard = AuthorizationRecord(company_id=company.id, scope_type=AuthorizationScopeType.WILDCARD_DOMAIN.value, value=f"*.{spec['domain']}", status=AuthorizationStatus.APPROVED.value, method=VerificationMethod.DNS_TXT.value, evidence=f"Wildcard scope approved for demonstration on {spec['domain']}.", notes="Wildcard approval covers sample subdomains only.", verified_at=now - timedelta(days=60), verified_by_id=platform.id, requested_by_id=writable.id, expires_at=now + timedelta(days=305), allow_active_probing=True, max_ports_per_target=100, source="manual")
        expired = AuthorizationRecord(company_id=company.id, scope_type=AuthorizationScopeType.DOMAIN.value, value=f"legacy.{spec['domain']}", status=AuthorizationStatus.EXPIRED.value, method=VerificationMethod.MANUAL_REVIEW.value, evidence="Historical review record retained for the retired legacy host.", notes="Expired authorization; not valid for new discovery.", verified_at=now - timedelta(days=220), verified_by_id=platform.id, requested_by_id=writable.id, expires_at=now - timedelta(days=40), allow_active_probing=False, max_ports_per_target=100, source="manual")
        session.add_all([approved, pending, wildcard, expired])
        authorizations[spec["slug"]] = approved
    await session.flush()

    for spec in specs:
        company = company_by_slug[spec["slug"]]
        writable = writables[spec["slug"]]
        bundle = await _seed_assets(session, company, spec, COMPANY_SPECS.index(spec), rng, now)
        services = await _seed_services(session, company, bundle, rng, now)
        bundle["services"] = services
        scans = await _seed_scans(session, company, spec, authorizations[spec["slug"]].id, writable, rng, now)
        certificates = await _seed_certificates(session, company, spec, bundle, scans, rng, now)
        vulnerabilities = await _seed_vulnerabilities(session, company, spec, COMPANY_SPECS.index(spec), bundle, services, writable, rng, now)
        changes = await _seed_changes(session, company, spec, bundle, certificates, services, scans, writable, rng, now)
        findings, _ = await _seed_findings(session, company, platform, writable, bundle, vulnerabilities, certificates, services, changes, scans, rng, now)
        await _seed_asset_events(session, company, bundle, certificates, findings, changes, scans, now)
        await _seed_alerts(session, company, spec, bundle, findings, certificates, changes, scans, tenant_users[spec["slug"]], writable, rng, now)

    await _seed_audit(session, platform, companies, writables, tenant_users, rng, now)
    await _seed_integrations(session, platform, now)
    await _recompute(session, companies, now)
    await _seed_risk_history(session, companies, rng, now)
    return await _collect_stats(session, companies)


async def _count(session: AsyncSession, statement: Any) -> int:
    return int((await session.scalar(statement)) or 0)


async def _collect_stats(session: AsyncSession, companies: list[Company]) -> list[dict[str, Any]]:
    open_statuses = [FindingStatus.OPEN.value, FindingStatus.TRIAGED.value, FindingStatus.ASSIGNED.value, FindingStatus.IN_PROGRESS.value]
    stats: list[dict[str, Any]] = []
    for company in companies:
        cid = company.id
        stats.append({
            "company": company.name,
            "assets": await _count(session, select(func.count(Asset.id)).where(Asset.company_id == cid)),
            "findings": await _count(session, select(func.count(Finding.id)).where(Finding.company_id == cid)),
            "open": await _count(session, select(func.count(Finding.id)).where(Finding.company_id == cid, Finding.status.in_(open_statuses))),
            "critical": await _count(session, select(func.count(Finding.id)).where(Finding.company_id == cid, Finding.status.in_(open_statuses), Finding.severity == Severity.CRITICAL.value)),
            "certificates": await _count(session, select(func.count(Certificate.id)).where(Certificate.company_id == cid)),
            "expiring": await _count(session, select(func.count(Certificate.id)).where(Certificate.company_id == cid, Certificate.is_expired.is_(False), Certificate.days_remaining >= 0, Certificate.days_remaining <= 30)),
            "expired": await _count(session, select(func.count(Certificate.id)).where(Certificate.company_id == cid, Certificate.is_expired.is_(True))),
            "alerts": await _count(session, select(func.count(Alert.id)).where(Alert.company_id == cid, Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]))),
        })
    return stats


def _print_summary(stats: list[dict[str, Any]], quiet: bool) -> None:
    if not quiet:
        print("Demo seed summary")
        header = f"{'Company':28} {'Assets':>6} {'Findings':>8} {'Open':>5} {'Critical':>8} {'Certs':>5} {'Expiring':>8} {'Expired':>7} {'Alerts':>6}"
        print(header)
        print("-" * len(header))
        for row in stats:
            print(f"{row['company']:<28} {row['assets']:>6} {row['findings']:>8} {row['open']:>5} {row['critical']:>8} {row['certificates']:>5} {row['expiring']:>8} {row['expired']:>7} {row['alerts']:>6}")
        print()
        print("Demo credentials")
        credentials = f"{'Email':34} {'Role':18} {'Access':58} {'Status':<9} {'Password'}"
        print(credentials)
        print("-" * len(credentials))
        for spec in USER_SPECS:
            status = "active" if spec["active"] else "disabled"
            print(f"{spec['email']:<34} {ROLE_DEFINITIONS[spec['role']]['name']:<18} {spec['scope']:<58} {status:<9} {PASSWORD}")
        print()
    print(SAMPLE_LINE)


async def _run(reset: bool, company_count: int, quiet: bool) -> int:
    rng = random.Random(20261023)
    now = datetime.now(timezone.utc)
    await create_schema()
    try:
        async with session_scope() as session:
            if reset:
                removed = await _reset_demo(session)
                if not quiet:
                    print(f"Removed {removed} demo compan{'y' if removed == 1 else 'ies'}; reseeding.")
            else:
                exists = await session.scalar(select(User.id).where(User.email == USER_SPECS[0]["email"]))
                if exists is not None:
                    if not quiet:
                        print("Demo seed already present; nothing to do.")
                    print(SAMPLE_LINE)
                    return 0
            stats = await _seed(session, company_count, rng, now)
        _print_summary(stats, quiet)
        return 0
    finally:
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed deterministic sample data for the Attack Surface Management demo.")
    parser.add_argument("--reset", action="store_true", help="Delete the known demo tenants and users, then reseed.")
    parser.add_argument("--companies", type=int, default=len(COMPANY_SPECS), help="Number of demo companies to seed (1-3).")
    parser.add_argument("--quiet", action="store_true", help="Suppress the summary tables and keep only the provenance line.")
    args = parser.parse_args()
    if not 1 <= args.companies <= len(COMPANY_SPECS):
        parser.error(f"--companies must be between 1 and {len(COMPANY_SPECS)}")
    try:
        return asyncio.run(_run(reset=args.reset, company_count=args.companies, quiet=args.quiet))
    except Exception as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())




