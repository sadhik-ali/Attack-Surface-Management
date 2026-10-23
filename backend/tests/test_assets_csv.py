"""CSV inventory import: validation, dry run, idempotent re-import."""

from __future__ import annotations

from tests.conftest import API, company_id_for, login

CSV_BODY = (
    "name,type,criticality,exposure,owner\n"
    "qa-import-a.example,domain,medium,internet_facing,QA\n"
    "qa-import-b.example,domain,high,partner_facing,QA\n"
    "not-a-type.example,spaceship,low,internet_facing,QA\n"
)


async def test_csv_import_dry_run_then_commit(client):
    headers = await login(client, "analyst@northwind.example")
    company = await company_id_for(client, headers, "northwind")

    dry = await client.post(
        f"{API}/companies/{company}/assets/import?dry_run=true",
        headers=headers,
        files={"file": ("inventory.csv", CSV_BODY, "text/csv")},
    )
    assert dry.status_code == 200, dry.text
    assert dry.json() == {
        "total_rows": 3,
        "created": 2,
        "updated": 0,
        "skipped": 0,
        "errors": dry.json()["errors"],
        "dry_run": True,
    }
    assert len(dry.json()["errors"]) == 1
    assert dry.json()["errors"][0]["row"] == 4

    committed = await client.post(
        f"{API}/companies/{company}/assets/import",
        headers=headers,
        files={"file": ("inventory.csv", CSV_BODY, "text/csv")},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["created"] == 2
    assert committed.json()["dry_run"] is False

    listing = await client.get(
        f"{API}/companies/{company}/assets",
        headers=headers,
        params={"q": "qa-import", "page_size": 100},
    )
    assert listing.status_code == 200
    names = {item["name"] for item in listing.json()["items"]}
    assert names == {"qa-import-a.example", "qa-import-b.example"}

    again = await client.post(
        f"{API}/companies/{company}/assets/import",
        headers=headers,
        files={"file": ("inventory.csv", CSV_BODY, "text/csv")},
    )
    assert again.status_code == 200
    assert again.json()["created"] == 0
    assert again.json()["updated"] == 2


async def test_csv_import_rejects_missing_columns(client):
    headers = await login(client, "analyst@northwind.example")
    company = await company_id_for(client, headers, "northwind")

    response = await client.post(
        f"{API}/companies/{company}/assets/import",
        headers=headers,
        files={"file": ("wrong.csv", "hostname,owner\nfoo.example,QA\n", "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_read_only_auditor_cannot_import(client):
    headers = await login(client, "auditor@meridian.example")
    company = await company_id_for(client, headers, "meridian-health")

    response = await client.post(
        f"{API}/companies/{company}/assets/import",
        headers=headers,
        files={"file": ("inventory.csv", CSV_BODY, "text/csv")},
    )
    assert response.status_code == 403
