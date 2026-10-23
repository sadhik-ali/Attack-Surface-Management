"""Report catalogue, synchronous CSV generation and the company risk snapshot.

Only CSV is implemented. A PDF request is rejected explicitly rather than
returning a file that claims to be a PDF, and the report catalogue records the
real row count and filter scope of every export.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Pagination,
    TenantContext,
    get_pagination,
    get_request_meta,
    record_audit,
    tenant_dependency,
)
from app.core.errors import NotFoundError, ValidationError_
from app.db.session import get_session
from app.models import (
    Asset,
    AuditAction,
    Certificate,
    Finding,
    Report,
    ReportFormat,
    ReportStatus,
    RiskScore,
    Vulnerability,
)
from app.models.enums import classify
from app.models.risk import RISK_MODEL_VERSION
from app.schemas.common import Page
from app.services.presenters import company_severity_counts

router = APIRouter(tags=["Reports"])

REPORT_TEMPLATES = {"asset_inventory", "findings", "vulnerabilities", "certificates"}


class ReportCreateRequest(BaseModel):
    template: str
    format: str = "csv"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _report_item(report: Report) -> dict:
    return {
        "id": report.id,
        "name": report.name,
        "template": report.template,
        "format": report.format,
        "status": report.status,
        "row_count": report.row_count,
        "artifact_filename": report.artifact_filename,
        "generated_by_email": report.generated_by_email,
        "generated_at": report.generated_at,
    }


async def _load_report(session: AsyncSession, ctx: TenantContext, report_id: str) -> Report:
    report = (await session.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if report is None or report.company_id != ctx.company.id:
        raise NotFoundError("Report not found")
    return report


def _csv_response(buffer: io.StringIO, filename: str) -> StreamingResponse:
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/companies/{company_id}/reports", response_model=Page[dict])
async def list_reports(
    ctx: TenantContext = Depends(tenant_dependency("report:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
) -> Page[dict]:
    stmt = select(Report).where(Report.company_id == ctx.company.id)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Report.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
        )
    ).scalars().all()
    return Page.build([_report_item(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/reports/{report_id}")
async def report_detail(
    report_id: str,
    ctx: TenantContext = Depends(tenant_dependency("report:read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    report = await _load_report(session, ctx, report_id)
    return _report_item(report)


@router.post("/companies/{company_id}/reports")
async def create_report(
    payload: ReportCreateRequest,
    request: Request,
    ctx: TenantContext = Depends(tenant_dependency("report:export")),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    meta = get_request_meta(request)
    template = (payload.template or "").strip().lower()
    report_format = (payload.format or "").strip().lower()

    if report_format == ReportFormat.PDF.value:
        raise ValidationError_("PDF export is not implemented yet; choose CSV")
    if report_format != ReportFormat.CSV.value:
        raise ValidationError_(
            f"Unknown report format '{payload.format}'",
            details={"allowed": [ReportFormat.CSV.value]},
        )
    if template not in REPORT_TEMPLATES:
        raise ValidationError_(
            f"Unknown report template '{payload.template}'",
            details={"allowed": sorted(REPORT_TEMPLATES)},
        )

    now = _utcnow()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    row_count = 0

    if template == "asset_inventory":
        writer.writerow(
            [
                "name",
                "type",
                "status",
                "criticality",
                "exposure",
                "risk_score",
                "open_findings",
                "owner",
                "source",
                "first_seen",
                "last_seen",
            ]
        )
        assets = (
            await session.execute(
                select(Asset).where(Asset.company_id == ctx.company.id).order_by(Asset.risk_score.desc())
            )
        ).scalars().all()
        for asset in assets:
            writer.writerow(
                [
                    asset.name,
                    asset.asset_type,
                    asset.status,
                    asset.criticality,
                    asset.exposure,
                    asset.risk_score,
                    asset.open_findings,
                    asset.owner or "",
                    asset.source,
                    _iso(asset.first_seen),
                    _iso(asset.last_seen),
                ]
            )
        row_count = len(assets)

    elif template == "findings":
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
        rows = (
            await session.execute(
                select(Finding, Asset.name)
                .outerjoin(Asset, Asset.id == Finding.asset_id)
                .where(Finding.company_id == ctx.company.id)
                .order_by(Finding.risk_score.desc())
            )
        ).all()
        for finding, asset_name in rows:
            writer.writerow(
                [
                    finding.title,
                    finding.severity,
                    finding.finding_type,
                    finding.confidence,
                    finding.status,
                    finding.risk_score,
                    asset_name or "",
                    finding.assignee_id or "",
                    _iso(finding.discovered_at),
                    _iso(finding.due_date),
                    finding.sla_breached,
                    finding.source,
                ]
            )
        row_count = len(rows)

    elif template == "vulnerabilities":
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
        rows = (
            await session.execute(
                select(Vulnerability, Asset.name)
                .outerjoin(Asset, Asset.id == Vulnerability.asset_id)
                .where(Vulnerability.company_id == ctx.company.id)
                .order_by(Vulnerability.cvss_base_score.desc())
            )
        ).all()
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
        row_count = len(rows)

    else:  # certificates
        writer.writerow(
            ["host", "port", "status", "issuer", "not_before", "not_after", "days_remaining", "source"]
        )
        certificates = (
            await session.execute(
                select(Certificate)
                .where(Certificate.company_id == ctx.company.id)
                .order_by(Certificate.days_remaining.asc())
            )
        ).scalars().all()
        for certificate in certificates:
            writer.writerow(
                [
                    certificate.host,
                    certificate.port,
                    certificate.status,
                    certificate.issuer_common_name or "",
                    _iso(certificate.not_before),
                    _iso(certificate.not_after),
                    certificate.days_remaining if certificate.days_remaining is not None else "",
                    certificate.source,
                ]
            )
        row_count = len(certificates)

    filename = f"{ctx.company.slug}-{template}-{now.date().isoformat()}.csv"
    scope = {"template": template, "format": report_format}
    report = Report(
        company_id=ctx.company.id,
        name=f"{ctx.company.name} {template.replace('_', ' ')} report",
        template=template,
        format=report_format,
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
        detail={"template": template, "format": report_format, "rows": row_count},
    )
    return _csv_response(buffer, filename)


@router.get("/companies/{company_id}/risk")
async def company_risk(
    ctx: TenantContext = Depends(tenant_dependency("risk:read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    snapshots = (
        await session.execute(
            select(RiskScore)
            .where(RiskScore.company_id == ctx.company.id, RiskScore.scope == "company")
            .order_by(RiskScore.computed_at.desc())
            .limit(2)
        )
    ).scalars().all()
    counts = await company_severity_counts(session, ctx.company.id)

    if not snapshots:
        score = float(ctx.company.risk_score or 0.0)
        return {
            "score": score,
            "classification": classify(score),
            "previous_score": None,
            "delta": None,
            "computed_at": None,
            "model_version": RISK_MODEL_VERSION,
            "factors": [],
            "driver_summary": None,
            "open_findings": sum(counts.values()),
            "severity_counts": counts,
            "note": "No stored company risk snapshot yet; this score was computed on request from the current asset roll-up.",
        }

    current = snapshots[0]
    previous = snapshots[1] if len(snapshots) > 1 else None
    previous_score = current.previous_score
    if previous_score is None and previous is not None:
        previous_score = previous.score
    delta = current.delta
    if delta is None and previous_score is not None:
        delta = round(current.score - previous_score, 1)

    factors = [
        {
            "key": key,
            "label": str(value.get("label", key)),
            "weight": float(value.get("weight", 0)),
            "contribution": float(value.get("contribution", 0)),
        }
        for key, value in (current.factors or {}).items()
        if isinstance(value, dict)
    ]
    return {
        "score": current.score,
        "classification": current.classification,
        "previous_score": previous_score,
        "delta": delta,
        "computed_at": current.computed_at,
        "model_version": current.model_version,
        "factors": factors,
        "driver_summary": current.driver_summary,
        "open_findings": sum(counts.values()),
        "severity_counts": counts,
    }
