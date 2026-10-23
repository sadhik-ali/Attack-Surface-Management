"""Authentication primitives: password hashing and JWT issuing.

Password hashing uses PBKDF2-HMAC-SHA256 from the standard library. Rationale:
it needs no native extension (so `pip install` cannot fail on a locked-down or
TLS-inspecting corporate machine), it is the same construction Django ships as
its default, and the iteration count is configurable. To move to Argon2id,
install `argon2-cffi` and swap the bodies of `hash_password` / `verify_password`
— the stored format is versioned, so old hashes keep verifying after a swap.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt

from app.core.config import settings

_ALGORITHM = "pbkdf2_sha256"
_TokenType = Literal["access", "refresh"]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    """Return a versioned, self-describing PBKDF2 digest: algo$iterations$salt$hash."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, settings.password_iterations)
    return f"{_ALGORITHM}${settings.password_iterations}${_b64(salt)}${_b64(digest)}"


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    # Cap input length: PBKDF2 cost grows with the password, so an unbounded
    # input lets a caller force disproportionate CPU work per login attempt.
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8")[:1024], salt, iterations)


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    candidate = _derive(password, base64.b64decode(salt), int(iterations))
    return hmac.compare_digest(_b64(candidate), expected)


def create_token(
    subject: str,
    token_type: _TokenType = "access",
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    ttl = expires_delta or timedelta(
        minutes=settings.access_token_ttl_minutes if token_type == "access" else settings.refresh_token_ttl_minutes
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": secrets.token_urlsafe(16),
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: _TokenType | None = None) -> dict[str, Any]:
    """Decode and validate a token. Raises `jwt.PyJWTError` on any problem."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
    return payload


def generate_public_id(prefix: str = "") -> str:
    """Short, URL-safe identifier for human-readable references (scopes, jobs)."""
    return f"{prefix}{secrets.token_urlsafe(9)}" if prefix else secrets.token_urlsafe(9)


def generate_api_token() -> str:
    return f"asm_{secrets.token_urlsafe(32)}"
