"""Authentication, RBAC and tenant-isolation tests."""

from __future__ import annotations

from tests.conftest import API, company_id_for, login


async def test_health_reports_database(client):
    live = await client.get("/health")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "up"


async def test_login_returns_identity_without_secrets(client):
    response = await client.post(
        f"{API}/auth/login",
        json={"email": "admin@northwind.example", "password": "AsmDemo!2026"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "admin@northwind.example"
    assert "hashed_password" not in response.text
    assert body["permissions"]

    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert [company["slug"] for company in me.json()["companies"]] == ["northwind"]


async def test_wrong_password_is_rejected(client):
    response = await client.post(
        f"{API}/auth/login",
        json={"email": "admin@northwind.example", "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_tenant_isolation_returns_404_not_403(client):
    headers = await login(client, "auditor@meridian.example")
    northwind = "d3b2d1714b05497c9b4e3054a7a7b272"

    cross = await client.get(f"{API}/companies/{northwind}/assets", headers=headers)
    assert cross.status_code == 404
    assert cross.json()["error"]["code"] == "not_found"

    meridian = await company_id_for(client, headers, "meridian-health")
    own = await client.get(f"{API}/companies/{meridian}/assets", headers=headers)
    assert own.status_code == 200
    for item in own.json()["items"]:
        assert item["company_id"] == meridian


async def test_read_only_auditor_cannot_write_assets(client):
    headers = await login(client, "auditor@meridian.example")
    meridian = await company_id_for(client, headers, "meridian-health")

    read = await client.get(f"{API}/companies/{meridian}/assets", headers=headers)
    assert read.status_code == 200

    write = await client.post(
        f"{API}/companies/{meridian}/assets",
        headers=headers,
        json={"name": "forbidden-write.example", "asset_type": "domain"},
    )
    assert write.status_code == 403
    assert write.json()["error"]["code"] == "forbidden"


async def test_platform_directory_is_super_admin_only(client):
    analyst = await login(client, "analyst@northwind.example")
    denied = await client.get(f"{API}/users", headers=analyst)
    assert denied.status_code == 403

    admin = await login(client, "admin@northwind.example")
    admin_denied = await client.get(f"{API}/users", headers=admin)
    assert admin_denied.status_code == 403

    platform = await login(client, "platform@asm.example")
    allowed = await client.get(f"{API}/users", headers=platform)
    assert allowed.status_code == 200

    # Company admins manage members through the tenant-scoped endpoint instead.
    northwind = await company_id_for(client, admin, "northwind")
    members = await client.get(f"{API}/companies/{northwind}/members", headers=admin)
    assert members.status_code == 200
    assert members.json()


async def test_four_eyes_blocks_self_approval(client):
    headers = await login(client, "admin@northwind.example")
    company = await company_id_for(client, headers, "northwind")

    records = await client.get(f"{API}/companies/{company}/authorizations", headers=headers)
    assert records.status_code == 200
    pending = next(record for record in records.json() if record["status"] == "pending")

    decision = await client.post(
        f"{API}/companies/{company}/authorizations/{pending['id']}/decision",
        headers=headers,
        json={"decision": "approved"},
    )
    assert decision.status_code == 422
    assert "different administrator" in decision.json()["error"]["message"]

    after = await client.get(f"{API}/companies/{company}/authorizations", headers=headers)
    unchanged = next(record for record in after.json() if record["id"] == pending["id"])
    assert unchanged["status"] == "pending"


async def test_invalid_token_is_rejected(client):
    response = await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401
