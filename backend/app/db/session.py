"""Session and engine management.

One async engine per process. SQLite (dev) and PostgreSQL (prod) differ in two
ways that have to be handled explicitly here:
  * SQLite needs `check_same_thread=False` and has a single-writer lock;
  * SQLite does not enable foreign key enforcement by default, and this schema
    relies on it for tenant isolation, so it is switched on per connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base
from app.models import *  # noqa: F401,F403  - register every mapper before create_all

logger = get_logger("asm.db")


def _build_engine() -> AsyncEngine:
    url = settings.database_url
    kwargs: dict = {"echo": bool(settings.debug and settings.app_env != "test")}

    if settings.is_sqlite:
        # A file-backed SQLite database shared across threads/connections.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        kwargs["poolclass"] = NullPool
    else:
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow

    return create_async_engine(url, **kwargs)


engine = _build_engine()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@event.listens_for(engine.sync_engine, "connect")
def _on_connect(dbapi_connection, _record) -> None:
    """Enforce FKs and use WAL on SQLite; set a statement timeout on Postgres."""
    if settings.is_sqlite:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
    else:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET timezone = 'UTC'")
        cursor.execute("SET statement_timeout = '30s'")
        cursor.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session.

    Commit on success, roll back on any exception, so a half-applied write can
    never be persisted because a route forgot to commit.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Same contract as `get_session` for jobs and scripts outside a request."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping_database() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("database health check failed", extra={"reason": str(exc)})
        return False


async def create_schema() -> None:
    """Create tables from metadata.

    Used for the SQLite demo path and tests. Production deployments run
    `alembic upgrade head` instead; the migration and the metadata are kept in
    sync because both derive from the same model definitions.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("schema ensured", extra={"backend": settings.backend, "tables": len(Base.metadata.tables)})


async def drop_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def dispose_engine() -> None:
    await engine.dispose()
