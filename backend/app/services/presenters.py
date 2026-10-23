"""ORM → response-model presenters.

Centralising the mapping keeps routers thin and guarantees every list row gets
the same provenance labelling. Presenters take already-loaded ORM objects and
never trigger lazy loads: in async SQLAlchemy a lazy attribute access inside a
serializer raises MissingGreenlet under load.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.permissions import ROLE_DEFINITIONS
from app.models import (
    Alert,
    Asset,
    Certificate,
    Company,
    CompanyMembership,
    Finding,
    User,
    Vulnerability,
)
from app.schemas.alert import AlertOut
from app.schemas.asset import AssetDetailOut, AssetOut, AssetEventOut, CertificateSummaryOut, ServiceOut
from app.schemas.auth import CompanyAccessOut, MembershipOut, UserOut, UserSummary
from app.schemas.certificate import CertificateOut
from app.schemas.common import provenance_for
from app.schemas.finding import FindingOut, RemediationTaskOut, VulnerabilityOut
from app.schemas.dashboard import ConfigurationChangeOut


def role_name(code: str | None) -> str | None:
    return ROLE_DEFINITIONS.get(code or "", {}).get("name", code)


def user_out(user: User) -> UserOut:
    memberships: list[MembershipOut] = []
    for membership in user.memberships:
        memberships.append(
            MembershipOut(
                company_id=membership.company_id,
                company_name=membership.company.name if membership.company else None,
                company_slug=membership.company.slug if membership.company else None,
                role_code=membership.role_code,
                role_name=role_name(membership.role_code),
                is_active=membership.is_active,
            )
        )
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        job_title=user.job_title,
        role_code=user.role_code,
        role_name=role_name(user.role_code),
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        avatar_color=user.avatar_color,
        timezone=user.timezone,
        memberships=memberships,
        created_at=user.created_at,
    )


def user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_code=user.role_code,
        is_active=user.is_active,
        avatar_color=user.avatar_color,
    )


def company_access(user: User, company: Company) -> CompanyAccessOut:
    return CompanyAccessOut(
        company_id=company.id,
        name=company.name,
        slug=company.slug,
        role_code=user.effective_role_code(company.id) or user.role_code,
        asset_count=company.asset_count,
        risk_score=company.risk_score,
        status=company.status,
    )


def asset_out(asset: Asset, *, service_count: int = 0) -> AssetOut:
    data = AssetOut.model_validate(asset)
    data.provenance = provenance_for(asset.source)
    data.service_count = service_count
    return data


def service_out(service) -> ServiceOut:
    return ServiceOut.model_validate(service)


def certificate_summary(cert: Certificate) -> CertificateSummaryOut:
    return CertificateSummaryOut(
        id=cert.id,
        host=cert.host,
        port=cert.port,
        subject_common_name=cert.subject_common_name,
        issuer_common_name=cert.issuer_common_name,
        issuer_organization=cert.issuer_organization,
        not_after=cert.not_after,
        days_remaining=cert.days_remaining,
        status=cert.status,
        is_expired=cert.is_expired,
        hostname_matches=cert.hostname_matches,
        observed_at=cert.observed_at,
        source=cert.source,
    )


def certificate_out(cert: Certificate, asset_name: str | None = None) -> CertificateOut:
    data = CertificateOut.model_validate(cert)
    data.asset_name = asset_name
    data.expires_label = cert.expires_label
    return data


def asset_detail_out(
    asset: Asset,
    *,
    services: list,
    certificates: list[Certificate],
    events: list,
    findings_by_severity: dict[str, int],
    change_count: int,
) -> AssetDetailOut:
    base = asset_out(asset, service_count=len(services))
    return AssetDetailOut(
        **base.model_dump(),
        services=[service_out(s) for s in services],
        certificates=[certificate_summary(c) for c in certificates],
        findings_by_severity=findings_by_severity,
        events=[AssetEventOut.model_validate(e) for e in events],
        change_count=change_count,
    )


def finding_out(
    finding: Finding,
    *,
    asset_name: str | None = None,
    assignee_name: str | None = None,
    task_count: int = 0,
) -> FindingOut:
    data = FindingOut.model_validate(finding)
    data.asset_name = asset_name
    data.assignee_name = assignee_name
    data.task_count = task_count
    data.provenance = provenance_for(finding.source)
    return data


def vulnerability_out(
    vuln: Vulnerability,
    *,
    asset_name: str | None = None,
    assignee_name: str | None = None,
) -> VulnerabilityOut:
    data = VulnerabilityOut.model_validate(vuln)
    data.asset_name = asset_name
    data.assignee_name = assignee_name
    data.provenance = provenance_for(vuln.source)
    return data


def task_out(task, assignee_name: str | None = None) -> RemediationTaskOut:
    data = RemediationTaskOut.model_validate(task)
    data.assignee_name = assignee_name
    return data


def alert_out(
    alert: Alert,
    *,
    asset_name: str | None = None,
    acknowledged_by_name: str | None = None,
) -> AlertOut:
    data = AlertOut.model_validate(alert)
    data.asset_name = asset_name
    data.acknowledged_by_name = acknowledged_by_name
    return data


def change_out(change, asset_name: str | None = None) -> ConfigurationChangeOut:
    data = ConfigurationChangeOut.model_validate(change)
    data.asset_name = asset_name
    return data


async def company_severity_counts(session, company_id: str) -> dict[str, int]:
    """One grouped query instead of five counts per page render."""
    from app.models import Finding
    from app.models.enums import OPEN_FINDING_STATUSES

    rows = (
        await session.execute(
            select(Finding.severity, func.count(Finding.id))
            .where(Finding.company_id == company_id, Finding.status.in_(list(OPEN_FINDING_STATUSES)))
            .group_by(Finding.severity)
        )
    ).all()
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}
    for severity, count in rows:
        counts[severity] = count
    return counts
