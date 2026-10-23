"""Asset inventory API: listing, registration, detail, timeline and CSV import/export."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    Pagination,
    TenantContext,
    apply_sort,
    get_pagination,
    get_request_meta,
    record_audit,
    tenant_dependency,
)
from app.core.errors import NotFoundError, ValidationError_
from app.db.session import get_session
from app.models import (
    Asset,
    AssetEvent,
    AssetEventType,
    AssetStatus,
    AssetType,
    AuditAction,
    Certificate,
    ConfigurationChange,
    Company,
    ExposedService,
    Finding,
    RecordSource,
)
from app.models.enums import OPEN_FINDING_STATUSES
from app.schemas.asset import (
    AssetCreateRequest,
    AssetDetailOut,
    AssetEventOut,
    AssetOut,
    AssetUpdateRequest,
    CsvImportError,
    CsvImportResult,
    DomainDetailOut,
    IPDetailOut,
)
from app.schemas.common import MessageResponse, Page
from app.schemas.finding import FindingOut
from app.services.assets import create_asset, log_event, normalize_identifier, recompute_asset_risk, validate_asset_type
from app.services.presenters import asset_detail_out, asset_out, company_severity_counts, finding_out, service_out

router = APIRouter(tags=["Assets"])

SORTABLE = {
    "name": Asset.name,
    "risk_score": Asset.risk_score,
    "last_seen": Asset.last_seen,
    "first_seen": Asset.first_seen,
    "created_at": Asset.created_at,
    "asset_type": Asset.asset_type,
    "criticality": Asset.criticality,
    "status": Asset.status,
}

CSV_COLUMNS = ["name", "type", "criticality", "exposure", "owner", "environment", "description", "url", "tags"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _load_asset(session: AsyncSession, ctx: TenantContext, asset_id: str) -> Asset:
    asset = (
        await session.execute(
            select(Asset)
            .options(selectinload(Asset.domain), selectinload(Asset.ip), selectinload(Asset.api), selectinload(Asset.cloud))
            .where(Asset.id == asset_id)
        )
    ).scalar_one_or_none()
    if asset is None or asset.company_id != ctx.company.id:
        raise NotFoundError("Asset not found")
    return asset


@router.get("/companies/{company_id}/assets", response_model=Page[AssetOut])
async def list_assets(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    asset_type: str | None = None,
    status: str | None = None,
    criticality: str | None = None,
    exposure: str | None = None,
    source: str | None = None,
    min_risk: float | None = Query(default=None, ge=0, le=10),
    has_findings: bool | None = None,
) -> Page[AssetOut]:
    stmt = select(Asset).where(Asset.company_id == ctx.company.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Asset.name).like(like), func.lower(Asset.owner).like(like)))
    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if status:
        stmt = stmt.where(Asset.status == status)
    if criticality:
        stmt = stmt.where(Asset.criticality == criticality)
    if exposure:
        stmt = stmt.where(Asset.exposure == exposure)
    if source:
        stmt = stmt.where(Asset.source == source)
    if min_risk is not None:
        stmt = stmt.where(Asset.risk_score >= min_risk)
    if has_findings is True:
        stmt = stmt.where(Asset.open_findings > 0)
    elif has_findings is False:
        stmt = stmt.where(Asset.open_findings == 0)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = apply_sort(stmt, SORTABLE, pagination, Asset.risk_score)
    rows = (
        await session.execute(
            stmt.options(selectinload(Asset.domain), selectinload(Asset.ip), selectinload(Asset.api), selectinload(Asset.cloud))
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
    ).scalars().all()

    asset_ids = [a.id for a in rows]
    service_counts: dict[str, int] = {}
    if asset_ids:
        service_counts = dict(
            (
                await session.execute(
                    select(ExposedService.asset_id, func.count(ExposedService.id))
                    .where(ExposedService.asset_id.in_(asset_ids))
                    .group_by(ExposedService.asset_id)
                )
            ).all()
        )

    items = [asset_out(a, service_count=service_counts.get(a.id, 0)) for a in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.post("/companies/{company_id}/assets", response_model=AssetOut, status_code=201)
async def register_asset(
    payload: AssetCreateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("asset:write")),
    session: AsyncSession = Depends(get_session),
) -> AssetOut:
    meta = get_request_meta(request)
    validate_asset_type(payload.asset_type)

    asset = await create_asset(
        session,
        ctx.company,
        name=payload.name,
        asset_type=payload.asset_type,
        source=RecordSource.MANUAL.value,
        criticality=payload.criticality,
        exposure=payload.exposure,
        description=payload.description,
        owner=payload.owner,
        technical_contact=payload.technical_contact,
        environment=payload.environment,
        url=payload.url,
        tags=payload.tags,
        actor_id=ctx.user.id,
    )

    # Type-specific detail rows. A manually registered asset has no observed
    # detail yet, so only the identifiers the user supplied are stored.
    if payload.asset_type in {AssetType.DOMAIN.value, AssetType.SUBDOMAIN.value, AssetType.WEB_APPLICATION.value}:
        from app.models import Domain

        root = payload.name.lower().rstrip(".")
        is_sub = root.count(".") > 1
        session.add(
            Domain(
                company_id=ctx.company.id,
                asset_id=asset.id,
                fqdn=root,
                root_domain=".".join(root.split(".")[-2:]),
                host_label=root.split(".")[0] if is_sub else None,
                is_subdomain=is_sub,
                source=RecordSource.MANUAL.value,
            )
        )
    elif payload.asset_type == AssetType.IP_ADDRESS.value:
        from app.models import IPAddress
        import ipaddress

        try:
            parsed = ipaddress.ip_address(payload.address or payload.name)
        except ValueError as exc:
            raise ValidationError_("Enter a valid IPv4 or IPv6 address") from exc
        session.add(
            IPAddress(
                company_id=ctx.company.id,
                asset_id=asset.id,
                address=str(parsed),
                version="ipv6" if parsed.version == 6 else "ipv4",
                is_private=parsed.is_private,
                source=RecordSource.MANUAL.value,
            )
        )
    elif payload.asset_type == AssetType.API_ENDPOINT.value:
        from app.models import ApiEndpoint
        import hashlib

        url = payload.url or payload.name
        method = (payload.method or "GET").upper()
        session.add(
            ApiEndpoint(
                company_id=ctx.company.id,
                asset_id=asset.id,
                url=url,
                method=method,
                path=payload.path or ("/" + url.split("/", 3)[-1] if "://" in url else url),
                url_hash=hashlib.sha256(f"{method}:{url}".encode()).hexdigest(),
                requires_auth=True,
                source=RecordSource.MANUAL.value,
            )
        )
    elif payload.asset_type == AssetType.CLOUD_RESOURCE.value:
        from app.models import CloudResource

        session.add(
            CloudResource(
                company_id=ctx.company.id,
                asset_id=asset.id,
                provider=payload.provider or "other",
                external_id=payload.external_id or payload.name,
                resource_type=payload.resource_type,
                region=payload.region,
                source=RecordSource.MANUAL.value,
            )
        )

    await record_audit(
        session,
        action=AuditAction.ASSET_CREATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="asset",
        object_id=asset.id,
        object_label=asset.name,
        detail={"asset_type": asset.asset_type},
    )
    await session.flush()
    asset = await _load_asset(session, ctx, asset.id)
    return asset_out(asset)


@router.get("/companies/{company_id}/assets/export")
async def export_assets_csv(
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("report:export")),
    session: AsyncSession = Depends(get_session),
    asset_type: str | None = None,
    risk_min: float | None = Query(default=None, ge=0, le=10),
) -> StreamingResponse:
    meta = get_request_meta(request)
    stmt = select(Asset).where(Asset.company_id == ctx.company.id)
    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if risk_min is not None:
        stmt = stmt.where(Asset.risk_score >= risk_min)
    rows = (await session.execute(stmt.order_by(Asset.risk_score.desc()))).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "name",
            "type",
            "status",
            "criticality",
            "exposure",
            "env",
            "owner",
            "risk_score",
            "risk_class",
            "open_findings",
            "source",
            "first_seen",
            "last_seen",
        ]
    )
    for asset in rows:
        writer.writerow(
            [
                asset.name,
                asset.asset_type,
                asset.status,
                asset.criticality,
                asset.exposure,
                asset.environment or "",
                asset.owner or "",
                asset.risk_score,
                asset.risk_classification or "",
                asset.open_findings,
                asset.source,
                asset.first_seen.isoformat() if asset.first_seen else "",
                asset.last_seen.isoformat() if asset.last_seen else "",
            ]
        )

    await record_audit(
        session,
        action=AuditAction.REPORT_EXPORTED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="report",
        detail={"template": "asset_inventory", "format": "csv", "rows": len(rows)},
    )
    buffer.seek(0)
    filename = f"{ctx.company.slug}-assets-{_utcnow().date().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/companies/{company_id}/assets/{asset_id}", response_model=AssetDetailOut)
async def asset_detail(
    asset_id: str,
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
) -> AssetDetailOut:
    asset = await _load_asset(session, ctx, asset_id)

    services = (
        await session.execute(select(ExposedService).where(ExposedService.asset_id == asset.id).order_by(ExposedService.port))
    ).scalars().all()
    certs = (
        await session.execute(
            select(Certificate).where(Certificate.asset_id == asset.id).order_by(Certificate.not_after.asc().nullslast())
        )
    ).scalars().all()
    events = (
        await session.execute(
            select(AssetEvent).where(AssetEvent.asset_id == asset.id).order_by(AssetEvent.occurred_at.desc()).limit(40)
        )
    ).scalars().all()
    change_count = (
        await session.execute(select(func.count()).select_from(ConfigurationChange).where(ConfigurationChange.asset_id == asset.id))
    ).scalar_one()
    asset_counts = dict(
        (
            await session.execute(
                select(Finding.severity, func.count(Finding.id))
                .where(Finding.asset_id == asset.id, Finding.status.in_(list(OPEN_FINDING_STATUSES)))
                .group_by(Finding.severity)
            )
        ).all()
    )
    return asset_detail_out(
        asset,
        services=services,
        certificates=certs,
        events=events,
        findings_by_severity=asset_counts,
        change_count=change_count,
    )


@router.patch("/companies/{company_id}/assets/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: str,
    payload: AssetUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("asset:write")),
    session: AsyncSession = Depends(get_session),
) -> AssetOut:
    meta = get_request_meta(request)
    asset = await _load_asset(session, ctx, asset_id)
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in {s.value for s in AssetStatus}:
        raise ValidationError_("Invalid asset status")
    changed_fields = []
    for key, value in updates.items():
        if value is not None and getattr(asset, key) != value:
            setattr(asset, key, value)
            changed_fields.append(key)
    if changed_fields:
        log_event(
            session,
            asset,
            AssetEventType.UPDATED,
            f"Asset updated: {', '.join(changed_fields)}",
            source=RecordSource.MANUAL.value,
            detail={"fields": changed_fields},
            actor_id=ctx.user.id,
        )
        await record_audit(
            session,
            action=AuditAction.ASSET_UPDATED,
            user=ctx.user,
            company_id=ctx.company.id,
            meta=meta,
            object_type="asset",
            object_id=asset.id,
            object_label=asset.name,
            detail={"fields": changed_fields},
        )
    return asset_out(asset)


@router.delete("/companies/{company_id}/assets/{asset_id}", response_model=MessageResponse)
async def retire_asset(
    asset_id: str,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("asset:delete")),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    meta = get_request_meta(request)
    asset = await _load_asset(session, ctx, asset_id)
    asset.status = AssetStatus.RETIRED.value
    asset.retired_at = _utcnow()
    log_event(
        session,
        asset,
        AssetEventType.RETIRED,
        "Asset retired from the inventory",
        actor_id=ctx.user.id,
    )
    await record_audit(
        session,
        action=AuditAction.ASSET_DELETED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="asset",
        object_id=asset.id,
        object_label=asset.name,
    )
    return MessageResponse(message="Asset retired. History is retained for audit.")


@router.get("/companies/{company_id}/assets/{asset_id}/timeline", response_model=list[AssetEventOut])
async def asset_timeline(
    asset_id: str,
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AssetEventOut]:
    asset = await _load_asset(session, ctx, asset_id)
    rows = (
        await session.execute(
            select(AssetEvent).where(AssetEvent.asset_id == asset.id).order_by(AssetEvent.occurred_at.desc()).limit(limit)
        )
    ).scalars().all()
    return [AssetEventOut.model_validate(r) for r in rows]


@router.get("/companies/{company_id}/assets/{asset_id}/findings", response_model=list[FindingOut])
async def asset_findings(
    asset_id: str,
    ctx: TenantContext = Depends(tenant_dependency("finding:read")),
    session: AsyncSession = Depends(get_session),
) -> list[FindingOut]:
    asset = await _load_asset(session, ctx, asset_id)
    rows = (
        await session.execute(
            select(Finding).where(Finding.asset_id == asset.id).order_by(Finding.risk_score.desc()).limit(100)
        )
    ).scalars().all()
    return [finding_out(f, asset_name=asset.name) for f in rows]


# --- CSV -------------------------------------------------------------------

MAX_IMPORT_BYTES = 2 * 1024 * 1024


@router.post("/companies/{company_id}/assets/import", response_model=CsvImportResult)
async def import_assets_csv(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = False,
    ctx: TenantContext = Depends(tenant_dependency("asset:import")),
    session: AsyncSession = Depends(get_session),
) -> CsvImportResult:
    meta = get_request_meta(request)
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValidationError_("CSV file is larger than 2 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError_("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError_("CSV file is empty")
    missing = {"name", "type"} - {h.strip().lower() for h in reader.fieldnames}
    if missing:
        raise ValidationError_(
            "CSV is missing required columns",
            details={"missing": sorted(missing), "expected": CSV_COLUMNS},
        )

    created = updated = skipped = 0
    errors: list[CsvImportError] = []
    valid_rows: list[dict] = []

    for index, row in enumerate(reader, start=2):
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        name = clean.get("name", "")
        asset_type = clean.get("type", "").lower()
        if not name:
            errors.append(CsvImportError(row=index, message="Missing asset name"))
            continue
        try:
            validate_asset_type(asset_type)
        except ValidationError_:
            errors.append(CsvImportError(row=index, message=f"Unknown asset type '{asset_type}'"))
            continue
        valid_rows.append({"row": index, **clean})

    for row in valid_rows:
        name = row["name"]
        asset_type = row["type"].lower()
        identifier = normalize_identifier(asset_type, name)
        existing = (
            await session.execute(
                select(Asset).where(Asset.company_id == ctx.company.id, Asset.normalized_identifier == identifier)
            )
        ).scalar_one_or_none()
        if existing:
            if dry_run:
                updated += 1
                continue
            existing.criticality = row.get("criticality") or existing.criticality
            existing.exposure = row.get("exposure") or existing.exposure
            existing.owner = row.get("owner") or existing.owner
            existing.description = row.get("description") or existing.description
            updated += 1
            continue
        if dry_run:
            created += 1
            continue
        try:
            asset = await create_asset(
                session,
                ctx.company,
                name=name,
                asset_type=asset_type,
                source=RecordSource.CSV_IMPORT.value,
                criticality=row.get("criticality") or "unknown",
                exposure=row.get("exposure") or "unknown",
                description=row.get("description") or None,
                owner=row.get("owner") or None,
                environment=row.get("environment") or None,
                url=row.get("url") or None,
                tags=[t.strip() for t in (row.get("tags") or "").split(";") if t.strip()],
                actor_id=ctx.user.id,
            )
            row["_asset_id"] = asset.id
            created += 1
        except ValidationError_ as exc:
            errors.append(CsvImportError(row=row["row"], message=exc.message))
            skipped += 1

    if not dry_run:
        await record_audit(
            session,
            action=AuditAction.ASSET_IMPORTED,
            user=ctx.user,
            company_id=ctx.company.id,
            meta=meta,
            object_type="asset",
            detail={"created": created, "updated": updated, "skipped": skipped, "errors": len(errors)},
        )
    return CsvImportResult(
        total_rows=len(valid_rows) + len(errors),
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors[:50],
        dry_run=dry_run,
    )
