"""Scan authorization gate.

A discovery run is legal only over scopes the customer has documented ownership
of. This module is the single place that decides whether a target is in scope,
and it fails closed: an unparsable target, an unapproved record, an expired
record or a missing record all deny the run.

The check is executed twice — when a scan is requested and again per target
inside the worker — because an approval can be revoked while a job sits in the
queue.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ScanAuthorizationError
from app.models import AuthorizationRecord, AuthorizationStatus
from app.models.enums import AuthorizationScopeType

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+\.?$")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AuthorizedTarget:
    target: str
    kind: str  # "domain" | "ip"
    record: AuthorizationRecord


def normalise_target(raw: str) -> tuple[str, str]:
    """Extract a host from any of domain / URL / IP / CIDR-ish input."""
    value = raw.strip().lower().rstrip(".")
    if not value:
        raise ScanAuthorizationError("Empty scan target")
    if "://" in value:
        parsed = urlparse(value)
        value = (parsed.hostname or "").rstrip(".")
    try:
        address = ipaddress.ip_address(value)
        return str(address), "ip"
    except ValueError:
        pass
    if "/" in value:
        try:
            network = ipaddress.ip_network(value, strict=False)
            return str(network), "cidr"
        except ValueError as exc:
            raise ScanAuthorizationError(f"'{raw}' is not a valid IP, CIDR or domain") from exc
    if not _DOMAIN_RE.match(value):
        raise ScanAuthorizationError(f"'{raw}' is not a valid domain or IP address")
    return value, "domain"


def target_in_scope(target: str, kind: str, scope_type: str, scope_value: str) -> bool:
    scope_value = scope_value.strip().lower().rstrip(".")

    if scope_type == AuthorizationScopeType.DOMAIN.value:
        return kind == "domain" and (target == scope_value or target.endswith("." + scope_value))
    if scope_type == AuthorizationScopeType.WILDCARD_DOMAIN.value:
        base = scope_value.removeprefix("*.").lstrip(".")
        return kind == "domain" and (target == base or target.endswith("." + base))
    if scope_type == AuthorizationScopeType.URL.value:
        try:
            host = (urlparse(scope_value if "://" in scope_value else f"https://{scope_value}").hostname or "").rstrip(".")
        except ValueError:
            return False
        return kind == "domain" and (target == host or target.endswith("." + host))
    if scope_type in {AuthorizationScopeType.IPV4.value, AuthorizationScopeType.IPV6.value}:
        return kind == "ip" and target == scope_value
    if scope_type == AuthorizationScopeType.CIDR.value:
        try:
            network = ipaddress.ip_network(scope_value, strict=False)
        except ValueError:
            return False
        if kind == "ip":
            try:
                return ipaddress.ip_address(target) in network
            except ValueError:
                return False
        if kind == "cidr":
            try:
                return ipaddress.ip_network(target, strict=False).subnet_of(network)
            except ValueError:
                return False
        return False
    return False


def record_is_live(record: AuthorizationRecord) -> bool:
    if record.status != AuthorizationStatus.APPROVED.value:
        return False
    if record.expires_at is not None and record.expires_at <= utcnow():
        return False
    return True


async def authorize_targets(
    session: AsyncSession,
    *,
    company_id: str,
    company_root_domains: list[str],
    targets: list[str],
    authorization_id: str | None,
    active_probing: bool,
) -> list[AuthorizedTarget]:
    """Resolve every target to a live authorization record or refuse the run.

    All-or-nothing: a partially authorized scan would silently do less than the
    operator asked for, and the target that was skipped is exactly the one an
    operator most needs to know about.
    """
    if not targets:
        raise ScanAuthorizationError("Provide at least one target to scan")

    records = list(
        (
            await session.execute(
                select(AuthorizationRecord).where(AuthorizationRecord.company_id == company_id)
            )
        ).scalars().all()
    )
    if authorization_id:
        records = [r for r in records if r.id == authorization_id]
        if not records:
            raise ScanAuthorizationError("The selected authorization record does not exist for this company")
        if not record_is_live(records[0]):
            raise ScanAuthorizationError("The selected authorization record is not approved or has expired")

    resolved: list[AuthorizedTarget] = []
    denied: list[str] = []
    for raw in targets:
        target, kind = normalise_target(raw)
        matched: AuthorizationRecord | None = None
        for record in records:
            if not record_is_live(record):
                continue
            if target_in_scope(target, kind, record.scope_type, record.value):
                matched = record
                break
        if matched is None:
            denied.append(raw)
            continue
        if active_probing and not matched.allow_active_probing:
            # A passive-only authorization cannot be used for TLS/HTTP/port probes.
            denied.append(f"{raw} (authorization permits passive checks only)")
            continue
        resolved.append(AuthorizedTarget(target=target, kind=kind, record=matched))

    if denied:
        raise ScanAuthorizationError(
            "These targets are not covered by an approved authorization: " + ", ".join(denied[:10]),
            details={
                "denied_targets": denied,
                "root_domains_on_file": company_root_domains,
                "hint": "Ask a company admin to add and approve an authorization record for this scope.",
            },
        )
    return resolved


async def authorize_single(
    session: AsyncSession,
    *,
    company_id: str,
    target: str,
    active_probing: bool,
    company_root_domains: list[str],
) -> AuthorizedTarget:
    resolved = await authorize_targets(
        session,
        company_id=company_id,
        company_root_domains=company_root_domains,
        targets=[target],
        authorization_id=None,
        active_probing=active_probing,
    )
    return resolved[0]
