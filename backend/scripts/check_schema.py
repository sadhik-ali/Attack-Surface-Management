"""Verify the ORM: every mapper configures and the DDL actually applies.

Run with `python scripts/check_schema.py`. Catching a broken `back_populates` or
an unapplicable column type here is much cheaper than discovering it on the
first API request.

The database URL is pinned to a throwaway temp file *before* `app.core.config`
is imported, because the engine is constructed at import time.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_TMP = tempfile.mktemp(suffix=".db")
os.environ["ASM_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}"
os.environ["ASM_AUTO_CREATE_SCHEMA"] = "false"


async def main() -> int:
    from sqlalchemy.orm import configure_mappers

    from app.core.config import settings
    from app.core.security import hash_password
    from app.db.base import Base
    import app.models  # noqa: F401
    from app.db.session import create_schema, dispose_engine, session_scope
    from app.models import Asset, AuthorizationRecord, Company, ScanPolicy, User
    from app.models.enums import (
        AssetType,
        AuthorizationScopeType,
        AuthorizationStatus,
        RecordSource,
        RoleCode,
    )

    print(f"checking against {settings.database_url}")
    configure_mappers()
    print(f"mappers configured: {len(Base.registry.mappers)} classes")

    await create_schema()
    print(f"DDL applied on {settings.backend}: {len(Base.metadata.tables)} tables")

    # Insert one row per core table to prove FKs, CHECK constraints and
    # defaults are coherent on the live backend, not just in metadata.
    async with session_scope() as session:
        company = Company(name="Schema Check Ltd", slug="schema-check", root_domains=["example.com"])
        session.add(company)
        await session.flush()

        admin = User(
            email="check@example.com",
            full_name="Schema Check",
            hashed_password=hash_password("Strongsentinel1!"),
            role_code=RoleCode.SUPER_ADMIN.value,
        )
        session.add(admin)
        await session.flush()

        session.add(
            AuthorizationRecord(
                company_id=company.id,
                scope_type=AuthorizationScopeType.DOMAIN.value,
                value="example.com",
                status=AuthorizationStatus.APPROVED.value,
                verified_by_id=admin.id,
                allow_active_probing=True,
            )
        )
        session.add(ScanPolicy(company_id=company.id, allowed_ports=[443, 80]))
        session.add(
            Asset(
                company_id=company.id,
                name="www.example.com",
                normalized_identifier="domain:www.example.com",
                asset_type=AssetType.DOMAIN.value,
                source=RecordSource.SEED.value,
            )
        )
        await session.flush()
        print("tenant insert/flush round-trip OK")

    await dispose_engine()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(_TMP + suffix)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
