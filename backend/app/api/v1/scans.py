"""Authorized discovery: scan capabilities, requests, history and cancellation.

A scan is only accepted when every target resolves to a live, approved
authorization record and the tenant's policy permits the requested checks. The
same gate is re-evaluated per target by the worker, so approval revoked while a
job waits in the queue still stops it.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Pagination,
    RequestMeta,
    TenantContext,
    apply_sort,
    get_pagination,
    get_request_meta,
    record_audit,
    tenant_dependency,
)
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError_
from app.db.session import get_session
from app.discovery.gate import authorize_targets, normalise_target
from app.jobs.runner import enqueue_scan
from app.models import (
    AuditAction,
    AuditOutcome,
    CompanyStatus,
    Scan,
    ScanEvent,
    ScanPolicy,
    ScanStatus,
    ScanType,
)
from app.schemas.common import Page
from app.schemas.scan import ScanCapabilityOut, ScanCreateRequest, ScanDetailOut, ScanEventOut, ScanOut

router = APIRouter(tags=["Discovery"])

UNDERLYING_PROBE_TYPES = {
    ScanType.TLS_CERTIFICATE.value,
    ScanType.HTTP_FINGERPRINT.value,
    ScanType.PORT_EXPOSURE.value,
    ScanType.FULL_RECON.value,
}

SORTABLE = {
    "created_at": Scan.created_at,
    "started_at": Scan.started_at,
    "finished_at": Scan.finished_at,
    "status": Scan.status,
    "scan_type": Scan.scan_type,
}

CAPABILITIES: list[dict] = [
    {
        "scan_type": ScanType.PASSIVE_DNS.value,
        "label": "DNS discovery",
        "description": "Resolves A, AAAA, CNAME, NS, MX and TXT records and records DNS/IP-mapping changes.",
        "implemented": True,
        "required_authorization": True,
        "intrusive": False,
        "availability_note": None,
    },
    {
        "scan_type": ScanType.CERTIFICATE_TRANSPARENCY.value,
        "label": "Certificate transparency",
        "description": "Enumerates subdomains for an authorized domain from public certificate-transparency logs (crt.sh).",
        "implemented": True,
        "required_authorization": True,
        "intrusive": False,
        "availability_note": "Queries the public crt.sh service; results depend on third-party availability.",
    },
    {
        "scan_type": ScanType.TLS_CERTIFICATE.value,
        "label": "TLS certificate probe",
        "description": "Performs a TLS handshake and reads the presented certificate, expiry, SAN coverage and key strength.",
        "implemented": True,
        "required_authorization": True,
        "intrusive": True,
        "availability_note": "Requires an authorization that permits active probing.",
    },
    {
        "scan_type": ScanType.HTTP_FINGERPRINT.value,
        "label": "HTTP fingerprint",
        "description": "Requests the landing page and records status, server headers, title and technologies.",
        "implemented": True,
        "required_authorization": True,
        "intrusive": True,
        "availability_note": "Requires an authorization that permits active probing.",
    },
    {
        "scan_type": ScanType.PORT_EXPOSURE.value,
        "label": "Port exposure check",
        "description": "TCP connect checks against the tenant's allowed port list. No payloads and no version probing.",
        "implemented": True,
        "required_authorization": True,
        "intrusive": True,
        "availability_note": "Only runs when safe mode is disabled and the authorization permits active probing.",
    },
    {
        "scan_type": ScanType.FULL_RECON.value,
        "label": "Full authorized recon",
        "description": "DNS resolution, certificate transparency, TLS, HTTP fingerprinting and the policy's allowed port checks.",
        "implemented": True,
        "required_authorization": True,
        "intrusive": True,
        "availability_note": "Runs every implemented check the tenant policy allows.",
    },
    {
        "scan_type": ScanType.CLOUD_INVENTORY.value,
        "label": "Cloud inventory",
        "description": "Would enumerate cloud provider resources. No cloud provider integration is configured.",
        "implemented": False,
        "required_authorization": False,
        "intrusive": False,
        "availability_note": "Not implemented: cloud accounts cannot be connected yet, so this scan type is rejected rather than simulated.",
    },
]

CAPABILITY_BY_TYPE = {entry["scan_type"]: entry for entry in CAPABILITIES}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _policy(session: AsyncSession, company_id: str) -> ScanPolicy:
    policy = (
        await session.execute(select(ScanPolicy).where(ScanPolicy.company_id == company_id))
    ).scalar_one_or_none()
    if policy is None:
        policy = ScanPolicy(
            company_id=company_id,
            max_concurrency=settings.scan_max_concurrency,
            requests_per_second=settings.scan_requests_per_second,
            allowed_ports=settings.default_scan_ports,
            max_targets_per_run=settings.scan_max_targets_per_run,
        )
        session.add(policy)
        await session.flush()
    return policy


async def _load_scan(session: AsyncSession, company_id: str, scan_id: str) -> Scan:
    scan = (
        await session.execute(select(Scan).where(Scan.id == scan_id, Scan.company_id == company_id))
    ).scalar_one_or_none()
    if scan is None:
        raise NotFoundError("Scan not found")
    return scan


def _scan_detail(scan: Scan, events: list[ScanEvent] | None = None) -> ScanDetailOut:
    base = ScanOut.model_validate(scan)
    return ScanDetailOut(
        **base.model_dump(),
        events=[ScanEventOut.model_validate(event) for event in events or []],
    )


@router.get(
    "/companies/{company_id}/scans/capabilities",
    response_model=list[ScanCapabilityOut],
    summary="List discovery capabilities and their implementation status",
)
async def scan_capabilities(
    ctx: TenantContext = Depends(tenant_dependency("scan:read")),
    session: AsyncSession = Depends(get_session),
) -> list[ScanCapabilityOut]:
    policy = await _policy(session, ctx.company.id)
    capabilities: list[ScanCapabilityOut] = []
    for entry in CAPABILITIES:
        note = entry["availability_note"]
        if settings.discovery_offline and entry["intrusive"]:
            note = "Active probing is globally disabled (ASM_DISCOVERY_OFFLINE=true)."
        elif policy.safe_mode and entry["scan_type"] in {ScanType.PORT_EXPOSURE.value, ScanType.FULL_RECON.value}:
            note = "Port checks are disabled while the tenant scan policy is in safe mode."
        elif policy.safe_mode and entry["intrusive"]:
            note = "Safe mode only suppresses port checks; TLS and HTTP probes still require an authorization that allows active probing."
        capabilities.append(ScanCapabilityOut(**{**entry, "availability_note": note}))
    return capabilities


@router.get("/companies/{company_id}/scans", response_model=Page[ScanOut], summary="List scan history")
async def list_scans(
    ctx: TenantContext = Depends(tenant_dependency("scan:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    status_filter: str | None = None,
    scan_type: str | None = None,
) -> Page[ScanOut]:
    stmt = select(Scan).where(Scan.company_id == ctx.company.id)
    count_stmt = select(func.count()).select_from(Scan).where(Scan.company_id == ctx.company.id)
    if status_filter:
        stmt = stmt.where(Scan.status == status_filter)
        count_stmt = count_stmt.where(Scan.status == status_filter)
    if scan_type:
        stmt = stmt.where(Scan.scan_type == scan_type)
        count_stmt = count_stmt.where(Scan.scan_type == scan_type)
    total = (await session.execute(count_stmt)).scalar_one()
    stmt = apply_sort(stmt, SORTABLE, pagination, Scan.created_at)
    rows = (
        await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))
    ).scalars().all()
    return Page.build([ScanOut.model_validate(row) for row in rows], total, pagination.page, pagination.page_size)


@router.post(
    "/companies/{company_id}/scans",
    response_model=ScanOut,
    status_code=201,
    summary="Request an authorized discovery scan",
)
async def create_scan(
    payload: ScanCreateRequest,
    ctx: TenantContext = Depends(tenant_dependency("discovery:run")),
    session: AsyncSession = Depends(get_session),
    meta: RequestMeta = Depends(get_request_meta),
) -> ScanOut:
    capability = CAPABILITY_BY_TYPE.get(payload.scan_type)
    if capability is None:
        raise ValidationError_("Unknown scan type", details={"allowed": sorted(CAPABILITY_BY_TYPE)})
    if not capability["implemented"]:
        raise ValidationError_(
            "This scan type is not implemented and will not be simulated",
            details={"scan_type": payload.scan_type, "note": capability["availability_note"]},
        )
    if not settings.discovery_enabled:
        raise ValidationError_("Discovery is disabled on this platform (ASM_DISCOVERY_ENABLED=false)")
    if not payload.confirm_authorized:
        raise ValidationError_(
            "You must confirm that the targets are owned or explicitly authorized for assessment",
            details={"field": "confirm_authorized"},
        )
    if ctx.company.status != CompanyStatus.ACTIVE.value:
        raise ConflictError("This company is not active; scans cannot be requested")
    if not payload.targets:
        raise ValidationError_("Provide at least one target")

    policy = await _policy(session, ctx.company.id)
    active = payload.scan_type in UNDERLYING_PROBE_TYPES
    if settings.discovery_offline and active:
        raise ValidationError_("Active probing is globally disabled (ASM_DISCOVERY_OFFLINE=true)")

    if len(payload.targets) > policy.max_targets_per_run:
        raise ValidationError_(
            f"This run lists {len(payload.targets)} targets; the policy limit is {policy.max_targets_per_run}",
            details={"max_targets_per_run": policy.max_targets_per_run},
        )

    expanded_count = 0
    for raw in payload.targets:
        try:
            target, kind = normalise_target(raw)
        except Exception as exc:
            raise ValidationError_(f"Invalid target '{raw}'", details={"reason": getattr(exc, 'message', str(exc))}) from exc
        if kind == "cidr":
            network = ipaddress.ip_network(target, strict=False)
            if network.num_addresses > 64:
                raise ValidationError_(
                    f"{target} expands to {network.num_addresses} addresses; scan at most a /26 per run",
                    details={"target": target},
                )
            expanded_count += max(0, network.num_addresses - 2)
        else:
            expanded_count += 1
    if expanded_count > policy.max_targets_per_run:
        raise ValidationError_(
            f"This run would touch {expanded_count} targets; the policy limit is {policy.max_targets_per_run}",
            details={"max_targets_per_run": policy.max_targets_per_run},
        )

    if payload.ports:
        allowed = {int(port) for port in policy.allowed_ports}
        disallowed = sorted({int(port) for port in payload.ports} - allowed)
        if disallowed:
            raise ValidationError_(
                "Some ports are outside this tenant's allowed scan range",
                details={"disallowed_ports": disallowed[:25], "allowed_ports": sorted(allowed)},
            )
        if policy.safe_mode:
            raise ValidationError_(
                "Port checks are disabled while the tenant scan policy is in safe mode",
                details={"safe_mode": True},
            )
    if payload.scan_type == ScanType.PORT_EXPOSURE.value and policy.safe_mode:
        raise ValidationError_("Port exposure scans require safe mode to be disabled for this company")

    # Legal gate first, scan row second: a refused request must leave no scan
    # artefact that could later be mistaken for a completed run.
    try:
        authorized = await authorize_targets(
            session,
            company_id=ctx.company.id,
            company_root_domains=ctx.company.root_domains or [],
            targets=payload.targets,
            authorization_id=payload.authorization_record_id,
            active_probing=active,
        )
    except Exception as exc:
        await record_audit(
            session,
            action=AuditAction.SCAN_DENIED,
            outcome=AuditOutcome.DENIED,
            user=ctx.user,
            company_id=ctx.company.id,
            meta=meta,
            detail={
                "scan_type": payload.scan_type,
                "targets": payload.targets[:50],
                "reason": getattr(exc, "message", str(exc))[:500],
            },
        )
        await session.commit()
        raise

    targets = [item.target for item in authorized]
    authorization_record_id = payload.authorization_record_id or authorized[0].record.id

    scan = Scan(
        company_id=ctx.company.id,
        name=payload.name or f"{capability['label']} — {_utcnow():%Y-%m-%d %H:%M} UTC",
        scan_type=payload.scan_type,
        status=ScanStatus.QUEUED.value,
        trigger="manual",
        requested_by_id=ctx.user.id,
        requested_by_email=ctx.user.email,
        authorization_record_id=authorization_record_id,
        policy_snapshot={
            "max_concurrency": policy.max_concurrency,
            "requests_per_second": policy.requests_per_second,
            "timeout_seconds": policy.timeout_seconds,
            "allowed_ports": list(policy.allowed_ports),
            "max_targets_per_run": policy.max_targets_per_run,
            "safe_mode": policy.safe_mode,
            "business_hours_only": policy.business_hours_only,
        },
        targets=targets,
        options={
            "include_subdomains": payload.include_subdomains,
            "ports": sorted({int(port) for port in payload.ports}),
        },
    )
    session.add(scan)
    await session.flush()
    await record_audit(
        session,
        action=AuditAction.SCAN_REQUESTED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="scan",
        object_id=scan.id,
        object_label=scan.name,
        detail={
            "scan_type": payload.scan_type,
            "targets": targets[:50],
            "authorization_record_id": authorization_record_id,
            "confirmed_authorized": payload.confirm_authorized,
            "active_probes": active,
        },
    )
    await session.commit()

    try:
        scan.job_id = enqueue_scan(scan.id)
    except Exception as exc:
        scan.status = ScanStatus.FAILED.value
        scan.error_message = str(exc)[:1000]
        scan.finished_at = _utcnow()
        session.add(
            ScanEvent(
                company_id=scan.company_id,
                scan_id=scan.id,
                level="error",
                stage="queue",
                message=str(exc)[:2000],
                occurred_at=_utcnow(),
            )
        )
        await session.commit()
        raise ConflictError(str(exc)) from exc
    await session.commit()
    return ScanOut.model_validate(scan)


@router.get("/companies/{company_id}/scans/{scan_id}", response_model=ScanDetailOut, summary="Scan detail and progress")
async def get_scan(
    scan_id: str,
    ctx: TenantContext = Depends(tenant_dependency("scan:read")),
    session: AsyncSession = Depends(get_session),
) -> ScanDetailOut:
    scan = await _load_scan(session, ctx.company.id, scan_id)
    events = (
        await session.execute(
            select(ScanEvent).where(ScanEvent.scan_id == scan.id).order_by(ScanEvent.occurred_at.asc()).limit(500)
        )
    ).scalars().all()
    return _scan_detail(scan, events)


@router.get("/companies/{company_id}/scans/{scan_id}/events", response_model=Page[ScanEventOut], summary="Scan event log")
async def scan_events(
    scan_id: str,
    ctx: TenantContext = Depends(tenant_dependency("scan:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
) -> Page[ScanEventOut]:
    scan = await _load_scan(session, ctx.company.id, scan_id)
    total = (
        await session.execute(select(func.count()).select_from(ScanEvent).where(ScanEvent.scan_id == scan.id))
    ).scalar_one()
    events = (
        await session.execute(
            select(ScanEvent)
            .where(ScanEvent.scan_id == scan.id)
            .order_by(ScanEvent.occurred_at.asc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).scalars().all()
    return Page.build([ScanEventOut.model_validate(event) for event in events], total, pagination.page, pagination.page_size)


@router.post("/companies/{company_id}/scans/{scan_id}/cancel", response_model=ScanOut, summary="Cancel a queued or running scan")
async def cancel_scan(
    scan_id: str,
    ctx: TenantContext = Depends(tenant_dependency("discovery:run")),
    session: AsyncSession = Depends(get_session),
    meta: RequestMeta = Depends(get_request_meta),
) -> ScanOut:
    scan = await _load_scan(session, ctx.company.id, scan_id)
    if scan.status not in {ScanStatus.QUEUED.value, ScanStatus.RUNNING.value}:
        raise ConflictError(f"This scan is already {scan.status.replace('_', ' ')}")
    previous_status = scan.status
    scan.status = ScanStatus.CANCELLED.value
    await record_audit(
        session,
        action=AuditAction.SCAN_CANCELLED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="scan",
        object_id=scan.id,
        object_label=scan.name,
        detail={"previous_status": previous_status},
    )
    await session.commit()
    await session.refresh(scan)
    return ScanOut.model_validate(scan)
