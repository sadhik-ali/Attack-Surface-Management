"""Scan authorization gate and capability honesty."""

from __future__ import annotations

from tests.conftest import API, company_id_for, login


async def test_capabilities_do_not_claim_cloud_support(client):
    headers = await login(client, "analyst@northwind.example")
    company = await company_id_for(client, headers, "northwind")

    response = await client.get(f"{API}/companies/{company}/scans/capabilities", headers=headers)
    assert response.status_code == 200
    capabilities = {entry["scan_type"]: entry for entry in response.json()}
    assert capabilities["passive_dns"]["implemented"] is True
    assert capabilities["cloud_inventory"]["implemented"] is False
    assert capabilities["cloud_inventory"]["availability_note"]


async def test_scan_requires_confirmation_and_approved_scope(client):
    headers = await login(client, "analyst@northwind.example")
    company = await company_id_for(client, headers, "northwind")

    unconfirmed = await client.post(
        f"{API}/companies/{company}/scans",
        headers=headers,
        json={"scan_type": "passive_dns", "targets": ["northwind.example"], "confirm_authorized": False},
    )
    assert unconfirmed.status_code == 422

    pending_scope = await client.post(
        f"{API}/companies/{company}/scans",
        headers=headers,
        json={
            "scan_type": "passive_dns",
            "targets": ["northwind-labs.example"],
            "name": "gate-test-pending",
            "confirm_authorized": True,
        },
    )
    assert pending_scope.status_code == 403
    assert pending_scope.json()["error"]["code"] == "authorization_required"

    outside_scope = await client.post(
        f"{API}/companies/{company}/scans",
        headers=headers,
        json={
            "scan_type": "passive_dns",
            "targets": ["not-owned.example"],
            "name": "gate-test-outside",
            "confirm_authorized": True,
        },
    )
    assert outside_scope.status_code == 403

    scans = await client.get(f"{API}/companies/{company}/scans", headers=headers, params={"page_size": 100})
    names = {scan["name"] for scan in scans.json()["items"]}
    assert "gate-test-pending" not in names
    assert "gate-test-outside" not in names


async def test_unimplemented_scan_type_is_rejected_not_simulated(client):
    headers = await login(client, "analyst@northwind.example")
    company = await company_id_for(client, headers, "northwind")

    response = await client.post(
        f"{API}/companies/{company}/scans",
        headers=headers,
        json={
            "scan_type": "cloud_inventory",
            "targets": ["northwind.example"],
            "confirm_authorized": True,
        },
    )
    assert response.status_code == 422
    assert "not implemented" in response.json()["error"]["message"].lower()


async def test_offline_mode_blocks_active_probes(client):
    headers = await login(client, "analyst@northwind.example")
    company = await company_id_for(client, headers, "northwind")

    response = await client.post(
        f"{API}/companies/{company}/scans",
        headers=headers,
        json={
            "scan_type": "tls_certificate",
            "targets": ["northwind.example"],
            "confirm_authorized": True,
        },
    )
    assert response.status_code == 422
    assert "disabled" in response.json()["error"]["message"].lower()


async def test_auditor_cannot_request_scans(client):
    headers = await login(client, "auditor@meridian.example")
    company = await company_id_for(client, headers, "meridian-health")

    response = await client.post(
        f"{API}/companies/{company}/scans",
        headers=headers,
        json={"scan_type": "passive_dns", "targets": ["meridianhealth.example"], "confirm_authorized": True},
    )
    assert response.status_code == 403
