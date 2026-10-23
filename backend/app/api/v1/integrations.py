"""Integration inventory.

The platform ships five working discovery primitives (DNS, certificate
transparency, TLS, HTTP and TCP-connect checks) and no cloud-provider
integration. This endpoint reports exactly that: built-in capabilities are
marked as implemented, cloud providers and webhook delivery are marked as not
implemented rather than presented as configured.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, tenant_dependency
from app.core.config import settings
from app.db.session import get_session
from app.models import Integration, ScanPolicy
from app.schemas.admin import IntegrationOut

router = APIRouter(tags=["Integrations"])

BUILT_INS = [
    {
        "name": "DNS resolution",
        "kind": "dns",
        "capability": "A/AAAA/CNAME/NS/MX/TXT resolution",
        "description": "Recursive DNS queries against the system resolver. No third-party account required.",
    },
    {
        "name": "Certificate transparency (crt.sh)",
        "kind": "certificate_transparency",
        "capability": "Public subdomain enumeration",
        "description": "Read-only queries to the public crt.sh service. Availability depends on crt.sh.",
    },
    {
        "name": "TLS certificate probe",
        "kind": "tls_probe",
        "capability": "Certificate, expiry, SAN and key inspection",
        "description": "A single TLS handshake per authorized host. Requires active-probing authorization.",
    },
    {
        "name": "HTTP fingerprint",
        "kind": "http_probe",
        "capability": "Status, headers, title, technologies",
        "description": "One GET request to the landing page. Requires active-probing authorization.",
    },
    {
        "name": "TCP connect check",
        "kind": "port_scanner",
        "capability": "Bounded port state checks",
        "description": "TCP connect only: no payloads and no service-version probing. Disabled while safe mode is on.",
    },
]

NOT_IMPLEMENTED = [
    {
        "name": "AWS inventory",
        "kind": "cloud_aws",
        "capability": "Cloud resource inventory",
        "description": "No AWS account integration is implemented. Cloud resources shown in demo data are labelled sample rows.",
    },
    {
        "name": "Azure inventory",
        "kind": "cloud_azure",
        "capability": "Cloud resource inventory",
        "description": "No Azure integration is implemented.",
    },
    {
        "name": "GCP inventory",
        "kind": "cloud_gcp",
        "capability": "Cloud resource inventory",
        "description": "No GCP integration is implemented.",
    },
    {
        "name": "Vulnerability feed",
        "kind": "vulnerability_feed",
        "capability": "CVE enrichment",
        "description": "No external vulnerability feed is wired; vulnerabilities are tracked from imported or observed findings only.",
    },
    {
        "name": "Outbound webhooks",
        "kind": "notification_webhook",
        "capability": "Slack / webhook notifications",
        "description": "Notifications are in-app only. Webhook delivery is not implemented.",
    },
]


@router.get("/companies/{company_id}/integrations", response_model=list[IntegrationOut], summary="Integration status")
async def list_integrations(
    ctx: TenantContext = Depends(tenant_dependency("integration:read")),
    session: AsyncSession = Depends(get_session),
) -> list[IntegrationOut]:
    policy = (
        await session.execute(select(ScanPolicy).where(ScanPolicy.company_id == ctx.company.id))
    ).scalar_one_or_none()
    safe_mode = policy.safe_mode if policy else True
    discovery_ready = settings.discovery_enabled and not settings.discovery_offline

    rows = (
        await session.execute(select(Integration).where(Integration.company_id == ctx.company.id))
    ).scalars().all()
    by_kind = {row.kind: row for row in rows}

    output: list[IntegrationOut] = []
    for capability in BUILT_INS:
        stored = by_kind.get(capability["kind"])
        enabled = discovery_ready
        status = "ready" if enabled else "disabled"
        if capability["kind"] == "port_scanner" and safe_mode:
            status = "degraded"
            enabled = False
        if stored is not None and stored.status == "disabled":
            status = "disabled"
            enabled = False
        output.append(
            IntegrationOut(
                id=stored.id if stored else None,
                name=capability["name"],
                kind=capability["kind"],
                status=status,
                built_in=True,
                verified=discovery_ready,
                enabled=enabled,
                capability=capability["capability"],
                description=capability["description"],
                secret_keys=[],
                last_run_at=stored.last_run_at if stored else None,
                last_error=stored.last_error if stored else None,
                implemented=True,
            )
        )

    for capability in NOT_IMPLEMENTED:
        stored = by_kind.get(capability["kind"])
        output.append(
            IntegrationOut(
                id=stored.id if stored else None,
                name=capability["name"],
                kind=capability["kind"],
                status="unconfigured",
                built_in=False,
                verified=False,
                enabled=False,
                capability=capability["capability"],
                description=capability["description"],
                secret_keys=list(stored.secret_keys or []) if stored else [],
                last_run_at=stored.last_run_at if stored else None,
                last_error=stored.last_error if stored else None,
                implemented=False,
            )
        )
    return output
