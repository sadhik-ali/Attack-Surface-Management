"""Authentication and identity schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import EmailLike, ORMModel


class LoginRequest(BaseModel):
    email: EmailLike
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if not any(c.isupper() for c in value) or not any(c.islower() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Use at least one uppercase letter, one lowercase letter and one digit")
        return value


class MembershipOut(ORMModel):
    company_id: str
    company_name: str | None = None
    company_slug: str | None = None
    role_code: str
    role_name: str | None = None
    is_active: bool


class RoleOut(ORMModel):
    code: str
    name: str
    description: str | None = None
    permissions: list[str]
    tenant_scoped: bool


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    job_title: str | None = None
    role_code: str
    role_name: str | None = None
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    avatar_color: str | None = None
    timezone: str
    memberships: list[MembershipOut] = []
    created_at: datetime


class UserSummary(ORMModel):
    id: str
    email: str
    full_name: str
    role_code: str
    is_active: bool
    avatar_color: str | None = None


class UserCreateRequest(BaseModel):
    email: EmailLike
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=256)
    job_title: str | None = Field(default=None, max_length=150)
    role_code: str = Field(default="read_only_auditor")
    company_id: str | None = None
    send_temporary_password: bool = True


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    job_title: str | None = Field(default=None, max_length=150)
    role_code: str | None = None
    is_active: bool | None = None


class MembershipCreateRequest(BaseModel):
    user_id: str
    role_code: str


class CompanyAccessOut(BaseModel):
    company_id: str
    name: str
    slug: str
    role_code: str
    asset_count: int
    risk_score: float
    status: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    permissions: list[str]
    companies: list[CompanyAccessOut]


class MeResponse(BaseModel):
    user: UserOut
    permissions: list[str]
    companies: list[CompanyAccessOut]
    alert_counts: dict[str, int]
