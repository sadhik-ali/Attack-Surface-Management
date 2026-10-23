"""Company security dashboard aggregation."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, tenant_dependency
from app.db.session import get_session
from app.models import Company, CompanyStatus
from app.schemas.dashboard import DashboardOut
from app.services.dashboard import build_dashboard

router = APIRouter(tags=["Dashboard"])


@router.get("/companies/{company_id}/dashboard", response_model=DashboardOut, summary="Company security dashboard")
async def company_dashboard(
    ctx: TenantContext = Depends(tenant_dependency("risk:read")),
    session: AsyncSession = Depends(get_session),
) -> DashboardOut:
    # Cross-company comparison is a platform-administrator capability; a tenant
    # dashboard must never reveal another company's posture.
    if ctx.user.is_super_admin:
        companies = list(
            (
                await session.execute(
                    select(Company).where(Company.status != CompanyStatus.ARCHIVED.value).order_by(Company.name)
                )
            ).scalars().all()
        )
        include_comparison = len(companies) > 1
    else:
        companies = [ctx.company]
        include_comparison = False
    return await build_dashboard(
        session,
        company=ctx.company,
        accessible_companies=companies,
        include_comparison=include_comparison,
    )
