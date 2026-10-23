"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    assets,
    auth,
    certificates,
    changes,
    companies,
    dashboard,
    findings,
    integrations,
    inventory,
    meta,
    reports,
    scans,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(assets.router)
api_router.include_router(inventory.router)
api_router.include_router(certificates.router)
api_router.include_router(findings.router)
api_router.include_router(changes.router)
api_router.include_router(alerts.router)
api_router.include_router(reports.router)
api_router.include_router(scans.router)
api_router.include_router(dashboard.router)
api_router.include_router(users.router)
api_router.include_router(meta.router)
api_router.include_router(integrations.router)
