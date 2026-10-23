"""Network checks used by the discovery engine.

Only bounded, non-destructive observations are performed:
  * DNS resolution (recursive queries to the system resolver);
  * certificate-transparency search via crt.sh (public, read-only HTTP GET);
  * a single TLS handshake per host:port to read the presented certificate;
  * HTTP HEAD/GET to read status, headers and page title;
  * an optional TCP connect check per port (no payloads, no version probing).

Every function is timeout-bounded and returns a typed result instead of raising,
so one unreachable host cannot abort a scan.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, ed448, rsa
from cryptography.x509.oid import NameOID

from app.core.logging import get_logger

logger = get_logger("asm.discovery")

USER_AGENT = "ASMScanner/1.0 (+authorized-security-assessment)"
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_GENERATOR_RE = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', re.IGNORECASE)


@dataclass(slots=True)
class DNSResult:
    name: str
    ok: bool
    records: list[dict[str, Any]] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    cnames: list[str] = field(default_factory=list)
    nameservers: list[str] = field(default_factory=list)
    mx: list[str] = field(default_factory=list)
    txt: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class CertificateResult:
    host: str
    port: int
    ok: bool
    serial: str | None = None
    fingerprint_sha256: str | None = None
    subject_cn: str | None = None
    subject_org: str | None = None
    issuer_cn: str | None = None
    issuer_org: str | None = None
    issuer_country: str | None = None
    sans: list[str] = field(default_factory=list)
    not_before: datetime | None = None
    not_after: datetime | None = None
    days_remaining: int | None = None
    is_expired: bool = False
    is_self_signed: bool = False
    hostname_matches: bool = True
    key_algorithm: str | None = None
    key_size: int | None = None
    signature_algorithm: str | None = None
    tls_version: str | None = None
    cipher: str | None = None
    chain_length: int | None = None
    ocsp_url: str | None = None
    weak_key: bool = False
    deprecated_signature: bool = False
    error: str | None = None

    @property
    def is_wildcard(self) -> bool:
        return any(name.startswith("*.") for name in self.sans) or bool(self.subject_cn and self.subject_cn.startswith("*."))


@dataclass(slots=True)
class HTTPResult:
    url: str
    ok: bool
    status_code: int | None = None
    final_url: str | None = None
    server: str | None = None
    powered_by: str | None = None
    title: str | None = None
    technologies: list[str] = field(default_factory=list)
    latency_ms: int | None = None
    content_type: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class PortResult:
    host: str
    port: int
    is_open: bool
    latency_ms: int | None = None
    error: str | None = None


# --- DNS --------------------------------------------------------------------


async def resolve_dns(name: str, timeout: float) -> DNSResult:
    result = DNSResult(name=name, ok=False)
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = min(timeout, 2.0)

    async def query(record_type: str) -> list:
        try:
            answer = await asyncio.wait_for(resolver.resolve(name, record_type), timeout=timeout)
            return list(answer)
        except (dns.exception.DNSException, asyncio.TimeoutError, OSError):
            return []

    try:
        a_records, aaaa_records, cname_records, ns_records, mx_records, txt_records = await asyncio.gather(
            query("A"), query("AAAA"), query("CNAME"), query("NS"), query("MX"), query("TXT")
        )
    except Exception as exc:  # pragma: no cover - resolver backends are environment-specific
        result.error = str(exc)[:300]
        return result

    for record in a_records:
        result.addresses.append(str(record))
        result.records.append({"type": "A", "value": str(record)})
    for record in aaaa_records:
        result.addresses.append(str(record))
        result.records.append({"type": "AAAA", "value": str(record)})
    for record in cname_records:
        target = str(record.target).rstrip(".")
        result.cnames.append(target)
        result.records.append({"type": "CNAME", "value": target})
    for record in ns_records:
        target = str(record.target).rstrip(".")
        result.nameservers.append(target)
        result.records.append({"type": "NS", "value": target})
    for record in mx_records:
        exchange = str(record.exchange).rstrip(".")
        result.mx.append(exchange)
        result.records.append({"type": "MX", "value": exchange, "priority": record.preference})
    for record in txt_records:
        value = " ".join(part.decode("utf-8", "replace") if isinstance(part, bytes) else str(part) for part in record.strings)
        result.txt.append(value)
        result.records.append({"type": "TXT", "value": value[:500]})

    result.ok = bool(result.records)
    return result


async def reverse_lookup(address: str, timeout: float) -> str | None:
    try:
        hostname, _ = await asyncio.wait_for(asyncio.get_running_loop().getnameinfo((address, 0), 0), timeout=timeout)
        return hostname.rstrip(".")
    except Exception:
        return None


# --- certificate transparency -------------------------------------------------


async def search_certificate_transparency(domain: str, timeout: float) -> tuple[list[str], str | None]:
    """Query crt.sh for names under `domain`.

    Returns (names, error). Rate limiting is intentional: crt.sh is a free public
    service and a scan must never hammer it.
    """
    names: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get("https://crt.sh/", params={"q": f"%.{domain}", "output": "json"})
            if response.status_code != 200:
                return [], f"crt.sh returned HTTP {response.status_code}"
            for entry in response.json():
                for raw in str(entry.get("name_value", "")).splitlines():
                    candidate = raw.strip().lower().lstrip("*.")
                    if candidate.endswith(domain) and " " not in candidate:
                        names.add(candidate)
        return sorted(names)[:500], None
    except Exception as exc:
        return [], str(exc)[:300]


# --- TLS ----------------------------------------------------------------------


def _name(cert: x509.Certificate, oid) -> str | None:
    attributes = cert.subject.get_attributes_for_oid(oid) if oid in (NameOID.COMMON_NAME, NameOID.ORGANIZATION_NAME, NameOID.COUNTRY_NAME) else []
    return str(attributes[0].value) if attributes else None


def _issuer_name(cert: x509.Certificate, oid) -> str | None:
    attributes = cert.issuer.get_attributes_for_oid(oid)
    return str(attributes[0].value) if attributes else None


def _hostname_matches(hostname: str, sans: list[str], common_name: str | None) -> bool:
    hostname = hostname.lower().rstrip(".")
    candidates = sans or ([common_name] if common_name else [])
    for candidate in candidates:
        candidate = candidate.lower().rstrip(".")
        if candidate == hostname:
            return True
        if candidate.startswith("*.") and hostname.count(".") == candidate.count(".") and hostname.endswith(candidate[1:]):
            return True
    return False


async def probe_tls(host: str, port: int, timeout: float) -> CertificateResult:
    result = CertificateResult(host=host, port=port, ok=False)
    context = ssl.create_default_context()
    # The probe's purpose is to read what the endpoint presents, including
    # broken certificates. Chain validation is not performed here; the finding
    # engine evaluates the certificate's properties instead.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, ssl=context, server_hostname=host), timeout=timeout)
        ssl_object = writer.get_extra_info("ssl_object")
        if ssl_object is None:
            result.error = "TLS handshake did not complete"
            return result
        der = ssl_object.getpeercert(binary_form=True)
        if not der:
            result.error = "No certificate presented"
            return result
        cert = x509.load_der_x509_certificate(der)
        result.ok = True
        result.serial = format(cert.serial_number, "x")
        from cryptography.hazmat.primitives import hashes

        result.fingerprint_sha256 = cert.fingerprint(hashes.SHA256()).hex()
        result.subject_cn = _name(cert, NameOID.COMMON_NAME)
        result.subject_org = _name(cert, NameOID.ORGANIZATION_NAME)
        result.issuer_cn = _issuer_name(cert, NameOID.COMMON_NAME)
        result.issuer_org = _issuer_name(cert, NameOID.ORGANIZATION_NAME)
        result.issuer_country = _issuer_name(cert, NameOID.COUNTRY_NAME)
        result.is_self_signed = cert.issuer == cert.subject

        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            result.sans = [str(name) for name in san_ext.value.get_values_for_type(x509.DNSName)]
        except x509.ExtensionNotFound:
            result.sans = []

        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
        now = datetime.now(timezone.utc)
        result.not_before = not_before
        result.not_after = not_after
        result.days_remaining = (not_after - now).days
        result.is_expired = not_after <= now
        result.hostname_matches = _hostname_matches(host, result.sans, result.subject_cn)

        public_key = cert.public_key()
        if isinstance(public_key, rsa.RSAPublicKey):
            result.key_algorithm = "RSA"
            result.key_size = public_key.key_size
            result.weak_key = public_key.key_size < 2048
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            result.key_algorithm = "ECDSA"
            result.key_size = public_key.key_size
            result.weak_key = public_key.key_size < 256
        elif isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            result.key_algorithm = "EdDSA"
        else:  # pragma: no cover - exotic key types
            result.key_algorithm = type(public_key).__name__

        signature_name = (cert.signature_algorithm_oid._name or "").lower()
        result.signature_algorithm = signature_name
        result.deprecated_signature = "sha1" in signature_name or "md5" in signature_name

        result.tls_version = ssl_object.version()
        cipher = ssl_object.cipher()
        result.cipher = cipher[0] if cipher else None
        result.chain_length = len(ssl_object.get_unverified_chain() or []) if hasattr(ssl_object, "get_unverified_chain") else 1

        try:
            aia = cert.extensions.get_extension_for_class(x509.AuthorityInformationAccess)
            for entry in aia.value:
                if entry.access_method == x509.AuthorityInformationAccessOID.OCSP:
                    result.ocsp_url = entry.access_location.value
                    break
        except x509.ExtensionNotFound:
            pass

        return result
    except asyncio.TimeoutError:
        result.error = f"TLS handshake timed out after {timeout}s"
    except ssl.SSLError as exc:
        result.error = f"TLS error: {exc.reason or exc}"
    except OSError as exc:
        result.error = f"Connection failed: {exc.strerror or exc}"
    except Exception as exc:  # pragma: no cover - malformed certificates
        result.error = f"Certificate parse failed: {exc}"[:300]
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
    return result


# --- HTTP ---------------------------------------------------------------------


async def probe_http(url: str, timeout: float) -> HTTPResult:
    result = HTTPResult(url=url, ok=False)
    started = asyncio.get_running_loop().time()
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=False,  # fingerprinting must work on misconfigured endpoints
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = await client.get(url)
            result.status_code = response.status_code
            result.final_url = str(response.url)
            result.server = response.headers.get("server")
            result.powered_by = response.headers.get("x-powered-by")
            result.content_type = response.headers.get("content-type")
            result.redirect_chain = [str(r.url) for r in response.history]
            technologies: set[str] = set()
            server = (result.server or "").lower()
            for tech, needle in (
                ("nginx", "nginx"),
                ("apache", "apache"),
                ("iis", "iis"),
                ("cloudflare", "cloudflare"),
                ("envoy", "envoy"),
                ("litespeed", "litespeed"),
                ("caddy", "caddy"),
            ):
                if needle in server:
                    technologies.add(tech)
            powered = (result.powered_by or "").lower()
            for tech in ("php", "asp.net", "express", "next.js", "django", "rails", "servlet"):
                if tech in powered:
                    technologies.add(tech)
            for cookie in response.cookies.jar:
                name = cookie.name.lower()
                if name.startswith("phpsessid"):
                    technologies.add("php")
                elif name.startswith("jsessionid"):
                    technologies.add("java")
                elif name.startswith("asp.net"):
                    technologies.add("asp.net")
                elif name.startswith("laravel"):
                    technologies.add("laravel")
            body = response.text[:200_000]
            title_match = _TITLE_RE.search(body)
            if title_match:
                result.title = unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()[:300]
            generator = _GENERATOR_RE.search(body)
            if generator:
                technologies.add(generator.group(1).strip().lower()[:60])
            result.technologies = sorted(technologies)
            result.ok = True
    except httpx.HTTPError as exc:
        result.error = f"{type(exc).__name__}: {exc}"[:300]
    except Exception as exc:  # pragma: no cover
        result.error = str(exc)[:300]
    finally:
        result.latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
    return result


# --- ports --------------------------------------------------------------------


async def check_port(host: str, port: int, timeout: float) -> PortResult:
    """Single TCP connect check. No payload, no banner grab, no version probe."""
    started = asyncio.get_running_loop().time()
    writer = None
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        return PortResult(host=host, port=port, is_open=True, latency_ms=int((asyncio.get_running_loop().time() - started) * 1000))
    except (asyncio.TimeoutError, OSError):
        return PortResult(host=host, port=port, is_open=False)
    except Exception as exc:  # pragma: no cover
        return PortResult(host=host, port=port, is_open=False, error=str(exc)[:200])
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def check_ports(host: str, ports: list[int], timeout: float, concurrency: int) -> list[PortResult]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def guarded(port: int) -> PortResult:
        async with semaphore:
            return await check_port(host, port, timeout)

    return list(await asyncio.gather(*(guarded(p) for p in ports)))


def is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
