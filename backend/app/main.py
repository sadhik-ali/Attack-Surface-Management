"""FastAPI application factory.

Cross-cutting concerns are installed here once: request identity, rate limiting,
CORS, error envelopes, structured logging and health checks.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import RateLimitedError, install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.db.session import create_schema, dispose_engine, ping_database

logger = get_logger("asm.api")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, logs one structured line per request, and enforces
    a coarse per-IP rate limit.

    The limiter is in-process and therefore per-worker: it is a safety valve
    against accidental client loops, not a substitute for a gateway-level limit.
    """

    def __init__(self, app, *, limit: int, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()

        if settings.rate_limit_enabled and request.url.path not in {"/health", "/health/ready"}:
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            bucket = self.hits[client]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests. Slow down and retry.",
                            "details": None,
                            "request_id": request_id,
                        }
                    },
                    headers={"Retry-After": str(self.window)},
                )
            bucket.append(now)

        try:
            response = await call_next(request)
        except RateLimitedError as exc:  # pragma: no cover - defensive
            return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "request_id": request_id}})

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        if request.url.path not in {"/health", "/health/ready"}:
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO", json_output=settings.app_env != "development")
    logger.info(
        "starting api",
        extra={"env": settings.app_env, "backend": settings.backend, "docs": "/docs"},
    )
    if settings.auto_create_schema and settings.is_sqlite:
        # Dev/demo convenience. Production requires `alembic upgrade head`.
        await create_schema()
    yield
    await dispose_engine()
    logger.info("api stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Multi-tenant Attack Surface Management API. Enforces tenant isolation and "
            "role-based authorization on every endpoint; discovery runs require a live, "
            "in-scope authorization record."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    app.add_middleware(RequestContextMiddleware, limit=settings.rate_limit_requests_per_minute)

    install_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    async def health() -> dict:
        return {"status": "ok", "service": "asm-api", "version": app.version, "environment": settings.app_env}

    @app.get("/health/ready", tags=["Health"], summary="Readiness probe (checks database)")
    async def ready() -> JSONResponse:
        ok = await ping_database()
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ready" if ok else "degraded", "database": "up" if ok else "down", "backend": settings.backend},
        )

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"name": settings.app_name, "docs": "/docs", "api": settings.api_prefix}

    return app


app = create_app()
