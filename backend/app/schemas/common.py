"""Shared response shapes: pagination, enums and provenance labels."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

T = TypeVar("T")

#: Accepts any syntactically valid address. Deliberately not `EmailStr`:
#: email-validator rejects reserved demo domains such as `example.com` and
#: `*.test`, which would make seeded demonstration accounts unable to sign in.
EmailLike = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=320,
        pattern=r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$",
    ),
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = max(1, -(-total // page_size)) if page_size else 1
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class MessageResponse(BaseModel):
    message: str


class Filters(BaseModel):
    search: str | None = Field(default=None, max_length=200)


class EnumOption(BaseModel):
    value: str
    label: str


class ProvenanceInfo(BaseModel):
    """Tells the UI whether a record is observed live, entered by a human, or sample data.

    The product must not present seeded fixtures as live scan output, so every
    list endpoint carries this per row and every page surfaces it.
    """

    source: str
    label: str
    is_simulated: bool
    is_observed: bool


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    informational: int = 0

    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.low + self.informational


class TrendPoint(BaseModel):
    date: str
    value: float


class TimeSeriesPoint(BaseModel):
    date: str
    label: str
    value: float


class AuditRef(BaseModel):
    id: str
    email: str | None = None
    full_name: str | None = None


def provenance_for(source: str) -> ProvenanceInfo:
    from app.models.enums import OBSERVED_SOURCES, RecordSource

    if source in OBSERVED_SOURCES:
        return ProvenanceInfo(source=source, label="Observed live", is_simulated=False, is_observed=True)
    if source == RecordSource.SEED.value:
        return ProvenanceInfo(source=source, label="Sample data", is_simulated=True, is_observed=False)
    if source == RecordSource.CSV_IMPORT.value:
        return ProvenanceInfo(source=source, label="Imported CSV", is_simulated=False, is_observed=False)
    if source == RecordSource.MANUAL.value:
        return ProvenanceInfo(source=source, label="Manually registered", is_simulated=False, is_observed=False)
    return ProvenanceInfo(source=source, label=str(source).replace("_", " ").title(), is_simulated=False, is_observed=False)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: object | None = None
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class TimestampedModel(ORMModel):
    id: str
    created_at: datetime
    updated_at: datetime
