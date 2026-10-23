"""Test harness.

The application reads settings at import time, so the environment is pinned to a
throwaway SQLite file *before* importing `app`. One deterministic seed is shared
by the session; tests that mutate data use unique identifiers so ordering does
not matter.
"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TEST_DB = Path(__file__).resolve().parent / "test_asm.db"

os.environ.update(
    {
        "ASM_APP_ENV": "test",
        "ASM_DATABASE_URL": f"sqlite+aiosqlite:///{TEST_DB.as_posix()}",
        "ASM_AUTO_CREATE_SCHEMA": "false",
        "ASM_RATE_LIMIT_ENABLED": "false",
        "ASM_DISCOVERY_ENABLED": "true",
        "ASM_DISCOVERY_OFFLINE": "true",
        "ASM_SECRET_KEY": "test-only-secret-not-for-any-deployment",
        "ASM_PASSWORD_ITERATIONS": "1000",
    }
)

from app.db.session import create_schema, dispose_engine, session_scope  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import PASSWORD, _seed  # noqa: E402

API = "/api/v1"


def _remove_database() -> None:
    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{TEST_DB}{suffix}")
        if path.exists():
            path.unlink()


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    _remove_database()

    async def setup() -> None:
        await create_schema()
        async with session_scope() as session:
            await _seed(session, 2, random.Random(20261023), datetime.now(timezone.utc))

    asyncio.run(setup())
    yield
    asyncio.run(dispose_engine())
    _remove_database()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def company_id_for(client: AsyncClient, headers: dict[str, str], slug: str) -> str:
    response = await client.get(f"{API}/companies", headers=headers)
    assert response.status_code == 200, response.text
    for company in response.json():
        if company["slug"] == slug:
            return company["id"]
    raise AssertionError(f"company {slug} not visible to caller")
