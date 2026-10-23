"""Role-based access control matrix.

Permissions are declared once here and materialised into the `roles` table by
the migration/seed step, so the UI can render available actions without a
second source of truth in the frontend.

Two axes are enforced independently:
  1. **capability** — does the caller's role include this permission?
  2. **tenancy**   — does the caller belong to the company owning the row?
A request must pass both. Capability checks never substitute for tenancy
checks, which is how multi-tenant products usually leak data.
"""

from __future__ import annotations

from app.models.enums import RoleCode

# --- permission names ------------------------------------------------------
PERMISSIONS: dict[str, str] = {
    "asset:read": "View assets, domains, IPs, services, APIs and cloud resources",
    "asset:write": "Register or edit assets",
    "asset:delete": "Retire or delete assets",
    "asset:import": "Bulk import assets from CSV",
    "discovery:run": "Start an authorized discovery or scan job",
    "scan:read": "View scan configuration and history",
    "certificate:read": "View SSL/TLS certificate monitoring",
    "vulnerability:read": "View vulnerabilities",
    "vulnerability:write": "Create or update vulnerabilities and remediation state",
    "finding:read": "View security findings",
    "finding:write": "Triage, assign and update findings",
    "change:read": "View configuration change history",
    "risk:read": "View risk scores and prioritisation",
    "alert:read": "View alerts and notifications",
    "alert:write": "Acknowledge or dismiss alerts",
    "report:read": "View reports",
    "report:export": "Export CSV/PDF reports",
    "company:read": "View company configuration",
    "company:write": "Create or modify companies and authorization records",
    "authorization:approve": "Approve or reject asset-ownership authorizations",
    "user:read": "View users and roles",
    "user:write": "Create users, grant or revoke company access",
    "integration:read": "View integration configuration",
    "integration:write": "Configure integrations and secrets",
    "settings:write": "Change platform and tenant settings",
    "audit:read": "View audit logs",
    "cross_company:read": "Read across all companies (platform administrators)",
}

_READ_ONLY = [
    "asset:read",
    "certificate:read",
    "vulnerability:read",
    "finding:read",
    "change:read",
    "risk:read",
    "alert:read",
    "report:read",
    "scan:read",
    "company:read",
]

_ANALYST = [
    *_READ_ONLY,
    "asset:write",
    "asset:import",
    "discovery:run",
    "vulnerability:write",
    "finding:write",
    "alert:write",
    "report:export",
]

_COMPANY_ADMIN = [
    *_ANALYST,
    "asset:delete",
    "authorization:approve",
    "user:read",
    "user:write",
    "integration:read",
    "audit:read",
]

_SUPER_ADMIN = [
    *_COMPANY_ADMIN,
    "company:write",
    "integration:write",
    "settings:write",
    "cross_company:read",
]

ROLE_DEFINITIONS: dict[str, dict] = {
    RoleCode.SUPER_ADMIN.value: {
        "name": "Super Admin",
        "description": "Manages the platform, companies, users, integrations and global settings.",
        "permissions": _SUPER_ADMIN,
        "is_system": True,
        "tenant_scoped": False,
    },
    RoleCode.COMPANY_ADMIN.value: {
        "name": "Company Admin",
        "description": "Manages one company's assets, users, scans, alerts and reports.",
        "permissions": _COMPANY_ADMIN,
        "is_system": True,
        "tenant_scoped": True,
    },
    RoleCode.SECURITY_ANALYST.value: {
        "name": "Security Analyst",
        "description": "Investigates assets, reviews findings, assigns remediation and generates reports.",
        "permissions": _ANALYST,
        "is_system": True,
        "tenant_scoped": True,
    },
    RoleCode.READ_ONLY_AUDITOR.value: {
        "name": "Read-Only Auditor",
        "description": "Views dashboards, inventories, findings and reports without modifying data.",
        "permissions": _READ_ONLY,
        "is_system": True,
        "tenant_scoped": True,
    },
}


def permissions_for(role_code: str) -> list[str]:
    return list(ROLE_DEFINITIONS.get(role_code, {}).get("permissions", []))


def is_valid_role(role_code: str) -> bool:
    return role_code in ROLE_DEFINITIONS


def all_permissions() -> dict[str, str]:
    return dict(PERMISSIONS)
