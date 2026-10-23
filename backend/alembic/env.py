"""Alembic environment for the ASM backend (async engine, SQLite + PostgreSQL).

Two rules define how this project migrates:

1. The database URL never lives in `alembic.ini`. It is injected here from
   `app.core.config.settings.database_url`, so `alembic` and the running app can
   never be pointed at different databases by accident.
2. The emitted DDL must be identical on SQLite (dev) and PostgreSQL (prod).
   That is handled by the model layer (`app/db/base.py`: char(36) UUID primary
   keys, non-native enums, JSON-with-JSONB-variant) plus `render_as_batch` here,
   which makes SQLite column changes work through Alembic's batch (recreate)
   recipe instead of the unsupported `ALTER COLUMN`.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool, types as sqltypes
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402  (import order is deliberate)
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401  registers all 27 tables on Base.metadata

config = context.config

# Alembic reads the URL from the ini interpolation, so '%' must be doubled
# (a password can legitimately contain '%').
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _is_json_with_postgres_variant(type_: sqltypes.TypeEngine) -> bool:
    """True for `json_type()` columns: JSON with a PostgreSQL JSONB variant."""
    variants = getattr(type_, "_variant_mapping", {})
    return any(isinstance(v, postgresql.JSONB) for v in variants.values())


def _render_type_decorator(obj: sqltypes.TypeDecorator) -> str:
    """Collapse a custom TypeDecorator onto its impl.

    A revision file is a frozen record of a schema change; if it renders
    `app.db.base.UTCDateTime()` it stops working the moment that class moves or
    changes, and old deployments can no longer upgrade. `UTCDateTime` has the
    exact same DDL as `sa.DateTime` (it only normalises values in Python), so the
    migration is rendered against the impl type.
    """
    impl = obj.impl_instance
    if isinstance(impl, sqltypes.DateTime):
        return f"sa.DateTime(timezone={impl.timezone!r})"
    return f"sa.{type(impl).__name__}()"


def render_item(type_, obj, autogen_context):
    """Keep generated DDL portable and free of application imports.

    Without this hook Alembic renders `sa.Enum(<enum AssetType>)` (a repr of a
    Python class that is not valid migration code and would tie a frozen
    revision to live model imports), `app.db.base.UTCDateTime()` (same problem),
    and `postgresql.JSONB(astext_type=Text())` (a bare `Text` name that is never
    imported, so the revision raises NameError on upgrade).
    """
    if type_ == "type":
        if isinstance(obj, sqltypes.Enum):
            args = ", ".join(repr(value) for value in obj.enums)
            # `create_constraint` is copied from the model rather than forced
            # off: today the models use SQLAlchemy's default (False), but a
            # future column that opts into a CHECK must not be silently
            # downgraded in the frozen revision.
            return (
                f"sa.Enum({args}, name={obj.name!r}, native_enum=False, "
                f"create_constraint={obj.create_constraint!r})"
            )

        if _is_json_with_postgres_variant(obj):
            autogen_context.imports.add("import sqlalchemy.dialects.postgresql as postgresql")
            return "sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')"

        if isinstance(obj, sqltypes.TypeDecorator):
            return _render_type_decorator(obj)

    # default rendering for everything else (tables, indexes, constraints,
    # scalars) so the generated file stays reviewable.
    return False


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Limit autogenerate to application objects.

    The 27 model tables all live in the connection's default schema, so
    `include_schemas=False` below is correct. Alembic's own version table (and
    SQLite's internal sequence table) are not part of the model metadata and
    must never be emitted as schema changes.
    """
    if type_ == "table" and name in {"alembic_version", "sqlite_sequence"}:
        return False
    return True


def configure(context_obj, **extra):
    context_obj.configure(
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite cannot ALTER columns; batch mode recreates the table instead.
        # Batch-issued operations are also valid on PostgreSQL, where they
        # degrade to plain ALTER/CREATE INDEX statements.
        render_as_batch=settings.is_sqlite,
        render_item=render_item,
        include_object=include_object,
        include_schemas=False,
        # Server defaults are rendered dialect-specifically (`CURRENT_TIMESTAMP`
        # vs `now()`), so comparing them would produce permanent false diffs.
        compare_server_default=False,
        **extra,
    )
    with context_obj.begin_transaction():
        context_obj.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade --sql`)."""
    url = config.get_main_option("sqlalchemy.url")
    configure(
        context,
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )


def do_run_migrations(connection: Connection) -> None:
    configure(context, connection=connection)


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
