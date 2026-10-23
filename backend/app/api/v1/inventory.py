"""Inventory API: domains, IP addresses, exposed services, API endpoints and cloud resources."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, TenantContext, apply_sort, get_pagination, tenant_dependency
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import ApiEndpoint, Asset, CloudResource, Domain, ExposedService, IPAddress, IPVersion
from app.schemas.asset import ApiEndpointOut, CloudResourceOut, DomainOut, IPOut, ServiceOut
from app.schemas.common import Page
from app.services.presenters import service_out

router = APIRouter(tags=["Inventory"])

DOMAIN_SORTABLE = {
    "fqdn": Domain.fqdn,
    "risk_score": Asset.risk_score,
    "last_seen": Asset.last_seen,
    "source": Domain.source,
}
IP_SORTABLE = {
    "address": IPAddress.address,
    "risk_score": Asset.risk_score,
    "last_seen": Asset.last_seen,
}
SERVICE_SORTABLE = {
    "port": ExposedService.port,
    "risk_level": ExposedService.risk_level,
    "last_seen": ExposedService.last_seen,
}
API_SORTABLE = {
    "url": ApiEndpoint.url,
    "method": ApiEndpoint.method,
    "risk_score": Asset.risk_score,
}
CLOUD_SORTABLE = {
    "provider": CloudResource.provider,
    "risk_score": Asset.risk_score,
}

MANAGEMENT_PORTS = (22, 3389, 5900)


def _domain_row(
    domain: Domain,
    asset_name: str | None,
    risk_score: float | None,
    criticality: str | None,
    last_seen: datetime | None,
) -> DomainOut:
    return DomainOut(
        id=domain.id,
        asset_id=domain.asset_id,
        fqdn=domain.fqdn,
        root_domain=domain.root_domain,
        host_label=domain.host_label,
        is_subdomain=domain.is_subdomain,
        is_wildcard=domain.is_wildcard,
        resolves_to=domain.resolves_to,
        http_status=domain.http_status,
        technologies=domain.technologies,
        source=domain.source,
        asset_name=asset_name,
        risk_score=risk_score if risk_score is not None else 0.0,
        criticality=criticality or "unknown",
        last_seen=last_seen,
    )


def _ip_row(
    ip: IPAddress,
    asset_name: str | None,
    risk_score: float | None,
    last_seen: datetime | None,
    service_count: int,
) -> IPOut:
    return IPOut(
        id=ip.id,
        asset_id=ip.asset_id,
        address=ip.address,
        version=ip.version,
        is_private=ip.is_private,
        asn=ip.asn,
        asn_organization=ip.asn_organization,
        geo_country_name=ip.geo_country_name,
        provider_hint=ip.provider_hint,
        reverse_dns=ip.reverse_dns,
        asset_name=asset_name,
        service_count=service_count,
        risk_score=risk_score if risk_score is not None else 0.0,
        last_seen=last_seen,
    )


def _api_row(endpoint: ApiEndpoint, asset_name: str | None, risk_score: float | None) -> ApiEndpointOut:
    return ApiEndpointOut(
        id=endpoint.id,
        asset_id=endpoint.asset_id,
        url=endpoint.url,
        method=endpoint.method,
        api_format=endpoint.api_format,
        auth_type=endpoint.auth_type,
        requires_auth=endpoint.requires_auth,
        unauthenticated_access=endpoint.unauthenticated_access,
        is_deprecated=endpoint.is_deprecated,
        last_status_code=endpoint.last_status_code,
        asset_name=asset_name,
        risk_score=risk_score if risk_score is not None else 0.0,
    )


def _cloud_row(resource: CloudResource, asset_name: str | None, risk_score: float | None) -> CloudResourceOut:
    return CloudResourceOut(
        id=resource.id,
        asset_id=resource.asset_id,
        provider=resource.provider,
        account_alias=resource.account_alias,
        region=resource.region,
        resource_type=resource.resource_type,
        external_id=resource.external_id,
        public_access=resource.public_access,
        encrypted=resource.encrypted,
        source=resource.source,
        asset_name=asset_name,
        risk_score=risk_score if risk_score is not None else 0.0,
    )


@router.get("/companies/{company_id}/domains", response_model=Page[DomainOut])
async def list_domains(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    is_subdomain: bool | None = None,
    root_domain: str | None = None,
    min_risk: float | None = Query(default=None, ge=0, le=10),
    has_certificate: bool | None = None,
) -> Page[DomainOut]:
    stmt = (
        select(Domain, Asset.name, Asset.risk_score, Asset.criticality, Asset.last_seen)
        .outerjoin(Asset, Domain.asset_id == Asset.id)
        .where(Domain.company_id == ctx.company.id)
    )
    if q:
        stmt = stmt.where(func.lower(Domain.fqdn).like(f"%{q.lower()}%"))
    if is_subdomain is not None:
        stmt = stmt.where(Domain.is_subdomain.is_(is_subdomain))
    if root_domain:
        stmt = stmt.where(func.lower(Domain.root_domain) == root_domain.lower())
    if min_risk is not None:
        stmt = stmt.where(Asset.risk_score >= min_risk)
    if has_certificate is True:
        stmt = stmt.where(Domain.certificate_id.is_not(None))
    elif has_certificate is False:
        stmt = stmt.where(Domain.certificate_id.is_(None))

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = apply_sort(stmt, DOMAIN_SORTABLE, pagination, Asset.risk_score).order_by(Domain.fqdn.asc())
    rows = (await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))).all()
    items = [_domain_row(*row) for row in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/domains/{domain_id}", response_model=DomainOut)
async def domain_detail(
    domain_id: str,
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
) -> DomainOut:
    row = (
        await session.execute(
            select(Domain, Asset.name, Asset.risk_score, Asset.criticality, Asset.last_seen)
            .outerjoin(Asset, Domain.asset_id == Asset.id)
            .where(Domain.id == domain_id, Domain.company_id == ctx.company.id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Domain not found")
    return _domain_row(*row)


@router.get("/companies/{company_id}/ip-addresses", response_model=Page[IPOut])
async def list_ip_addresses(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    version: str | None = None,
    is_private: bool | None = None,
    provider_hint: str | None = None,
    min_risk: float | None = Query(default=None, ge=0, le=10),
) -> Page[IPOut]:
    stmt = (
        select(IPAddress, Asset.name, Asset.risk_score, Asset.last_seen)
        .outerjoin(Asset, IPAddress.asset_id == Asset.id)
        .where(IPAddress.company_id == ctx.company.id)
    )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(IPAddress.address).like(like), func.lower(IPAddress.reverse_dns).like(like))
        )
    if version:
        try:
            parsed_version = IPVersion(version.lower())
        except ValueError:
            stmt = stmt.where(false())
        else:
            stmt = stmt.where(IPAddress.version == parsed_version)
    if is_private is not None:
        stmt = stmt.where(IPAddress.is_private.is_(is_private))
    if provider_hint:
        stmt = stmt.where(func.lower(IPAddress.provider_hint) == provider_hint.lower())
    if min_risk is not None:
        stmt = stmt.where(Asset.risk_score >= min_risk)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = apply_sort(stmt, IP_SORTABLE, pagination, Asset.risk_score)
    rows = (await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))).all()

    asset_ids = [ip.asset_id for ip, *_ in rows]
    service_counts: dict[str, int] = {}
    if asset_ids:
        service_counts = dict(
            (
                await session.execute(
                    select(ExposedService.asset_id, func.count(ExposedService.id))
                    .where(
                        ExposedService.company_id == ctx.company.id,
                        ExposedService.asset_id.in_(asset_ids),
                    )
                    .group_by(ExposedService.asset_id)
                )
            ).all()
        )

    items = [
        _ip_row(ip, asset_name, risk_score, last_seen, service_counts.get(ip.asset_id, 0))
        for ip, asset_name, risk_score, last_seen in rows
    ]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/services", response_model=Page[ServiceOut])
async def list_services(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    port: int | None = Query(default=None, ge=0, le=65535),
    state: str | None = None,
    risky: bool | None = None,
    unexpected: bool | None = None,
    category: str | None = None,
    encrypted: bool | None = None,
) -> Page[ServiceOut]:
    stmt = select(ExposedService).where(ExposedService.company_id == ctx.company.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(ExposedService.service_name).like(like),
                func.lower(ExposedService.product).like(like),
                func.lower(ExposedService.host).like(like),
            )
        )
    if port is not None:
        stmt = stmt.where(ExposedService.port == port)
    if state:
        stmt = stmt.where(func.lower(ExposedService.state) == state.lower())
    if risky is not None:
        stmt = stmt.where(ExposedService.is_risky.is_(risky))
    if unexpected is not None:
        stmt = stmt.where(ExposedService.is_expected.is_(not unexpected))
    if category:
        stmt = stmt.where(func.lower(ExposedService.protocol_category) == category.lower())
    if encrypted is not None:
        stmt = stmt.where(ExposedService.is_encrypted.is_(encrypted))

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = apply_sort(stmt, SERVICE_SORTABLE, pagination, ExposedService.port)
    rows = (await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))).scalars().all()
    return Page.build([service_out(row) for row in rows], total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/services/summary")
async def services_summary(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    management = or_(
        ExposedService.port.in_(MANAGEMENT_PORTS),
        func.lower(ExposedService.protocol_category) == "management",
    )
    counts = (
        await session.execute(
            select(
                func.count(ExposedService.id),
                func.coalesce(func.sum(case((ExposedService.is_risky.is_(True), 1), else_=0)), 0),
                func.coalesce(func.sum(case((ExposedService.is_expected.is_(False), 1), else_=0)), 0),
                func.coalesce(func.sum(case((ExposedService.is_encrypted.is_(False), 1), else_=0)), 0),
                func.coalesce(func.sum(case((management, 1), else_=0)), 0),
            ).where(ExposedService.company_id == ctx.company.id)
        )
    ).one()
    by_category = (
        await session.execute(
            select(ExposedService.protocol_category, func.count(ExposedService.id))
            .where(ExposedService.company_id == ctx.company.id, ExposedService.protocol_category.is_not(None))
            .group_by(ExposedService.protocol_category)
            .order_by(func.count(ExposedService.id).desc(), ExposedService.protocol_category.asc())
        )
    ).all()
    return {
        "total": counts[0],
        "risky": counts[1],
        "unexpected": counts[2],
        "unencrypted": counts[3],
        "management_interfaces": counts[4],
        "by_category": [{"category": category, "count": count} for category, count in by_category],
    }


@router.get("/companies/{company_id}/services/{service_id}", response_model=ServiceOut)
async def service_detail(
    service_id: str,
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
) -> ServiceOut:
    service = (
        await session.execute(
            select(ExposedService).where(
                ExposedService.id == service_id,
                ExposedService.company_id == ctx.company.id,
            )
        )
    ).scalar_one_or_none()
    if service is None:
        raise NotFoundError("Service not found")
    return service_out(service)


@router.get("/companies/{company_id}/api-endpoints", response_model=Page[ApiEndpointOut])
async def list_api_endpoints(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(default=None, max_length=200),
    method: str | None = None,
    api_format: str | None = None,
    requires_auth: bool | None = None,
    unauthenticated: bool | None = None,
    deprecated: bool | None = None,
) -> Page[ApiEndpointOut]:
    stmt = (
        select(ApiEndpoint, Asset.name, Asset.risk_score)
        .outerjoin(Asset, ApiEndpoint.asset_id == Asset.id)
        .where(ApiEndpoint.company_id == ctx.company.id)
    )
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(ApiEndpoint.url).like(like), func.lower(ApiEndpoint.path).like(like))
        )
    if method:
        stmt = stmt.where(func.upper(ApiEndpoint.method) == method.upper())
    if api_format:
        stmt = stmt.where(func.lower(ApiEndpoint.api_format) == api_format.lower())
    if requires_auth is not None:
        stmt = stmt.where(ApiEndpoint.requires_auth.is_(requires_auth))
    if unauthenticated is not None:
        stmt = stmt.where(ApiEndpoint.unauthenticated_access.is_(unauthenticated))
    if deprecated is not None:
        stmt = stmt.where(ApiEndpoint.is_deprecated.is_(deprecated))

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = apply_sort(stmt, API_SORTABLE, pagination, Asset.risk_score)
    rows = (await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))).all()
    items = [_api_row(endpoint, asset_name, risk_score) for endpoint, asset_name, risk_score in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/cloud-resources", response_model=Page[CloudResourceOut])
async def list_cloud_resources(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
    pagination: Pagination = Depends(get_pagination),
    provider: str | None = None,
    public_access: bool | None = None,
    encrypted: bool | None = None,
    resource_type: str | None = None,
    region: str | None = None,
    q: str | None = Query(default=None, max_length=200),
) -> Page[CloudResourceOut]:
    stmt = (
        select(CloudResource, Asset.name, Asset.risk_score)
        .outerjoin(Asset, CloudResource.asset_id == Asset.id)
        .where(CloudResource.company_id == ctx.company.id)
    )
    if provider:
        stmt = stmt.where(func.lower(CloudResource.provider) == provider.lower())
    if public_access is not None:
        stmt = stmt.where(CloudResource.public_access.is_(public_access))
    if encrypted is not None:
        stmt = stmt.where(CloudResource.encrypted.is_(encrypted))
    if resource_type:
        stmt = stmt.where(func.lower(CloudResource.resource_type) == resource_type.lower())
    if region:
        stmt = stmt.where(func.lower(CloudResource.region) == region.lower())
    if q:
        stmt = stmt.where(func.lower(CloudResource.external_id).like(f"%{q.lower()}%"))

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = apply_sort(stmt, CLOUD_SORTABLE, pagination, Asset.risk_score)
    rows = (await session.execute(stmt.offset(pagination.offset).limit(pagination.page_size))).all()
    items = [_cloud_row(resource, asset_name, risk_score) for resource, asset_name, risk_score in rows]
    return Page.build(items, total, pagination.page, pagination.page_size)


@router.get("/companies/{company_id}/cloud-resources/summary")
async def cloud_resources_summary(
    ctx: TenantContext = Depends(tenant_dependency("asset:read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    counts = (
        await session.execute(
            select(
                func.count(CloudResource.id),
                func.coalesce(func.sum(case((CloudResource.public_access.is_(True), 1), else_=0)), 0),
                func.coalesce(func.sum(case((CloudResource.encrypted.is_(False), 1), else_=0)), 0),
                func.coalesce(func.sum(case((CloudResource.logging_enabled.is_(False), 1), else_=0)), 0),
            ).where(CloudResource.company_id == ctx.company.id)
        )
    ).one()
    by_provider = (
        await session.execute(
            select(CloudResource.provider, func.count(CloudResource.id))
            .where(CloudResource.company_id == ctx.company.id)
            .group_by(CloudResource.provider)
            .order_by(func.count(CloudResource.id).desc(), CloudResource.provider.asc())
        )
    ).all()
    by_type = (
        await session.execute(
            select(CloudResource.resource_type, func.count(CloudResource.id))
            .where(CloudResource.company_id == ctx.company.id, CloudResource.resource_type.is_not(None))
            .group_by(CloudResource.resource_type)
            .order_by(func.count(CloudResource.id).desc(), CloudResource.resource_type.asc())
        )
    ).all()
    return {
        "total": counts[0],
        "public": counts[1],
        "unencrypted": counts[2],
        "no_logging": counts[3],
        "by_provider": [
            {"provider": str(getattr(provider, "value", provider)), "count": count}
            for provider, count in by_provider
        ],
        "by_type": [{"type": resource_type, "count": count} for resource_type, count in by_type],
    }
