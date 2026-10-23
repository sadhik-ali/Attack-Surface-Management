"""Certificate status derivation and cleanup of the expired/expiring boundary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import session_scope
from app.discovery import checks
from app.discovery.engine import _persist_certificate
from app.models import Asset, Company, Scan


def _result(host: str, fingerprint: str, *, days: int, expired: bool = False) -> checks.CertificateResult:
    now = datetime.now(timezone.utc)
    return checks.CertificateResult(
        host=host,
        port=443,
        ok=True,
        serial="01",
        fingerprint_sha256=fingerprint,
        subject_cn=host,
        issuer_cn="Test CA",
        sans=[host],
        not_before=now - timedelta(days=30),
        not_after=now + timedelta(days=days),
        days_remaining=days,
        is_expired=expired,
        hostname_matches=True,
    )


async def test_certificate_status_thresholds():
    async with session_scope() as session:
        company = (await session.execute(select(Company).where(Company.slug == "northwind"))).scalar_one()
        asset = (await session.execute(select(Asset).where(Asset.company_id == company.id).limit(1))).scalar_one()
        scan = (
            await session.execute(select(Scan).where(Scan.company_id == company.id).limit(1))
        ).scalar_one()

        expiring, created = await _persist_certificate(
            session, scan=scan, asset=asset, result=_result("qa-expiring.example", "fp-expiring", days=5)
        )
        assert created is True
        assert expiring.status == "expiring_soon"
        assert expiring.days_remaining == 5
        assert expiring.is_expired is False

        expired, _ = await _persist_certificate(
            session,
            scan=scan,
            asset=asset,
            result=_result("qa-expired.example", "fp-expired", days=-1, expired=True),
        )
        assert expired.status == "expired"
        assert expired.is_expired is True

        valid, _ = await _persist_certificate(
            session, scan=scan, asset=asset, result=_result("qa-valid.example", "fp-valid", days=90)
        )
        assert valid.status == "valid"
