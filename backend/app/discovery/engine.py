"""Authorized discovery engine.

Execution model:
  * targets are processed sequentially, with network calls for one target run
    concurrently. The database session is never shared across concurrent
    tasks, which async SQLAlchemy does not support.
  * every target is re-authorized immediately before it is touched;
  * per-target failures are recorded and the scan continues;
  * the run is bounded by the tenant's scan policy and the global settings.

What is genuinely measured: DNS records, TLS certificates, HTTP headers/titles,
subdomains from public certificate-transparency logs, and (only when the policy
has safe_mode disabled and the authorization allows active probing) TCP connect
state for a bounded port list. Nothing is simulated and no result is invented.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.discovery import checks
from app.discovery.gate import authorize_single, normalise_target
from app.models import (
    AlertType,
    Asset,
    AssetEventType,
    AssetStatus,
    AssetType,
    Certificate,
    CertificateStatus,
    ChangeType,
    Company,
    Confidence,
    ConfigurationChange,
    Domain,
    ExposedService,
    FindingType,
    IPAddress,
    IPVersion,
    RecordSource,
    Scan,
    ScanEvent,
    ScanPolicy,
    ScanStatus,
    ScanType,
    ServiceState,
    Severity,
)
from app.services.assets import log_event, mark_observed, recompute_asset_risk, recompute_company_risk, record_change
from app.services.findings import fingerprint_for, upsert_alert, upsert_finding

logger = get_logger("asm.discovery.engine")

RISKY_PORTS: dict[int, tuple[str, str]] = {
    21: ("FTP", "critical"),
    23: ("Telnet", "critical"),
    445: ("SMB", "critical"),
    1433: ("Microsoft SQL Server", "critical"),
    3306: ("MySQL", "high"),
    3389: ("Remote Desktop", "critical"),
    5432: ("PostgreSQL", "high"),
    5900: ("VNC", "critical"),
    6379: ("Redis", "critical"),
    9200: ("Elasticsearch", "critical"),
    27017: ("MongoDB", "critical"),
}

ADMIN_HINTS = ("admin", "phpmyadmin", "grafana", "jenkins", "kibana", "webmin", "cpanel", "portainer", "jupyter", "console")
STAGING_HINTS = ("staging", "stage.", "dev.", "test.", "uat.", "preprod", "demo.", "beta.")


@dataclass
class ScanStats:
    targets_total: int = 0
    completed: int = 0
    failed: int = 0
    assets_new: int = 0
    assets_changed: int = 0
    services_found: int = 0
    certificates_found: int = 0
    findings_created: int = 0
    changes_detected: int = 0
    errors: list[str] = field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _event(session: AsyncSession, scan: Scan, message: str, *, level: str = "info", stage: str | None = None, detail: dict | None = None) -> None:
    session.add(
        ScanEvent(
            company_id=scan.company_id,
            scan_id=scan.id,
            level=level,
            stage=stage,
            message=message[:2000],
            detail=detail,
            occurred_at=utcnow(),
        )
    )
    await session.flush()


async def _policy_for(session: AsyncSession, company_id: str) -> ScanPolicy:
    policy = (await session.execute(select(ScanPolicy).where(ScanPolicy.company_id == company_id))).scalar_one_or_none()
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


# --- asset helpers ------------------------------------------------------------


async def _get_or_create_domain(
    session: AsyncSession, company: Company, fqdn: str, source: str, *, is_subdomain: bool, root_domain: str | None = None
) -> tuple[Asset, Domain, bool]:
    asset_type = AssetType.SUBDOMAIN.value if is_subdomain else AssetType.DOMAIN.value
    asset = (
        await session.execute(
            select(Asset).where(Asset.company_id == company.id, Asset.normalized_identifier == f"{asset_type}:{fqdn}")
        )
    ).scalar_one_or_none()

    # The hostname may already be inventoried under another type (for example a
    # web application registered by hand). The domain table is unique per fqdn,
    # so an existing typed row identifies the asset to reuse.
    if asset is None:
        domain_row = (
            await session.execute(select(Domain).where(Domain.company_id == company.id, Domain.fqdn == fqdn))
        ).scalar_one_or_none()
        if domain_row is not None:
            asset = await session.get(Asset, domain_row.asset_id)

    if asset is not None:
        domain_row = (
            await session.execute(select(Domain).where(Domain.asset_id == asset.id))
        ).scalar_one_or_none()
        if domain_row is None:
            domain_row = Domain(
                company_id=company.id,
                asset_id=asset.id,
                fqdn=fqdn,
                root_domain=root_domain or ".".join(fqdn.split(".")[-2:]),
                host_label=fqdn.split(".")[0] if is_subdomain else None,
                is_subdomain=is_subdomain,
                source=source,
            )
            session.add(domain_row)
            await session.flush()
        return asset, domain_row, False

    now = utcnow()
    asset = Asset(
        company_id=company.id,
        name=fqdn,
        normalized_identifier=f"{asset_type}:{fqdn}",
        asset_type=asset_type,
        status=AssetStatus.NEW.value,
        criticality="unknown",
        exposure="internet_facing",
        source=source,
        first_seen=now,
        last_seen=now,
        observation_count=1,
    )
    session.add(asset)
    await session.flush()
    domain_row = Domain(
        company_id=company.id,
        asset_id=asset.id,
        fqdn=fqdn,
        root_domain=root_domain or ".".join(fqdn.split(".")[-2:]),
        host_label=fqdn.split(".")[0] if is_subdomain else None,
        is_subdomain=is_subdomain,
        source=source,
    )
    session.add(domain_row)
    log_event(session, asset, AssetEventType.CREATED, f"Discovered by scan ({source.replace('_', ' ')})", source=source)
    company.asset_count = (company.asset_count or 0) + 1
    await session.flush()
    return asset, domain_row, True


async def _get_or_create_ip(session: AsyncSession, company: Company, address: str, source: str) -> tuple[Asset, IPAddress, bool]:
    asset = (
        await session.execute(select(Asset).where(Asset.company_id == company.id, Asset.normalized_identifier == f"{AssetType.IP_ADDRESS.value}:{address}"))
    ).scalar_one_or_none()
    if asset is not None:
        ip_row = (await session.execute(select(IPAddress).where(IPAddress.asset_id == asset.id))).scalar_one_or_none()
        if ip_row is None:
            parsed = ipaddress.ip_address(address)
            ip_row = IPAddress(
                company_id=company.id,
                asset_id=asset.id,
                address=address,
                version=IPVersion.V6.value if parsed.version == 6 else IPVersion.V4.value,
                is_private=parsed.is_private or parsed.is_loopback,
                source=source,
            )
            session.add(ip_row)
            await session.flush()
        return asset, ip_row, False

    parsed = ipaddress.ip_address(address)
    now = utcnow()
    asset = Asset(
        company_id=company.id,
        name=address,
        normalized_identifier=f"{AssetType.IP_ADDRESS.value}:{address}",
        asset_type=AssetType.IP_ADDRESS.value,
        status=AssetStatus.NEW.value,
        exposure="internet_facing" if checks.is_public_address(address) else "internal",
        source=source,
        first_seen=now,
        last_seen=now,
        observation_count=1,
    )
    session.add(asset)
    await session.flush()
    ip_row = IPAddress(
        company_id=company.id,
        asset_id=asset.id,
        address=address,
        version=IPVersion.V6.value if parsed.version == 6 else IPVersion.V4.value,
        is_private=parsed.is_private or parsed.is_loopback,
        source=source,
    )
    session.add(ip_row)
    log_event(session, asset, AssetEventType.CREATED, f"IP address observed for the first time ({source.replace('_', ' ')})", source=source)
    company.asset_count = (company.asset_count or 0) + 1
    await session.flush()
    return asset, ip_row, True


def _diff_records(old: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    old_map = {(r.get("type"), r.get("value")) for r in old or []}
    new_map = {(r.get("type"), r.get("value")) for r in new or []}
    added = [{"type": t, "value": v} for t, v in sorted(new_map - old_map, key=lambda x: (str(x[0]), str(x[1])))]
    removed = [{"type": t, "value": v} for t, v in sorted(old_map - new_map, key=lambda x: (str(x[0]), str(x[1])))]
    return added, removed


async def _apply_dns(
    session: AsyncSession,
    *,
    scan: Scan,
    asset: Asset,
    domain: Domain,
    dns: checks.DNSResult,
    source: str,
) -> int:
    """Persist resolved records, emitting change events for real differences."""
    changes = 0
    now = utcnow()
    old_records = domain.dns_records or []
    new_records = [{"type": r["type"], "value": r["value"]} for r in dns.records if r["type"] in {"A", "AAAA", "CNAME", "MX", "NS"}]
    added, removed = _diff_records(old_records, new_records)

    for record in added:
        severity = Severity.MEDIUM.value if record["type"] in {"A", "AAAA"} else Severity.INFORMATIONAL.value
        await record_change(
            session,
            asset,
            change_type=ChangeType.DNS_RECORD.value,
            field=f"dns.{record['type']}",
            old_value=None,
            new_value=record["value"],
            summary=f"New {record['type']} record for {asset.name}: {record['value']}",
            severity=severity,
            source=source,
            scan_id=scan.id,
            suspicious=False,
            detail={"record_type": record["type"], "value": record["value"]},
        )
        changes += 1
    for record in removed:
        await record_change(
            session,
            asset,
            change_type=ChangeType.DNS_RECORD.value,
            field=f"dns.{record['type']}",
            old_value=record["value"],
            new_value=None,
            summary=f"{record['type']} record removed from {asset.name}: {record['value']}",
            severity=Severity.MEDIUM.value,
            source=source,
            scan_id=scan.id,
            suspicious=True,
            detail={"record_type": record["type"], "value": record["value"]},
        )
        changes += 1

    previous_ips = set(domain.resolves_to or [])
    current_ips = set(dns.addresses)
    for address in sorted(current_ips - previous_ips):
        await record_change(
            session,
            asset,
            change_type=ChangeType.IP_MAPPING.value,
            field="resolves_to",
            old_value=None,
            new_value=address,
            summary=f"{asset.name} now resolves to {address}",
            severity=Severity.MEDIUM.value,
            source=source,
            scan_id=scan.id,
            suspicious=bool(previous_ips) and address not in previous_ips,
        )
        changes += 1
    for address in sorted(previous_ips - current_ips):
        await record_change(
            session,
            asset,
            change_type=ChangeType.IP_MAPPING.value,
            field="resolves_to",
            old_value=address,
            new_value=None,
            summary=f"{asset.name} no longer resolves to {address}",
            severity=Severity.MEDIUM.value,
            source=source,
            scan_id=scan.id,
            suspicious=True,
        )
        changes += 1

    domain.dns_records = new_records
    domain.resolves_to = sorted(current_ips)
    if dns.nameservers:
        domain.nameservers = dns.nameservers
    domain.dns_resolved_at = now
    domain.source = source
    asset.last_seen = now
    return changes


async def _persist_certificate(session: AsyncSession, *, scan: Scan, asset: Asset, result: checks.CertificateResult) -> tuple[Certificate, bool]:
    existing = (
        await session.execute(
            select(Certificate).where(
                Certificate.company_id == asset.company_id,
                Certificate.host == result.host,
                Certificate.port == result.port,
                Certificate.fingerprint_sha256 == result.fingerprint_sha256,
            )
        )
    ).scalar_one_or_none()

    status = CertificateStatus.VALID.value
    if result.is_expired:
        status = CertificateStatus.EXPIRED.value
    elif result.days_remaining is not None and result.days_remaining <= settings.certificate_expiry_warning_days:
        status = CertificateStatus.EXPIRING_SOON.value
    elif result.is_self_signed:
        status = CertificateStatus.SELF_SIGNED.value
    elif not result.hostname_matches:
        status = CertificateStatus.HOSTNAME_MISMATCH.value
    elif result.weak_key or result.deprecated_signature:
        status = CertificateStatus.WEAK_SIGNATURE.value

    created = False
    if existing is None:
        existing = Certificate(
            company_id=asset.company_id,
            asset_id=asset.id,
            scan_id=scan.id,
            host=result.host,
            port=result.port,
            serial_number=result.serial,
            fingerprint_sha256=result.fingerprint_sha256,
            subject_common_name=result.subject_cn,
            subject_organization=result.subject_org,
            issuer_common_name=result.issuer_cn,
            issuer_organization=result.issuer_org,
            issuer_country=result.issuer_country,
            subject_alternative_names=result.sans,
            san_wildcard=result.is_wildcard,
            not_before=result.not_before,
            not_after=result.not_after,
            days_remaining=result.days_remaining,
            status=status,
            is_expired=result.is_expired,
            is_self_signed=result.is_self_signed,
            hostname_matches=result.hostname_matches,
            is_wildcard=result.is_wildcard,
            key_algorithm=result.key_algorithm,
            key_size=result.key_size,
            signature_algorithm=result.signature_algorithm,
            tls_version=result.tls_version,
            certificate_chain_length=result.chain_length,
            ocsp_url=result.ocsp_url,
            weak_key=result.weak_key,
            deprecated_signature=result.deprecated_signature,
            source=RecordSource.ACTIVE_TLS_PROBE.value,
            observed_at=utcnow(),
        )
        session.add(existing)
        await session.flush()
        created = True
    else:
        existing.scan_id = scan.id
        existing.days_remaining = result.days_remaining
        existing.status = status
        existing.is_expired = result.is_expired
        existing.hostname_matches = result.hostname_matches
        existing.not_after = result.not_after
        existing.observed_at = utcnow()
    return existing, created


async def _certificate_findings(session: AsyncSession, *, scan: Scan, asset: Asset, cert: Certificate, result: checks.CertificateResult) -> int:
    created = 0
    evidence = f"Observed {result.host}:{result.port} — issuer {result.issuer_cn or 'unknown'}, expires {result.not_after.isoformat() if result.not_after else 'unknown'}"
    checks_list: list[tuple[str, str, str, str, str]] = []
    if result.is_expired:
        checks_list.append(
            (
                "TLS certificate expired",
                Severity.HIGH.value,
                "The certificate presented by this endpoint is past its validity period, so clients receive a trust error.",
                "Renew the certificate and deploy it to this endpoint.",
                "expired",
            )
        )
    elif result.days_remaining is not None and result.days_remaining <= settings.certificate_expiry_warning_days:
        severity = Severity.HIGH.value if result.days_remaining <= settings.certificate_expiry_critical_days else Severity.MEDIUM.value
        checks_list.append(
            (
                f"TLS certificate expires in {result.days_remaining} days",
                severity,
                "An expiring certificate will cause an outage when it lapses.",
                "Renew the certificate before expiry and verify automated rotation.",
                "expiring",
            )
        )
    if result.ok and not result.hostname_matches:
        checks_list.append(
            (
                "TLS certificate does not match the hostname",
                Severity.HIGH.value,
                "None of the certificate's subject alternative names cover the host it was served for.",
                "Reissue the certificate with a SAN that matches this hostname.",
                "mismatch",
            )
        )
    if result.is_self_signed:
        checks_list.append(
            (
                "Self-signed TLS certificate",
                Severity.MEDIUM.value,
                "The certificate is not issued by a publicly trusted authority.",
                "Replace with a certificate issued by a trusted CA.",
                "self_signed",
            )
        )
    if result.weak_key:
        checks_list.append(
            (
                f"Weak certificate key ({result.key_algorithm} {result.key_size})",
                Severity.MEDIUM.value,
                "The key is below current minimum strength guidance.",
                "Reissue the certificate with an RSA-2048+ or ECDSA P-256+ key.",
                "weak_key",
            )
        )
    if result.deprecated_signature:
        checks_list.append(
            (
                f"Deprecated certificate signature ({result.signature_algorithm})",
                Severity.MEDIUM.value,
                "SHA-1/MD5 signatures are not accepted by modern clients.",
                "Reissue the certificate with a SHA-256 or stronger signature.",
                "weak_sig",
            )
        )

    for title, severity, description, recommendation, key in checks_list:
        finding, was_created = await upsert_finding(
            session,
            asset=asset,
            finding_type=FindingType.CERTIFICATE.value,
            title=title,
            severity=severity,
            description=description,
            evidence=evidence,
            recommendation=recommendation,
            confidence="confirmed",
            source=RecordSource.ACTIVE_TLS_PROBE.value,
            certificate_id=cert.id,
            scan_id=scan.id,
            extra_key=f"cert:{cert.id}:{key}",
        )
        if was_created:
            created += 1
            log_event(session, asset, AssetEventType.FINDING_OPENED, f"Certificate finding: {title}", severity=severity, source=RecordSource.ACTIVE_TLS_PROBE.value)
            await upsert_alert(
                session,
                company_id=asset.company_id,
                dedupe_key=f"cert:{cert.id}:{key}",
                alert_type=(
                    AlertType.CERTIFICATE_EXPIRED
                    if key == "expired"
                    else AlertType.CERTIFICATE_EXPIRING
                    if key == "expiring"
                    else AlertType.RISKY_CONFIGURATION_CHANGE
                ),
                severity=severity,
                title=f"{title} — {result.host}",
                message=description,
                recommendation=recommendation,
                asset_id=asset.id,
                finding_id=finding.id,
                certificate_id=cert.id,
                scan_id=scan.id,
                source=RecordSource.ACTIVE_TLS_PROBE.value,
            )
    return created


async def _record_service(
    session: AsyncSession,
    *,
    scan: Scan,
    asset: Asset,
    ip_row: IPAddress | None,
    host: str,
    port: int,
    service_name: str | None,
    protocol_category: str | None,
    encrypted: bool,
    source: str,
) -> tuple[ExposedService, bool]:
    existing = (
        await session.execute(
            select(ExposedService).where(
                ExposedService.company_id == asset.company_id,
                ExposedService.asset_id == asset.id,
                ExposedService.port == port,
                ExposedService.transport == "tcp",
            )
        )
    ).scalar_one_or_none()
    now = utcnow()
    risky = port in RISKY_PORTS
    risk_level = RISKY_PORTS.get(port, (None, None))[1] if risky else None

    if existing is None:
        existing = ExposedService(
            company_id=asset.company_id,
            asset_id=asset.id,
            ip_address_id=ip_row.id if ip_row else None,
            host=host,
            port=port,
            transport="tcp",
            service_name=service_name or ("https" if port == 443 else "http" if port == 80 else None),
            protocol_category=protocol_category,
            state=ServiceState.OPEN.value,
            is_encrypted=encrypted,
            is_expected=not risky,
            is_risky=risky,
            risk_level=risk_level,
            recommendation="Restrict this service to trusted networks." if risky else None,
            first_seen=now,
            last_seen=now,
            source=source,
        )
        session.add(existing)
        await session.flush()
        log_event(
            session,
            asset,
            AssetEventType.SERVICE_OBSERVED,
            f"Port {port}/tcp observed open" + (f" ({service_name})" if service_name else ""),
            source=source,
            severity=risk_level,
            scan_id=scan.id,
        )
        if risk_level in {Severity.CRITICAL.value, Severity.HIGH.value}:
            await upsert_alert(
                session,
                company_id=asset.company_id,
                dedupe_key=f"service:{asset.id}:{port}",
                alert_type=AlertType.NEW_EXPOSED_SERVICE,
                severity=risk_level,
                title=f"Risky service exposed — {host}:{port}",
                message=f"Port {port} is reachable from the internet on {asset.name} and is commonly restricted to trusted networks.",
                recommendation="Block the port at the edge or require VPN access.",
                asset_id=asset.id,
                scan_id=scan.id,
                source=source,
            )
        return existing, True

    existing.state = ServiceState.OPEN.value
    existing.last_seen = now
    existing.gone_since = None
    existing.service_name = service_name or existing.service_name
    if existing.source == RecordSource.SEED.value and source != RecordSource.SEED.value:
        # An observed fact supersedes a fixture row, and the provenance change is
        # explicit so the UI stops labelling the row as sample data.
        existing.source = source
    return existing, False


async def _http_findings(session: AsyncSession, *, scan: Scan, asset: Asset, result: checks.HTTPResult, domain_row: Domain | None) -> int:
    created = 0
    if not result.ok or result.status_code is None:
        return 0

    title = (result.title or "").lower()
    url = (result.final_url or result.url).lower()

    if any(hint in title or hint in url for hint in ADMIN_HINTS):
        finding, was_created = await upsert_finding(
            session,
            asset=asset,
            finding_type=FindingType.RISKY_ENDPOINT.value,
            title="Publicly reachable administrative interface",
            severity=Severity.HIGH.value,
            description="An administrative console appears to be served from the public internet.",
            evidence=f"HTTP {result.status_code} at {result.final_url} with title '{result.title or ''}'",
            recommendation="Put the console behind SSO/VPN, or restrict it by IP allow-list.",
            confidence=Confidence.POTENTIAL.value,
            source=RecordSource.ACTIVE_HTTP_PROBE.value,
            scan_id=scan.id,
            extra_key=url,
        )
        if was_created:
            created += 1
            await upsert_alert(
                session,
                company_id=asset.company_id,
                dedupe_key=f"admin-endpoint:{asset.id}:{url}",
                alert_type=AlertType.RISKY_ENDPOINT,
                severity=Severity.HIGH.value,
                title=f"Administrative interface exposed — {asset.name}",
                message="An administrative interface is reachable from the public internet.",
                recommendation="Restrict access to trusted networks or require SSO.",
                asset_id=asset.id,
                finding_id=finding.id,
                scan_id=scan.id,
                source=RecordSource.ACTIVE_HTTP_PROBE.value,
            )

    if any(hint in (asset.name or "").lower() for hint in STAGING_HINTS) and asset.exposure == "internet_facing":
        finding, was_created = await upsert_finding(
            session,
            asset=asset,
            finding_type=FindingType.MISCONFIGURATION.value,
            title="Development or staging environment publicly reachable",
            severity=Severity.MEDIUM.value,
            description="A non-production hostname responds on the public internet, which often lacks production controls.",
            evidence=f"HTTP {result.status_code} at {result.final_url}",
            recommendation="Require authentication in front of non-production environments or remove the public DNS record.",
            confidence=Confidence.POTENTIAL.value,
            source=RecordSource.ACTIVE_HTTP_PROBE.value,
            scan_id=scan.id,
        )
        if was_created:
            created += 1
            await upsert_alert(
                session,
                company_id=asset.company_id,
                dedupe_key=f"staging:{asset.id}",
                alert_type=AlertType.RISKY_ENDPOINT,
                severity=Severity.MEDIUM.value,
                title=f"Staging environment exposed — {asset.name}",
                message="A development or staging hostname is publicly reachable.",
                recommendation="Put authentication in front of non-production environments.",
                asset_id=asset.id,
                finding_id=finding.id,
                scan_id=scan.id,
                source=RecordSource.ACTIVE_HTTP_PROBE.value,
            )

    if "index of /" in title:
        finding, was_created = await upsert_finding(
            session,
            asset=asset,
            finding_type=FindingType.DATA_EXPOSURE.value,
            title="Directory listing enabled",
            severity=Severity.MEDIUM.value,
            description="The web server returns a browsable directory index.",
            evidence=f"Page title '{result.title}' at {result.final_url}",
            recommendation="Disable auto-indexing on the web server.",
            confidence=Confidence.POTENTIAL.value,
            source=RecordSource.ACTIVE_HTTP_PROBE.value,
            scan_id=scan.id,
            extra_key=url,
        )
        created += 1 if was_created else 0

    server_header = result.server or ""
    if any(marker in server_header.lower() for marker in ("apache/", "nginx/", "iis/", "php/")):
        finding, was_created = await upsert_finding(
            session,
            asset=asset,
            finding_type=FindingType.MISCONFIGURATION.value,
            title="Server version disclosed in HTTP headers",
            severity=Severity.LOW.value,
            description="The Server header advertises the exact product version, which helps an attacker choose exploits.",
            evidence=f"Server: {server_header}",
            recommendation="Suppress version details in the Server header.",
            source=RecordSource.ACTIVE_HTTP_PROBE.value,
            scan_id=scan.id,
        )
        created += 1 if was_created else 0

    if domain_row is not None:
        domain_row.web_server = result.server
        domain_row.http_status = result.status_code
        domain_row.http_title = result.title
        domain_row.technologies = result.technologies
        domain_row.source = RecordSource.ACTIVE_HTTP_PROBE.value
    asset.url = asset.url or result.final_url
    return created


async def _port_scan(
    session: AsyncSession,
    *,
    scan: Scan,
    asset: Asset,
    ip_row: IPAddress | None,
    host: str,
    ports: list[int],
    policy: ScanPolicy,
) -> tuple[int, int, list[int]]:
    """TCP connect check. Returns (services_found, findings_created, open_ports)."""
    results = await checks.check_ports(host, ports, timeout=2.0, concurrency=policy.max_concurrency)
    open_ports = [r.port for r in results if r.is_open]
    newly_opened: list[int] = []
    services = 0
    findings = 0
    for result in results:
        if not result.is_open:
            continue
        existing = (
            await session.execute(
                select(ExposedService).where(
                    ExposedService.company_id == asset.company_id,
                    ExposedService.asset_id == asset.id,
                    ExposedService.port == result.port,
                    ExposedService.transport == "tcp",
                )
            )
        ).scalar_one_or_none()
        service, created = await _record_service(
            session,
            scan=scan,
            asset=asset,
            ip_row=ip_row,
            host=host,
            port=result.port,
            service_name=None,
            protocol_category="management" if result.port in {22, 3389, 5900} else ("database" if result.port in {3306, 5432, 6379, 9200, 27017, 1433} else "other"),
            encrypted=result.port in {443, 8443},
            source=RecordSource.ACTIVE_PORT_PROBE.value,
        )
        services += 1 if created else 0
        if existing is None:
            newly_opened.append(result.port)
        if result.port in RISKY_PORTS:
            name, severity = RISKY_PORTS[result.port]
            finding, was_created = await upsert_finding(
                session,
                asset=asset,
                finding_type=FindingType.EXPOSED_SERVICE.value,
                title=f"{name} exposed to the internet (port {result.port})",
                severity=severity,
                description=f"A TCP connect check found port {result.port} open on {host}.",
                evidence=f"TCP connect to {host}:{result.port} succeeded",
                recommendation=f"Restrict {name} to trusted networks or place it behind an authenticated proxy.",
                source=RecordSource.ACTIVE_PORT_PROBE.value,
                service_id=service.id,
                scan_id=scan.id,
                extra_key=str(result.port),
            )
            findings += 1 if was_created else 0
            log_event(session, asset, AssetEventType.FINDING_OPENED, f"Risky service found: {name} on port {result.port}", severity=severity, source=RecordSource.ACTIVE_PORT_PROBE.value, scan_id=scan.id)
    if newly_opened:
        await record_change(
            session,
            asset,
            change_type=ChangeType.EXPOSED_PORT.value,
            field="open_ports",
            old_value=None,
            new_value=", ".join(str(p) for p in newly_opened),
            summary=f"New open ports observed on {asset.name}: {', '.join(str(p) for p in newly_opened)}",
            severity=Severity.HIGH.value if any(p in RISKY_PORTS for p in newly_opened) else Severity.MEDIUM.value,
            source=RecordSource.ACTIVE_PORT_PROBE.value,
            scan_id=scan.id,
            unplanned_exposure=any(p in RISKY_PORTS for p in newly_opened),
        )
    return services, findings, open_ports


async def _scan_domain(
    session: AsyncSession,
    *,
    scan: Scan,
    company: Company,
    policy: ScanPolicy,
    target: str,
    stats: ScanStats,
    active: bool,
    include_subdomains: bool,
    ports: list[int],
) -> None:
    dns = await checks.resolve_dns(target, settings.dns_timeout_seconds)
    if not dns.ok and dns.error:
        raise RuntimeError(dns.error)
    await _event(session, scan, f"DNS resolved {target} ({len(dns.records)} records)", stage="dns")

    roots = {str(root).lower().rstrip(".") for root in (company.root_domains or [])}
    if roots:
        root = next((r for r in roots if target == r or target.endswith(f".{r}")), None)
        is_subdomain = root is not None and target != root
        root = root or ".".join(target.split(".")[-2:])
    else:
        is_subdomain = target.count(".") > 1
        root = ".".join(target.split(".")[-2:])
    asset, domain_row, asset_created = await _get_or_create_domain(
        session, company, target, RecordSource.PASSIVE_DNS.value, is_subdomain=is_subdomain, root_domain=root
    )
    stats.assets_new += 1 if asset_created else 0
    await mark_observed(session, asset, source=RecordSource.PASSIVE_DNS.value, scan_id=scan.id)
    stats.changes_detected += await _apply_dns(session, scan=scan, asset=asset, domain=domain_row, dns=dns, source=RecordSource.PASSIVE_DNS.value)
    if dns.nameservers:
        domain_row.nameservers = dns.nameservers

    ip_rows: list[IPAddress] = []
    for address in dns.addresses[:20]:
        ip_asset, ip_row, ip_created = await _get_or_create_ip(session, company, address, RecordSource.PASSIVE_DNS.value)
        stats.assets_new += 1 if ip_created else 0
        if ip_created:
            ip_row.reverse_dns = await checks.reverse_lookup(address, settings.dns_timeout_seconds)
            ip_row.geo_country = None
            logger.debug("new ip asset", extra={"address": address})
        ip_rows.append(ip_row)
        await upsert_alert(
            session,
            company_id=company.id,
            dedupe_key=f"new-asset:{ip_asset.id}",
            alert_type=AlertType.NEW_ASSET,
            severity=Severity.LOW.value,
            title=f"New IP address discovered — {address}",
            message=f"{address} was observed resolving from {target} during an authorized scan.",
            asset_id=ip_asset.id,
            scan_id=scan.id,
            source=RecordSource.PASSIVE_DNS.value,
            notify=ip_created,
        )

    if include_subdomains and scan.scan_type in {ScanType.CERTIFICATE_TRANSPARENCY.value, ScanType.FULL_RECON.value}:
        names, error = await checks.search_certificate_transparency(target, settings.http_timeout_seconds)
        if error:
            await _event(session, scan, f"Certificate transparency lookup failed for {target}: {error}", level="warning", stage="ct")
        else:
            await _event(session, scan, f"Certificate transparency returned {len(names)} names for {target}", stage="ct")
            for name in names:
                if name == target or len(name) > 253:
                    continue
                sub_asset, _, created = await _get_or_create_domain(
                    session, company, name, RecordSource.PASSIVE_CT_LOG.value, is_subdomain=True, root_domain=root
                )
                if created:
                    stats.assets_new += 1
                    await upsert_alert(
                        session,
                        company_id=company.id,
                        dedupe_key=f"new-asset:{sub_asset.id}",
                        alert_type=AlertType.NEW_ASSET,
                        severity=Severity.LOW.value,
                        title=f"New subdomain discovered — {name}",
                        message=f"{name} appears in public certificate-transparency logs for {target}.",
                        recommendation="Confirm the subdomain is expected and still owned by the organization.",
                        asset_id=sub_asset.id,
                        scan_id=scan.id,
                        source=RecordSource.PASSIVE_CT_LOG.value,
                    )
                    log_event(session, sub_asset, AssetEventType.CREATED, f"Subdomain enumerated from certificate transparency for {target}", source=RecordSource.PASSIVE_CT_LOG.value, scan_id=scan.id)

    if not active:
        return

    # --- TLS + HTTP ---------------------------------------------------------
    host_for_probe = target
    tls = await checks.probe_tls(host_for_probe, 443, settings.tls_timeout_seconds)
    cert_seen = False
    if tls.ok:
        cert, cert_created = await _persist_certificate(session, scan=scan, asset=asset, result=tls)
        cert_seen = True
        stats.certificates_found += 1 if cert_created else 0
        log_event(session, asset, AssetEventType.CERTIFICATE_OBSERVED, f"TLS certificate observed on port 443 (expires in {tls.days_remaining} days)" if tls.days_remaining is not None else "TLS certificate observed on port 443", source=RecordSource.ACTIVE_TLS_PROBE.value, scan_id=scan.id)
        stats.findings_created += await _certificate_findings(session, scan=scan, asset=asset, cert=cert, result=tls)
        _, svc_created = await _record_service(
            session, scan=scan, asset=asset, ip_row=ip_rows[0] if ip_rows else None, host=host_for_probe,
            port=443, service_name=(tls.tls_version or "https").lower() if tls.tls_version else "https",
            protocol_category="web", encrypted=True, source=RecordSource.ACTIVE_TLS_PROBE.value,
        )
        stats.services_found += 1 if svc_created else 0
        if domain_row is not None:
            domain_row.certificate_id = cert.id
    else:
        await _event(session, scan, f"TLS probe failed for {target}: {tls.error}", level="warning", stage="tls")

    scheme = "https" if cert_seen else "http"
    http = await checks.probe_http(f"{scheme}://{host_for_probe}/", settings.http_timeout_seconds)
    if http.ok:
        await _event(session, scan, f"HTTP {http.status_code} from {http.final_url}", stage="http")
        stats.findings_created += await _http_findings(session, scan=scan, asset=asset, result=http, domain_row=domain_row)
        if http.status_code is not None:
            _, svc_created = await _record_service(
                session, scan=scan, asset=asset, ip_row=ip_rows[0] if ip_rows else None, host=host_for_probe,
                port=443 if scheme == "https" else 80, service_name="https" if scheme == "https" else "http",
                protocol_category="web", encrypted=scheme == "https", source=RecordSource.ACTIVE_HTTP_PROBE.value,
            )
            stats.services_found += 1 if svc_created else 0
    else:
        await _event(session, scan, f"HTTP probe failed for {target}: {http.error}", level="warning", stage="http")

    if ports and not policy.safe_mode:
        services, findings, open_ports = await _port_scan(
            session, scan=scan, asset=asset, ip_row=ip_rows[0] if ip_rows else None, host=host_for_probe, ports=ports, policy=policy
        )
        stats.services_found += services
        stats.findings_created += findings
        stats.changes_detected += 1 if open_ports else 0
        await _event(session, scan, f"TCP connect check complete: {len(open_ports)} open of {len(ports)} ports", stage="ports")

    await recompute_asset_risk(session, asset)


async def _scan_ip(
    session: AsyncSession,
    *,
    scan: Scan,
    company: Company,
    policy: ScanPolicy,
    target: str,
    stats: ScanStats,
    active: bool,
    ports: list[int],
) -> None:
    asset, ip_row, created = await _get_or_create_ip(session, company, target, RecordSource.PASSIVE_DNS.value)
    stats.assets_new += 1 if created else 0
    if created:
        ip_row.reverse_dns = await checks.reverse_lookup(target, settings.dns_timeout_seconds)
        await upsert_alert(
            session,
            company_id=company.id,
            dedupe_key=f"new-asset:{asset.id}",
            alert_type=AlertType.NEW_ASSET,
            severity=Severity.LOW.value,
            title=f"New IP address discovered — {target}",
            message=f"{target} was added to the inventory by an authorized scan.",
            asset_id=asset.id,
            scan_id=scan.id,
            source=RecordSource.PASSIVE_DNS.value,
        )
    await mark_observed(session, asset, source=RecordSource.PASSIVE_DNS.value, scan_id=scan.id)

    if not active:
        return

    tls = await checks.probe_tls(target, 443, settings.tls_timeout_seconds)
    if tls.ok:
        cert, cert_created = await _persist_certificate(session, scan=scan, asset=asset, result=tls)
        stats.certificates_found += 1 if cert_created else 0
        stats.findings_created += await _certificate_findings(session, scan=scan, asset=asset, cert=cert, result=tls)
        _, svc_created = await _record_service(
            session, scan=scan, asset=asset, ip_row=ip_row, host=target, port=443,
            service_name="https", protocol_category="web", encrypted=True, source=RecordSource.ACTIVE_TLS_PROBE.value,
        )
        stats.services_found += 1 if svc_created else 0

    http = await checks.probe_http(f"{'https' if tls.ok else 'http'}://{target}/", settings.http_timeout_seconds)
    if http.ok:
        stats.findings_created += await _http_findings(session, scan=scan, asset=asset, result=http, domain_row=None)

    if ports and not policy.safe_mode:
        services, findings, open_ports = await _port_scan(session, scan=scan, asset=asset, ip_row=ip_row, host=target, ports=ports, policy=policy)
        stats.services_found += services
        stats.findings_created += findings
        stats.changes_detected += 1 if open_ports else 0

    await recompute_asset_risk(session, asset)


async def _expand_targets(targets: list[str], max_targets: int) -> list[tuple[str, str]]:
    expanded: list[tuple[str, str]] = []
    for raw in targets:
        target, kind = normalise_target(raw)
        if kind == "cidr":
            network = ipaddress.ip_network(target, strict=False)
            if network.num_addresses > 64:
                raise ValueError(f"{target} expands to {network.num_addresses} addresses; scan at most /26 at a time")
            for host in list(network.hosts())[:max_targets]:
                expanded.append((str(host), "ip"))
        else:
            expanded.append((target, kind))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for target, kind in expanded:
        if target not in seen:
            seen.add(target)
            unique.append((target, kind))
    if len(unique) > max_targets:
        raise ValueError(f"This run would touch {len(unique)} targets; the policy limit is {max_targets}")
    return unique


async def run_scan(scan_id: str) -> None:
    """Entry point used by both the in-process runner and the Celery worker."""
    async with session_scope() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            logger.warning("scan not found", extra={"scan_id": scan_id})
            return
        if scan.status not in {ScanStatus.QUEUED.value, ScanStatus.RUNNING.value}:
            return

        company = await session.get(Company, scan.company_id)
        if company is None:
            scan.status = ScanStatus.FAILED.value
            scan.error_message = "Company no longer exists"
            return

        policy = await _policy_for(session, company.id)
        scan.status = ScanStatus.RUNNING.value
        scan.started_at = scan.started_at or utcnow()
        await _event(session, scan, "Scan started")

        active = scan.scan_type in {
            ScanType.TLS_CERTIFICATE.value,
            ScanType.HTTP_FINGERPRINT.value,
            ScanType.FULL_RECON.value,
            ScanType.PORT_EXPOSURE.value,
        }
        if settings.discovery_offline:
            # Global kill switch: resolve names from DNS only and never open a
            # socket to a target, regardless of what the scan requested.
            active = False
        include_subdomains = bool(scan.options.get("include_subdomains", True))
        allowed_ports = {int(p) for p in policy.allowed_ports if 0 < int(p) < 65536}
        requested_ports = scan.options.get("ports")
        if requested_ports is None and scan.scan_type in {ScanType.PORT_EXPOSURE.value, ScanType.FULL_RECON.value}:
            requested_ports = allowed_ports
        ports = sorted({int(p) for p in requested_ports or []} & allowed_ports)[:80] if not policy.safe_mode and active else []

        try:
            targets = await _expand_targets(list(scan.targets), policy.max_targets_per_run)
        except ValueError as exc:
            scan.status = ScanStatus.FAILED.value
            scan.error_message = str(exc)
            scan.finished_at = utcnow()
            await _event(session, scan, f"Scan refused: {exc}", level="error")
            return

        stats = ScanStats(targets_total=len(targets))
        scan.targets_total = len(targets)
        await session.commit()

        cancelled = False
        for target, kind in targets:
            # The row may have been cancelled by a user since the last commit.
            await session.refresh(scan)
            if scan.status == ScanStatus.CANCELLED.value:
                cancelled = True
                await _event(session, scan, "Cancellation requested; stopping before the next target", level="warning", stage="cancel")
                break
            # Re-authorize at execution time: approval may have been revoked while queued.
            try:
                await authorize_single(
                    session,
                    company_id=company.id,
                    target=target,
                    active_probing=active,
                    company_root_domains=company.root_domains or [],
                )
            except Exception as exc:
                stats.failed += 1
                stats.errors.append(f"{target}: {getattr(exc, 'message', str(exc))}")
                await _event(session, scan, f"Authorization check failed for {target}: {getattr(exc, 'message', str(exc))}", level="error", stage="authorize")
                await session.commit()
                continue

            try:
                if kind == "ip":
                    await _scan_ip(
                        session, scan=scan, company=company, policy=policy, target=target,
                        stats=stats, active=active, ports=ports,
                    )
                else:
                    await _scan_domain(
                        session, scan=scan, company=company, policy=policy, target=target,
                        stats=stats, active=active, include_subdomains=include_subdomains, ports=ports,
                    )
                stats.completed += 1
                await _event(session, scan, f"Completed {target}", stage="target")
            except Exception as exc:  # one bad target must not end the run
                stats.failed += 1
                stats.errors.append(f"{target}: {exc}")
                logger.warning("target scan failed", extra={"scan_id": scan.id, "target": target, "error": str(exc)[:300]})
                await _event(session, scan, f"Failed {target}: {exc}", level="error", stage="target")

            scan.targets_completed = stats.completed
            scan.targets_failed = stats.failed
            scan.assets_new = stats.assets_new
            scan.services_found = stats.services_found
            scan.certificates_found = stats.certificates_found
            scan.findings_created = stats.findings_created
            scan.changes_detected = stats.changes_detected
            await session.commit()

            if policy.requests_per_second > 0:
                await asyncio.sleep(1.0 / policy.requests_per_second)

        finished_at = utcnow()
        scan.finished_at = finished_at
        if scan.started_at:
            started = scan.started_at if scan.started_at.tzinfo else scan.started_at.replace(tzinfo=timezone.utc)
            scan.duration_seconds = max(0, int((finished_at - started).total_seconds()))
        scan.result_summary = {
            "targets_completed": stats.completed,
            "targets_failed": stats.failed,
            "errors": stats.errors[:20],
            "active_probes": active,
            "safe_mode": policy.safe_mode,
            "cancelled": cancelled,
        }
        scan.produced_live_data = stats.completed > 0
        if cancelled:
            scan.status = ScanStatus.CANCELLED.value
            await _event(
                session,
                scan,
                f"Scan cancelled after {stats.completed} of {len(targets)} targets; partial observations were kept",
                level="warning",
                stage="cancel",
            )
        else:
            scan.status = ScanStatus.COMPLETED_WITH_ERRORS.value if stats.failed else ScanStatus.COMPLETED.value
            await _event(session, scan, f"Scan finished: {stats.completed} targets completed, {stats.failed} failed", level="info" if not stats.failed else "warning")

        await recompute_company_risk(session, company.id)
        await _write_risk_snapshot(session, company.id)
        await session.commit()
        logger.info("scan finished", extra={"scan_id": scan.id, "completed": stats.completed, "failed": stats.failed})


async def _write_risk_snapshot(session: AsyncSession, company_id: str) -> None:
    from app.models import Finding, RiskScore
    from app.models.enums import OPEN_FINDING_STATUSES, classify
    from app.models.risk import RISK_MODEL_VERSION

    company = await session.get(Company, company_id)
    if company is None:
        return
    scores = [
        score
        for score in (await session.execute(select(Asset.risk_score).where(Asset.company_id == company_id))).scalars().all()
        if score
    ]
    open_findings = (
        await session.execute(
            select(Finding.severity).where(Finding.company_id == company_id, Finding.status.in_(list(OPEN_FINDING_STATUSES)))
        )
    ).scalars().all()
    counts = {s: 0 for s in ("critical", "high", "medium", "low", "informational")}
    for severity in open_findings:
        if severity in counts:
            counts[severity] += 1
    previous = (
        await session.execute(
            select(RiskScore).where(RiskScore.company_id == company_id, RiskScore.scope == "company").order_by(RiskScore.computed_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    score = round(company.risk_score or 0.0, 1)
    session.add(
        RiskScore(
            company_id=company_id,
            scope="company",
            object_id=company_id,
            score=score,
            classification=classify(score),
            factors={"top_asset_scores": sorted(scores, reverse=True)[:5]},
            finding_count=sum(counts.values()),
            critical_count=counts["critical"],
            high_count=counts["high"],
            model_version=RISK_MODEL_VERSION,
            computed_at=utcnow(),
            previous_score=previous.score if previous else None,
            delta=round(score - previous.score, 1) if previous else None,
            driver_summary=f"{counts['critical']} critical and {counts['high']} high findings across {len(scores)} risky assets.",
        )
    )
