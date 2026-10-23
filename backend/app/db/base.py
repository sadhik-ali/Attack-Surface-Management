"""Declarative base and shared column mixins.

The schema is portable across the SQLite development target and the PostgreSQL
production target:
  * primary keys are 36-char UUID strings rather than a dialect-specific UUID
    column, so dumps and fixtures behave identically on both;
  * JSON columns use `JSON` with a PostgreSQL `JSONB` variant;
  * autoincrement integer keys are avoided in favour of generated UUIDs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, JSON, ForeignKey, String, TypeDecorator, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def enum_column(enum_cls, constraint_name: str | None = None):
    """Persist an `StrEnum` as VARCHAR.

    `native_enum=False` is deliberate: PostgreSQL native enum types are
    schema-level objects that must be created and dropped in lockstep with
    migrations, and they do not exist in SQLite at all. A plain VARCHAR is
    portable and keeps migrations identical on both backends. The stored text
    is the member's public `value` (for example `internet_facing`), never its
    Python name, so raw SQL, exports and API responses all agree. Values are
    validated by Pydantic at the API boundary; SQLAlchemy does not emit a CHECK
    constraint for these columns unless `create_constraint=True` is passed,
    which is not used here.
    """
    return SAEnum(
        enum_cls,
        name=constraint_name or f"ck_{enum_cls.__name__.lower()}",
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


def json_type() -> JSON:
    """JSON that becomes JSONB (indexable, binary) on PostgreSQL."""
    return JSON().with_variant(JSONB, "postgresql")


def new_uuid() -> str:
    return uuid.uuid4().hex


class UTCDateTime(TypeDecorator):
    """Timezone-aware datetimes normalised to UTC.

    SQLite discards tzinfo, which would make expiry math silently wrong, so the
    value is coerced on the way in and re-stamped on the way out.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base for every ORM model."""


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), default=utcnow, onupdate=utcnow, nullable=False
    )


class TenantMixin(UUIDPrimaryKeyMixin, TimestampMixin):
    """Mixin for every row owned by exactly one company (tenant).

    `company_id` is non-nullable and indexed on purpose: tenant isolation is
    enforced by the query layer, and a nullable owner column is how rows
    silently escape their tenant.
    """

    __abstract__ = True

    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
