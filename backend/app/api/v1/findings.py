"""Findings, remediation tasks, CVE vulnerabilities and CSV exports.

Every route is tenant-scoped by `tenant_dependency`, every query carries
`company_id`, and a row belonging to another tenant is reported as 404 rather
than 403 so ids cannot be enumerated across companies.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    AssetEventType,
    AuditAction,
    CompanyMembership,
    Confidence,
    Finding,
    FindingStatus,
    RemediationStatus,
    RemediationTask,
    Report,
    ReportFormat,
    ReportStatus,
    Severity,
    TaskPriority,
    User,
    Vulnerability,
    VulnerabilityStatus,
)
from app.models.enums import OPEN_FINDING_STATUSES, SEVERITY_ORDER
from app.schemas.common import MessageResponse, Page
from app.schemas.finding import (
    FindingNoteRequest,
    FindingOut,
    FindingUpdateRequest,
    RemediationTaskCreateRequest,
    RemediationTaskOut,
    RemediationTaskUpdateRequest,
    VulnerabilityOut,
    VulnerabilityUpdateRequest,
)
from app.services.assets import log_event, recompute_asset_risk, recompute_company_risk
from app.services.presenters import finding_out, task_out, vulnerability_out

router = APIRouter(tags=["Findings & Vulnerabilities"])

#: Higher rank = more severe, so `sort=severity&order=desc` lists critical first.
SEVERITY_RANK = {name: len(SEVERITY_ORDER) - index for index, name in enumerate(SEVERITY_ORDER)}

FINDING_SORTABLE = {
    "risk_score": Finding.risk_score,
    "discovered_at": Finding.discovered_at,
    "severity": case(SEVERITY_RANK, value=Finding.severity, else_=0),
    "due_date": Finding.due_date,
    "status": Finding.status,
}

VULNERABILITY_SORTABLE = {
    "cvss_base_score": Vulnerability.cvss_base_score,
    "discovered_at": Vulnerability.discovered_at,
    "severity": case(SEVERITY_RANK, value=Vulnerability.severity, else_=0),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _checked_enum(value: str, enum_cls, label: str) -> str:
    """Reject unknown enum values on writes instead of persisting a bad string."""
    allowed = {member.value for member in enum_cls}
    if value not in allowed:
        raise ValidationError_(f"Invalid {label} '{value}'", details={"allowed": sorted(allowed)})
    return value


async def _validate_assignee(session: AsyncSession, ctx: TenantContext, user_id: str) -> str:
    """An assignee must be an active member of *this* company, not just any user."""
    membership = (
        await session.execute(
            select(CompanyMembership).where(
                CompanyMembership.company_id == ctx.company.id,
                CompanyMembership.user_id == user_id,
                CompanyMembership.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise ValidationError_("Assignee must be an active member of this company")
    return user_id


async def _load_finding(session: AsyncSession, ctx: TenantContext, finding_id: str) -> Finding:
    finding = (await session.execute(select(Finding).where(Finding.id == finding_id))).scalar_one_or_none()
    if finding is None or finding.company_id != ctx.company.id:
        raise NotFoundError("Finding not found")
    return finding


async def _load_vulnerability(session: AsyncSession, ctx: TenantContext, vulnerability_id: str) -> Vulnerability:
    vulnerability = (
        await session.execute(select(Vulnerability).where(Vulnerability.id == vulnerability_id))
    ).scalar_one_or_none()
    if vulnerability is None or vulnerability.company_id != ctx.company.id:
        raise NotFoundError("Vulnerability not found")
    return vulnerability


async def _names_for_finding(session: AsyncSession, finding: Finding) -> tuple[str | None, str | None]:
    asset_name = (await session.execute(select(Asset.name).where(Asset.id == finding.asset_id))).scalar_one_or_none()
    assignee_name = None
    if finding.assignee_id:
        assignee_name = (
            await session.execute(select(User.full_name).where(User.id == finding.assignee_id))
        ).scalar_one_or_none()
    return asset_name, assignee_name


async def _names_for_vulnerability(session: AsyncSession, vulnerability: Vulnerability) -> tuple[str | None, str | None]:
    asset_name = (
        await session.execute(select(Asset.name).where(Asset.id == vulnerability.asset_id))
    ).scalar_one_or_none()
    assignee_name = None
    if vulnerability.assignee_id:
        assignee_name = (
            await session.execute(select(User.full_name).where(User.id == vulnerability.assignee_id))
        ).scalar_one_or_none()
    return asset_name, assignee_name


async def _finding_response(session: AsyncSession, finding: Finding) -> FindingOut:
    asset_name, assignee_name = await _names_for_finding(session, finding)
    task_count = (
        await session.execute(
            select(func.count()).select_from(RemediationTask).where(RemediationTask.finding_id == finding.id)
        )
    ).scalar_one()
    return finding_out(finding, asset_name=asset_name, assignee_name=assignee_name, task_count=task_count)


async def _load_task(session: AsyncSession, ctx: TenantContext, finding_id: str, task_id: str) -> RemediationTask:
    task = (
        await session.execute(
            select(RemediationTask).where(RemediationTask.id == task_id, RemediationTask.finding_id == finding_id)
        )
    ).scalar_one_or_none()
    if task is None or task.company_id != ctx.company.id:
        raise NotFoundError("Remediation task not found")
    return task


def _finding_stmt(
    ctx: TenantContext,
    *,
    q: str | None = None,
    severity: list[str] | None = None,
    status: str | None = None,
    finding_type: str | None = None,
    confidence: str | None = None,
    assignee_id: str | None = None,
    asset_id: str | None = None,
    source: str | None = None,
    min_risk: float | None = None,
    sla_breached: bool | None = None,
    open_only: bool = False,
):
    stmt = select(Finding).where(Finding.company_id == ctx.company.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Finding.title).like(like), func.lower(Finding.description).like(like)))
    if severity:
        stmt = stmt.where(Finding.severity.in_(severity))
    if status:
        stmt = stmt.where(Finding.status == status)
    if finding_type:
        stmt = stmt.where(Finding.finding_type == finding_type)
    if confidence:
        stmt = stmt.where(Finding.confidence == confidence)
    if assignee_id:
        stmt = stmt.where(Finding.assignee_id == assignee_id)
    if asset_id:
        stmt = stmt.where(Finding.asset_id == asset_id)
    if source:
        stmt = stmt.where(Finding.source == source)
    if min_risk is not None:
        stmt = stmt.where(Finding.risk_score >= min_risk)
    if sla_breached is not None:
        stmt = stmt.where(Finding.sla_breached.is_(sla_breached))
    if open_only:
        stmt = stmt.where(Finding.status.in_(list(OPEN_FINDING_STATUSES)))
    return stmt


def _vulnerability_stmt(
    ctx: TenantContext,
    *,
    q: str | None = None,
    severity: list[str] | None = None,
    status: str | None = None,
    confidence: str | None = None,
    asset_id: str | None = None,
    exploitability: str | None = None,
    ransomware_only: bool = False,
):
    stmt = select(Vulnerability).where(Vulnerability.company_id == ctx.company.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Vulnerability.cve_id).like(like),
                func.lower(Vulnerability.title).like(like),
                func.lower(Vulnerability.affected_product).like(like),
            )
        )
    if severity:
        stmt = stmt.where(Vulnerability.severity.in_(severity))
    if status:
        stmt = stmt.where(Vulnerability.status == status)
    if confidence:
        stmt = stmt.where(Vulnerability.confidence == confidence)
    if asset_id:
        stmt = stmt.where(Vulnerability.asset_id == asset_id)
    if exploitability:
        stmt = stmt.where(Vulnerability.exploitability == exploitability)
    if ransomware_only:
        stmt = stmt.where(Vulnerability.in_ransomware_catalog.is_(True))
    return stmt


def _scope(**values) -> dict:
    """Drop empty filters so a stored report records exactly what was requested."""
    return {key: value for key, value in values.items() if value is not None and value != [] and value is not False}


def _record_report(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    template: str,
    scope: dict,
    row_count: int,
    filename: str,
    now: datetime,
) -> Report:
    report = Report(
        company_id=ctx.company.id,
        name=f"{ctx.company.name} {template.replace('_', ' ')} export",
        template=template,
        format=ReportFormat.CSV.value,
        status=ReportStatus.READY.value,
        scope=scope,
        row_count=row_count,
        artifact_filename=filename,
        generated_by_id=ctx.user.id,
        generated_by_email=ctx.user.email,
        generated_at=now,
        source="manual",
    )
    session.add(report)
    return report


# --- findings --------------------------------------------------------------


@router.get("/companies/{company_id}/findings", response_model=Page[FindingOut])
async def list_findings(
    ctx: TenantContext = Depends(tenant_dependency("finding:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    severity: list[str] | None = Query(default=None),
    status: str | None = None,
    finding_type: str | None = None,
    confidence: str | None = None,
    assignee_id: str | None = None,
    asset_id: str | None = None,
    source: str | None = None,
    min_risk: float | None = Query(default=None, ge=0, le=10),
    sla_breached: bool | None = None,
    open_only: bool = False,
) -> Page[FindingOut]:
    stmt = _finding_stmt(
        ctx,
        q=q,
        severity=severity,
        status=status,
        finding_type=finding_type,
        confidence=confidence,
        assignee_id=assignee_id,
        asset_id=asset_id,
        source=source,
        min_risk=min_risk,
        sla_breached=sla_breached,
        open_only=open_only,
    )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    page_stmt = stmt.add_columns(Asset.name, User.full_name).outerjoin(Asset, Asset.id == Finding.asset_id)
    page_stmt = page_stmt.outerjoin(User, User.id == Finding.assignee_id)
    page_stmt = apply_sort(page_stmt, FINDING_SORTABLE, pagination, Finding.risk_score)
    rows = (
        await session.execute(page_stmt.offset(pagination.offset).limit(pagination.page_size))
    ).all()

    finding_ids = [finding.id for finding, _, _ in rows]
    task_counts: dict[str, int] = {}
    if finding_ids:
        task_counts = dict(
            (
                await session.execute(
                    select(RemediationTask.finding_id, func.count(RemediationTask.id))
                    .where(RemediationTask.finding_id.in_(finding_ids))
                    .group_by(RemediationTask.finding_id)
                )
            ).all()
        )

    items = [
        finding_out(finding, asset_name=asset_name, assignee_name=assignee_name, task_count=task_counts.get(finding.id, 0))
        for finding, asset_name, assignee_name in rows
    ]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/findings/export")
async def export_findings_csv(
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("report:export")),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(default=None, max_length=200),
    severity: list[str] | None = Query(default=None),
    status: str | None = None,
    finding_type: str | None = None,
    confidence: str | None = None,
    assignee_id: str | None = None,
    asset_id: str | None = None,
    source: str | None = None,
    min_risk: float | None = Query(default=None, ge=0, le=10),
    sla_breached: bool | None = None,
    open_only: bool = False,
) -> StreamingResponse:
    meta = get_request_meta(request)
    stmt = _finding_stmt(
        ctx,
        q=q,
        severity=severity,
        status=status,
        finding_type=finding_type,
        confidence=confidence,
        assignee_id=assignee_id,
        asset_id=asset_id,
        source=source,
        min_risk=min_risk,
        sla_breached=sla_breached,
        open_only=open_only,
    )
    stmt = stmt.add_columns(Asset.name, User.full_name).outerjoin(Asset, Asset.id == Finding.asset_id)
    stmt = stmt.outerjoin(User, User.id == Finding.assignee_id).order_by(Finding.risk_score.desc())
    rows = (await session.execute(stmt)).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "title",
            "severity",
            "type",
            "confidence",
            "status",
            "risk_score",
            "asset",
            "assignee",
            "discovered_at",
            "due_date",
            "sla_breached",
            "source",
        ]
    )
    for finding, asset_name, assignee_name in rows:
        writer.writerow(
            [
                finding.title,
                finding.severity,
                finding.finding_type,
                finding.confidence,
                finding.status,
                finding.risk_score,
                asset_name or "",
                assignee_name or "",
                _iso(finding.discovered_at),
                _iso(finding.due_date),
                finding.sla_breached,
                finding.source,
            ]
        )

    now = _utcnow()
    filename = f"{ctx.company.slug}-findings-{now.date().isoformat()}.csv"
    scope = _scope(
        q=q,
        severity=severity,
        status=status,
        finding_type=finding_type,
        confidence=confidence,
        assignee_id=assignee_id,
        asset_id=asset_id,
        source=source,
        min_risk=min_risk,
        sla_breached=sla_breached,
        open_only=open_only,
    )
    report = _record_report(
        session, ctx, template="findings", scope=scope, row_count=len(rows), filename=filename, now=now
    )
    await session.flush()
    await record_audit(
        session,
        action=AuditAction.REPORT_EXPORTED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="report",
        object_id=report.id,
        object_label=report.name,
        detail={"template": "findings", "format": "csv", "rows": len(rows), "scope": scope},
    )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/companies/{company_id}/findings/{finding_id}")
async def finding_detail(
    finding_id: str,
    ctx: TenantContext = Depends(tenant_dependency("finding:read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    finding = await _load_finding(session, ctx, finding_id)
    asset_name, assignee_name = await _names_for_finding(session, finding)
    task_rows = (
        await session.execute(
            select(RemediationTask, User.full_name)
            .outerjoin(User, User.id == RemediationTask.assignee_id)
            .where(RemediationTask.finding_id == finding.id, RemediationTask.company_id == ctx.company.id)
            .order_by(RemediationTask.created_at.asc())
        )
    ).all()
    tasks = [task_out(task, assignee_name=name) for task, name in task_rows]
    return {
        "finding": finding_out(
            finding, asset_name=asset_name, assignee_name=assignee_name, task_count=len(tasks)
        ),
        "tasks": tasks,
    }


@router.patch("/companies/{company_id}/findings/{finding_id}", response_model=FindingOut)
async def update_finding(
    finding_id: str,
    payload: FindingUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("finding:write")),
    session: AsyncSession = Depends(get_session),
) -> FindingOut:
    meta = get_request_meta(request)
    finding = await _load_finding(session, ctx, finding_id)
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.get("status")
    if new_status is not None:
        _checked_enum(new_status, FindingStatus, "finding status")
    if updates.get("severity") is not None:
        _checked_enum(updates["severity"], Severity, "severity")
    if updates.get("assignee_id") is not None:
        await _validate_assignee(session, ctx, updates["assignee_id"])

    old_status = finding.status
    for key in ("recommendation", "remediation_notes", "due_date", "assignee_id"):
        if key in updates:
            setattr(finding, key, updates[key])
    if updates.get("severity") is not None:
        finding.severity = updates["severity"]

    status_changed = new_status is not None and new_status != old_status
    if status_changed:
        finding.status = new_status
        now = _utcnow()
        if new_status == FindingStatus.REMEDIATED.value:
            finding.remediated_at = now
            finding.closed_at = now
        elif new_status in {
            FindingStatus.ACCEPTED_RISK.value,
            FindingStatus.FALSE_POSITIVE.value,
            FindingStatus.DUPLICATE.value,
        }:
            finding.closed_at = now
        elif new_status in {FindingStatus.OPEN.value, FindingStatus.IN_PROGRESS.value}:
            # Reopening: the finding is live work again, so the clock restarts and
            # the old remediation timestamp must not linger.
            finding.reopen_count = (finding.reopen_count or 0) + 1
            finding.closed_at = None
            finding.remediated_at = None

    if status_changed:
        # The status change must reach the database before the roll-up queries run,
        # because the session is configured with autoflush disabled.
        await session.flush()
        asset = await session.get(Asset, finding.asset_id)
        if asset is not None and asset.company_id == ctx.company.id:
            await recompute_asset_risk(session, asset)
            await session.flush()
            await recompute_company_risk(session, ctx.company.id)
            closed = finding.status not in OPEN_FINDING_STATUSES
            log_event(
                session,
                asset,
                AssetEventType.FINDING_CLOSED if closed else AssetEventType.FINDING_OPENED,
                f"Finding {'closed' if closed else 'reopened'}: {finding.title}"[:400],
                severity=finding.severity,
                detail={"finding_id": finding.id, "status": finding.status, "previous_status": old_status},
                actor_id=ctx.user.id,
            )

    await record_audit(
        session,
        action=AuditAction.FINDING_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="finding",
        object_id=finding.id,
        object_label=finding.title,
        detail={
            "fields": sorted(updates),
            "status_from": old_status,
            "status_to": finding.status,
        },
    )
    return await _finding_response(session, finding)


@router.post("/companies/{company_id}/findings/{finding_id}/notes", response_model=FindingOut)
async def add_finding_note(
    finding_id: str,
    payload: FindingNoteRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("finding:write")),
    session: AsyncSession = Depends(get_session),
) -> FindingOut:
    meta = get_request_meta(request)
    finding = await _load_finding(session, ctx, finding_id)
    stamp = _utcnow().strftime("%Y-%m-%d %H:%M UTC")
    author = ctx.user.full_name or ctx.user.email
    line = f"[{stamp}] {author}: {payload.note}"
    existing = (finding.remediation_notes or "").rstrip()
    finding.remediation_notes = f"{existing}\n\n{line}" if existing else line

    await record_audit(
        session,
        action=AuditAction.FINDING_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="finding",
        object_id=finding.id,
        object_label=finding.title,
        detail={"note_added": True},
    )
    return await _finding_response(session, finding)


@router.post(
    "/companies/{company_id}/findings/{finding_id}/tasks",
    response_model=RemediationTaskOut,
    status_code=201,
)
async def create_remediation_task(
    finding_id: str,
    payload: RemediationTaskCreateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("finding:write")),
    session: AsyncSession = Depends(get_session),
) -> RemediationTaskOut:
    meta = get_request_meta(request)
    finding = await _load_finding(session, ctx, finding_id)
    _checked_enum(payload.priority, TaskPriority, "task priority")
    title = payload.title.strip()
    if not title:
        raise ValidationError_("Task title cannot be blank")
    assignee_name = None
    if payload.assignee_id is not None:
        await _validate_assignee(session, ctx, payload.assignee_id)
        assignee_name = (
            await session.execute(select(User.full_name).where(User.id == payload.assignee_id))
        ).scalar_one_or_none()

    task = RemediationTask(
        company_id=ctx.company.id,
        finding_id=finding.id,
        asset_id=finding.asset_id,
        title=title,
        description=payload.description,
        priority=payload.priority,
        status=RemediationStatus.OPEN.value,
        assignee_id=payload.assignee_id,
        created_by_id=ctx.user.id,
        due_date=payload.due_date,
        progress_percent=0,
    )
    session.add(task)
    await session.flush()

    await record_audit(
        session,
        action=AuditAction.FINDING_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="remediation_task",
        object_id=task.id,
        object_label=task.title,
        detail={"finding_id": finding.id, "task_created": True},
    )
    return task_out(task, assignee_name=assignee_name)


@router.patch(
    "/companies/{company_id}/findings/{finding_id}/tasks/{task_id}",
    response_model=RemediationTaskOut,
)
async def update_remediation_task(
    finding_id: str,
    task_id: str,
    payload: RemediationTaskUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("finding:write")),
    session: AsyncSession = Depends(get_session),
) -> RemediationTaskOut:
    meta = get_request_meta(request)
    await _load_finding(session, ctx, finding_id)
    task = await _load_task(session, ctx, finding_id, task_id)
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.get("status")
    if new_status is not None:
        _checked_enum(new_status, RemediationStatus, "task status")
    if updates.get("priority") is not None:
        _checked_enum(updates["priority"], TaskPriority, "task priority")
    if updates.get("assignee_id") is not None:
        await _validate_assignee(session, ctx, updates["assignee_id"])

    old_status = task.status
    for key in ("assignee_id", "verification_note"):
        if key in updates:
            setattr(task, key, updates[key])
    if updates.get("priority") is not None:
        task.priority = updates["priority"]
    if updates.get("progress_percent") is not None:
        task.progress_percent = updates["progress_percent"]

    if new_status is not None:
        task.status = new_status
        if new_status in {RemediationStatus.RESOLVED.value, RemediationStatus.VERIFIED.value}:
            task.completed_at = _utcnow()
            task.progress_percent = 100
        elif old_status in {RemediationStatus.RESOLVED.value, RemediationStatus.VERIFIED.value}:
            task.completed_at = None

    assignee_name = None
    if task.assignee_id:
        assignee_name = (
            await session.execute(select(User.full_name).where(User.id == task.assignee_id))
        ).scalar_one_or_none()

    await record_audit(
        session,
        action=AuditAction.FINDING_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="remediation_task",
        object_id=task.id,
        object_label=task.title,
        detail={"finding_id": finding_id, "fields": sorted(updates), "status_from": old_status, "status_to": task.status},
    )
    return task_out(task, assignee_name=assignee_name)


@router.delete(
    "/companies/{company_id}/findings/{finding_id}/tasks/{task_id}",
    response_model=MessageResponse,
)
async def delete_remediation_task(
    finding_id: str,
    task_id: str,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("finding:write")),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    meta = get_request_meta(request)
    await _load_finding(session, ctx, finding_id)
    task = await _load_task(session, ctx, finding_id, task_id)
    title = task.title
    await session.delete(task)
    await record_audit(
        session,
        action=AuditAction.FINDING_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="remediation_task",
        object_id=task_id,
        object_label=title,
        detail={"finding_id": finding_id, "task_deleted": True},
    )
    return MessageResponse(message="Remediation task deleted")


# --- vulnerabilities -------------------------------------------------------


@router.get("/companies/{company_id}/vulnerabilities", response_model=Page[VulnerabilityOut])
async def list_vulnerabilities(
    ctx: TenantContext = Depends(tenant_dependency("vulnerability:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    severity: list[str] | None = Query(default=None),
    status: str | None = None,
    confidence: str | None = None,
    asset_id: str | None = None,
    exploitability: str | None = None,
    ransomware_only: bool = False,
) -> Page[VulnerabilityOut]:
    stmt = _vulnerability_stmt(
        ctx,
        q=q,
        severity=severity,
        status=status,
        confidence=confidence,
        asset_id=asset_id,
        exploitability=exploitability,
        ransomware_only=ransomware_only,
    )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    page_stmt = stmt.add_columns(Asset.name, User.full_name).outerjoin(Asset, Asset.id == Vulnerability.asset_id)
    page_stmt = page_stmt.outerjoin(User, User.id == Vulnerability.assignee_id)
    page_stmt = apply_sort(page_stmt, VULNERABILITY_SORTABLE, pagination, Vulnerability.cvss_base_score)
    rows = (await session.execute(page_stmt.offset(pagination.offset).limit(pagination.page_size))).all()

    items = [
        vulnerability_out(vulnerability, asset_name=asset_name, assignee_name=assignee_name)
        for vulnerability, asset_name, assignee_name in rows
    ]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/vulnerabilities/export")
async def export_vulnerabilities_csv(
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("report:export")),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(default=None, max_length=200),
    severity: list[str] | None = Query(default=None),
    status: str | None = None,
    confidence: str | None = None,
    asset_id: str | None = None,
    exploitability: str | None = None,
    ransomware_only: bool = False,
) -> StreamingResponse:
    meta = get_request_meta(request)
    stmt = _vulnerability_stmt(
        ctx,
        q=q,
        severity=severity,
        status=status,
        confidence=confidence,
        asset_id=asset_id,
        exploitability=exploitability,
        ransomware_only=ransomware_only,
    )
    stmt = stmt.add_columns(Asset.name).outerjoin(Asset, Asset.id == Vulnerability.asset_id)
    stmt = stmt.order_by(Vulnerability.cvss_base_score.desc())
    rows = (await session.execute(stmt)).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "cve",
            "severity",
            "cvss",
            "confidence",
            "status",
            "asset",
            "product",
            "version",
            "fixed_version",
            "discovered_at",
            "source",
        ]
    )
    for vulnerability, asset_name in rows:
        writer.writerow(
            [
                vulnerability.cve_id,
                vulnerability.severity,
                vulnerability.cvss_base_score if vulnerability.cvss_base_score is not None else "",
                vulnerability.confidence,
                vulnerability.status,
                asset_name or "",
                vulnerability.affected_product or "",
                vulnerability.affected_version or "",
                vulnerability.fixed_version or "",
                _iso(vulnerability.discovered_at),
                vulnerability.source,
            ]
        )

    now = _utcnow()
    filename = f"{ctx.company.slug}-vulnerabilities-{now.date().isoformat()}.csv"
    scope = _scope(
        q=q,
        severity=severity,
        status=status,
        confidence=confidence,
        asset_id=asset_id,
        exploitability=exploitability,
        ransomware_only=ransomware_only,
    )
    report = _record_report(
        session, ctx, template="vulnerabilities", scope=scope, row_count=len(rows), filename=filename, now=now
    )
    await session.flush()
    await record_audit(
        session,
        action=AuditAction.REPORT_EXPORTED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="report",
        object_id=report.id,
        object_label=report.name,
        detail={"template": "vulnerabilities", "format": "csv", "rows": len(rows), "scope": scope},
    )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/companies/{company_id}/vulnerabilities/{vulnerability_id}", response_model=VulnerabilityOut)
async def vulnerability_detail(
    vulnerability_id: str,
    ctx: TenantContext = Depends(tenant_dependency("vulnerability:read")),
    session: AsyncSession = Depends(get_session),
) -> VulnerabilityOut:
    vulnerability = await _load_vulnerability(session, ctx, vulnerability_id)
    asset_name, assignee_name = await _names_for_vulnerability(session, vulnerability)
    return vulnerability_out(vulnerability, asset_name=asset_name, assignee_name=assignee_name)


@router.patch("/companies/{company_id}/vulnerabilities/{vulnerability_id}", response_model=VulnerabilityOut)
async def update_vulnerability(
    vulnerability_id: str,
    payload: VulnerabilityUpdateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("vulnerability:write")),
    session: AsyncSession = Depends(get_session),
) -> VulnerabilityOut:
    meta = get_request_meta(request)
    vulnerability = await _load_vulnerability(session, ctx, vulnerability_id)
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.get("status")
    if new_status is not None:
        _checked_enum(new_status, VulnerabilityStatus, "vulnerability status")
    if updates.get("severity") is not None:
        _checked_enum(updates["severity"], Severity, "severity")
    if updates.get("confidence") is not None:
        _checked_enum(updates["confidence"], Confidence, "confidence")
    if updates.get("assignee_id") is not None:
        await _validate_assignee(session, ctx, updates["assignee_id"])

    old_status = vulnerability.status
    for key in ("assignee_id", "remediation_note", "due_date"):
        if key in updates:
            setattr(vulnerability, key, updates[key])
    if updates.get("severity") is not None:
        vulnerability.severity = updates["severity"]
    if updates.get("confidence") is not None:
        vulnerability.confidence = updates["confidence"]

    if new_status is not None:
        vulnerability.status = new_status
        if new_status == VulnerabilityStatus.FIXED.value:
            if old_status != new_status or vulnerability.resolved_at is None:
                vulnerability.resolved_at = _utcnow()
        else:
            vulnerability.resolved_at = None

    await record_audit(
        session,
        action=AuditAction.VULNERABILITY_UPDATED,
        user=ctx.user,
        company_id=ctx.company.id,
        meta=meta,
        object_type="vulnerability",
        object_id=vulnerability.id,
        object_label=vulnerability.cve_id,
        detail={
            "fields": sorted(updates),
            "status_from": old_status,
            "status_to": vulnerability.status,
        },
    )
    asset_name, assignee_name = await _names_for_vulnerability(session, vulnerability)
    return vulnerability_out(vulnerability, asset_name=asset_name, assignee_name=assignee_name)
