"""Structured error handling.

All failure paths funnel through a small set of exception types so the API
always returns the same envelope, the frontend can react uniformly, and stack
traces never leak to a client.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logging import get_logger

logger = get_logger("asm.errors")


class AppError(Exception):
    """Base class for expected, client-visible failures."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, details: Any = None, status_code: int | None = None, code: str | None = None) -> None:
        self.message = message
        self.details = details
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        super().__init__(message)


class ValidationError_(AppError):  # noqa: N818 - distinct from pydantic's ValidationError
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"

    def __init__(self, message: str = "Authentication required", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"

    def __init__(self, message: str = "You do not have permission to perform this action", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"

    def __init__(self, message: str = "Resource not found", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class ScanAuthorizationError(AppError):
    """Raised when a scan is requested without a valid, in-scope authorization."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "authorization_required"


def error_envelope(exc: AppError | Exception, request_id: str) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        }
    return {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred. Refer to the request id when contacting support.",
            "details": None,
            "request_id": request_id,
        }
    }


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        rid = _request_id(request)
        if exc.status_code >= 500:
            logger.exception("server error", extra={"request_id": rid, "code": exc.code, "message": exc.message})
        return JSONResponse(status_code=exc.status_code, content=error_envelope(exc, rid))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = _request_id(request)
        # `ctx` can contain the raw input value; strip it before serialising so
        # a rejected password or token is never echoed into a response/log.
        safe = [
            {
                "loc": [str(part) for part in item.get("loc", [])],
                "msg": item.get("msg"),
                "type": item.get("type"),
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "validation_error", "message": "Request validation failed", "details": safe, "request_id": rid}},
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        rid = _request_id(request)
        logger.warning("database integrity violation", extra={"request_id": rid, "type": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": {"code": "conflict", "message": "This record conflicts with an existing entry (duplicate or broken reference).", "details": None, "request_id": rid}},
        )

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        rid = _request_id(request)
        logger.exception("database failure", extra={"request_id": rid, "type": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": "database_unavailable", "message": "The database is temporarily unavailable.", "details": None, "request_id": rid}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = _request_id(request)
        logger.exception("unhandled exception", extra={"request_id": rid, "type": type(exc).__name__})
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_envelope(exc, rid))
