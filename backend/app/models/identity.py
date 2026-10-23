"""Identity: users, roles, tenant memberships and the audit trail."""

from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column, json_type, utcnow, UTCDateTime
from app.models.enums import AuditAction, AuditOutcome, NotificationChannel, RoleCode, Severity


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant_scoped: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def has(self, permission: str) -> bool:
        return permission in (self.permissions or [])


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(150))
    hashed_password: Mapped[str] = mapped_column(String(300), nullable=False)
    # Platform-level role. For non-admins the effective role comes from the
    # company membership; see `User.effective_role_code`.
    role_code: Mapped[str] = mapped_column(enum_column(RoleCode), default=RoleCode.READ_ONLY_AUDITOR, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    avatar_color: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(60), default="UTC", nullable=False)

    memberships = relationship(
        "CompanyMembership", back_populates="user", cascade="all, delete-orphan", foreign_keys="CompanyMembership.user_id"
    )

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow()

    @property
    def is_super_admin(self) -> bool:
        return self.role_code == RoleCode.SUPER_ADMIN.value

    def effective_role_code(self, company_id: str | None) -> str:
        """Role used for authorization against a specific tenant.

        A super admin keeps that role everywhere; everyone else is governed by
        their membership for the company being touched. No membership means no
        effective role, which downstream resolves to zero permissions.
        """
        if self.is_super_admin:
            return RoleCode.SUPER_ADMIN.value
        if company_id is None:
            return ""
        for membership in self.memberships:
            if membership.company_id == company_id and membership.is_active:
                return membership.role_code
        return ""

    def accessible_company_ids(self) -> set[str]:
        if self.is_super_admin:
            return set()  # empty means "not restricted"; callers check is_super_admin first
        return {m.company_id for m in self.memberships if m.is_active}


class CompanyMembership(TenantMixin, Base):
    """Grants a user a role inside exactly one company."""

    __tablename__ = "company_memberships"
    __table_args__ = (Index("uq_membership_user_company", "user_id", "company_id", unique=True),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(enum_column(RoleCode), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    user = relationship("User", back_populates="memberships", foreign_keys=[user_id])
    company = relationship("Company", back_populates="memberships")


class AlertPreference(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-user notification routing and suppression."""

    __tablename__ = "alert_preferences"
    __table_args__ = (Index("ix_alert_pref_user_company", "user_id", "company_id", unique=True),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id", ondelete="CASCADE"))
    min_severity: Mapped[str] = mapped_column(enum_column(Severity), default=Severity.LOW, nullable=False)
    channels: Mapped[list] = mapped_column(json_type(), default=lambda: [NotificationChannel.IN_APP.value], nullable=False)
    muted_types: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    daily_digest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only record of sensitive operations.

    Deliberately has no FK cascade on `company_id`: an audit entry must survive
    the deletion of the company it describes.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_company_created", "company_id", "created_at"),
        Index("ix_audit_action_created", "action", "created_at"),
    )

    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("companies.id", ondelete="SET NULL"), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(320))
    actor_role: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(enum_column(AuditAction), nullable=False)
    outcome: Mapped[str] = mapped_column(enum_column(AuditOutcome), default=AuditOutcome.SUCCESS, nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(60))
    object_id: Mapped[str | None] = mapped_column(String(36))
    object_label: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(60))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    request_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[dict | None] = mapped_column(json_type())
    # Secrets are never stored here; only the *name* of a rotated credential.
    redacted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


def register_login_failure(user: User, max_attempts: int, lockout_minutes: int) -> bool:
    """Increment the failure counter and lock the account past the threshold.

    Returns whether the account is now locked, so the caller can log the state
    change without re-deriving it.
    """
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= max_attempts:
        user.locked_until = utcnow() + timedelta(minutes=lockout_minutes)
        return True
    return False


def clear_login_failures(user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
