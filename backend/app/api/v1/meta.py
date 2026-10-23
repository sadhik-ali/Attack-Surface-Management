"""Metadata for the UI: roles, permissions, enum vocabularies and platform settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_platform_admin
from app.core.config import settings
from app.core.permissions import PERMISSIONS, ROLE_DEFINITIONS
from app.models import User
from app.models.enums import (
    AlertStatus,
    AlertType,
    AssetStatus,
    AssetType,
    CertificateStatus,
    ChangeType,
    CriticalityTier,
    ExposureClass,
    FindingStatus,
    FindingType,
    RecordSource,
    RemediationStatus,
    ScanStatus,
    ScanType,
    Severity,
    VulnerabilityStatus,
)
from app.schemas.admin import EnumMetaOut, PlatformSettingsOut, RetentionOut
from app.schemas.common import EnumOption

router = APIRouter(tags=["Metadata"])


def _options(enum_cls) -> list[EnumOption]:
    return [EnumOption(value=member.value, label=member.value.replace("_", " ").title()) for member in enum_cls]


@router.get("/meta/roles", summary="Role definitions and their permissions")
async def list_roles(_user: User = Depends(get_current_user)) -> list[dict]:
    return [
        {
            "code": code,
            "name": definition["name"],
            "description": definition["description"],
            "permissions": definition["permissions"],
            "is_system": definition["is_system"],
            "tenant_scoped": definition["tenant_scoped"],
        }
        for code, definition in ROLE_DEFINITIONS.items()
    ]


@router.get("/meta/permissions", summary="Permission catalogue")
async def list_permissions(user: User = Depends(require_platform_admin)) -> list[dict]:
    return [{"code": code, "description": description} for code, description in PERMISSIONS.items()]


@router.get("/meta/enums", response_model=EnumMetaOut, summary="Enum vocabularies used by filters and forms")
async def enums(_user: User = Depends(get_current_user)) -> EnumMetaOut:
    return EnumMetaOut(
        asset_types=_options(AssetType),
        asset_statuses=_options(AssetStatus),
        criticalities=_options(CriticalityTier),
        exposures=_options(ExposureClass),
        severities=_options(Severity),
        finding_types=_options(FindingType),
        finding_statuses=_options(FindingStatus),
        vulnerability_statuses=_options(VulnerabilityStatus),
        certificate_statuses=_options(CertificateStatus),
        change_types=_options(ChangeType),
        scan_types=_options(ScanType),
        scan_statuses=_options(ScanStatus),
        alert_types=_options(AlertType),
        alert_statuses=_options(AlertStatus),
        sources=_options(RecordSource),
        remediation_statuses=_options(RemediationStatus),
    )


@router.get("/meta/settings", response_model=PlatformSettingsOut, summary="Platform configuration (no secrets)")
async def platform_settings(_admin: User = Depends(require_platform_admin)) -> PlatformSettingsOut:
    return PlatformSettingsOut(
        app_name=settings.app_name,
        app_env=settings.app_env,
        api_prefix=settings.api_prefix,
        discovery_enabled=settings.discovery_enabled,
        discovery_offline=settings.discovery_offline,
        job_backend=settings.job_backend,
        demo_mode=settings.demo_mode,
        certificate_expiry_warning_days=settings.certificate_expiry_warning_days,
        certificate_expiry_critical_days=settings.certificate_expiry_critical_days,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_requests_per_minute=settings.rate_limit_requests_per_minute,
        retention=RetentionOut(
            scan_result_retention_days=settings.scan_result_retention_days,
            audit_log_retention_days=settings.audit_log_retention_days,
        ),
        supported_integrations=["dns", "certificate_transparency", "tls_probe", "http_probe", "port_scanner"],
    )
