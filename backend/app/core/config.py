"""Application settings.

Single source of truth for runtime configuration. Values come from environment
variables (or a local `.env` file during development) and are validated at
import time so a misconfigured process fails fast instead of degrading silently.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DatabaseBackend = Literal["sqlite", "postgresql"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ASM_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application -------------------------------------------------------
    app_name: str = "Attack Surface Management"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_prefix: str = "/api/v1"
    debug: bool = False

    # --- database ----------------------------------------------------------
    # Dev/demo runs on SQLite (aiosqlite); production runs on PostgreSQL.
    # Migrations are written once against SQLAlchemy Core and apply to both.
    database_url: str = "sqlite+aiosqlite:///./asm.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    auto_create_schema: bool = True  # create_all on boot when no migrations exist (SQLite dev)

    # --- auth --------------------------------------------------------------
    secret_key: str = Field(
        default="dev-only-insecure-secret-change-me",
        description="Signs access tokens. MUST be replaced outside development.",
    )
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_minutes: int = 60 * 24 * 14
    jwt_algorithm: str = "HS256"
    password_iterations: int = 600_000
    login_max_failed_attempts: int = 8
    login_lockout_minutes: int = 15

    # --- http --------------------------------------------------------------
    cors_origins: str = "http://localhost:5180,http://127.0.0.1:5180"
    api_port: int = 8010
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 600

    # --- discovery / scanning ---------------------------------------------
    # Active probing is deliberately constrained: an unauthorized or runaway
    # scan against third-party infrastructure is both a legal and an
    # availability problem, so limits are enforced in code rather than docs.
    discovery_enabled: bool = True
    discovery_offline: bool = Field(
        default=False,
        description="Force passive resolution only and block all outbound probes.",
    )
    dns_timeout_seconds: float = 4.0
    tls_timeout_seconds: float = 6.0
    http_timeout_seconds: float = 8.0
    scan_max_concurrency: int = 8
    scan_requests_per_second: float = 4.0
    scan_max_targets_per_run: int = 250
    scan_default_ports: str = "21,22,23,25,53,80,110,143,443,445,3389,5432,5984,6379,8080,8443,9200,27017"

    certificate_expiry_warning_days: int = 30
    certificate_expiry_critical_days: int = 7

    # --- data retention ----------------------------------------------------
    scan_result_retention_days: int = 365
    audit_log_retention_days: int = 730

    # --- background jobs ---------------------------------------------------
    # "in-process" runs jobs on the API event loop (no Redis needed);
    # "celery" publishes to the Redis broker used by docker-compose.
    job_backend: Literal["in-process", "celery"] = "in-process"
    redis_url: str = "redis://localhost:6379/0"

    # --- demo / sample data ------------------------------------------------
    demo_mode: bool = True
    demo_data_label: str = "Sample data"

    @field_validator("secret_key")
    @classmethod
    def _reject_default_secret_in_production(cls, v: str, info) -> str:
        if info.data.get("app_env") == "production" and v.startswith("dev-only"):
            raise ValueError("ASM_SECRET_KEY must be set to a strong random value in production")
        return v

    @property
    def backend(self) -> DatabaseBackend:
        return "postgresql" if "postgres" in self.database_url else "sqlite"

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def default_scan_ports(self) -> list[int]:
        return sorted({int(p) for p in self.scan_default_ports.split(",") if p.strip()})


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
