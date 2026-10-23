"""Risk model and alert-preference fan-out."""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import session_scope
from app.models import AlertPreference, AlertType, Company, Notification, Severity, User
from app.models.enums import classify
from app.services.findings import upsert_alert
from app.services.risk import assess_finding


def test_critical_exploited_finding_scores_highest():
    exploited = assess_finding(
        severity="critical",
        asset_type="api_endpoint",
        exposure="internet_facing",
        criticality="business_critical",
        confidence="confirmed",
        cvss=10.0,
        has_known_exploit=True,
    )
    potential = assess_finding(
        severity="critical",
        asset_type="api_endpoint",
        exposure="internet_facing",
        criticality="business_critical",
        confidence="potential",
        cvss=10.0,
        has_known_exploit=True,
    )
    internal = assess_finding(
        severity="critical",
        asset_type="api_endpoint",
        exposure="internal",
        criticality="low",
        confidence="confirmed",
        cvss=10.0,
    )

    assert exploited.score >= 9.5
    assert classify(exploited.score) == "critical"
    assert exploited.score > potential.score > internal.score
    assert {factor.key for factor in exploited.factors} >= {"severity", "exploitability", "exposure", "known_exploit"}
    assert "critical severity" in exploited.driver_summary.lower()
    exploit_factor = next(factor for factor in exploited.factors if factor.key == "known_exploit")
    assert "public exploit" in exploit_factor.description.lower()


def test_company_risk_classification_boundaries():
    assert classify(10.0) == "critical"
    assert classify(8.0) == "high"
    assert classify(5.0) == "medium"
    assert classify(2.0) == "low"
    assert classify(0.1) == "informational"


async def test_alert_preferences_filter_notifications():
    async with session_scope() as session:
        company = (await session.execute(select(Company).where(Company.slug == "northwind"))).scalar_one()
        admin = (await session.execute(select(User).where(User.email == "admin@northwind.example"))).scalar_one()
        analyst = (await session.execute(select(User).where(User.email == "analyst@northwind.example"))).scalar_one()

        # Seeded preferences: admin = low, analyst = medium.
        low_alert, _ = await upsert_alert(
            session,
            company_id=company.id,
            dedupe_key="test-low-severity",
            alert_type=AlertType.RISKY_ENDPOINT,
            severity=Severity.LOW.value,
            title="Low severity preference probe",
            message="Should only reach recipients with a low threshold.",
        )
        high_alert, _ = await upsert_alert(
            session,
            company_id=company.id,
            dedupe_key="test-high-severity",
            alert_type=AlertType.RISKY_ENDPOINT,
            severity=Severity.HIGH.value,
            title="High severity preference probe",
            message="Should reach both seeded Northwind recipients.",
        )
        await session.flush()

        async def recipients(alert_id: str) -> set[str]:
            rows = (
                await session.execute(select(Notification.user_id).where(Notification.alert_id == alert_id))
            ).scalars().all()
            return set(rows)

        low_recipients = await recipients(low_alert.id)
        high_recipients = await recipients(high_alert.id)
        assert admin.id in low_recipients
        assert analyst.id not in low_recipients
        assert {admin.id, analyst.id} <= high_recipients

        # Muting a type suppresses only that type's notifications.
        preference = (
            await session.execute(
                select(AlertPreference).where(
                    AlertPreference.user_id == analyst.id,
                    AlertPreference.company_id == company.id,
                )
            )
        ).scalar_one()
        preference.muted_types = [AlertType.RISKY_ENDPOINT.value]
        muted_alert, _ = await upsert_alert(
            session,
            company_id=company.id,
            dedupe_key="test-muted-type",
            alert_type=AlertType.RISKY_ENDPOINT,
            severity=Severity.CRITICAL.value,
            title="Muted type preference probe",
            message="The analyst muted this alert type.",
        )
        await session.flush()
        muted_recipients = await recipients(muted_alert.id)
        assert admin.id in muted_recipients
        assert analyst.id not in muted_recipients
