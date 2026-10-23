"""Structured logging with secret-safe formatting.

Every log line is JSON so it can be shipped to any aggregator, and all outbound
values pass through a redaction filter: credentials, tokens and integration
secrets must never reach a log sink even by accident.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

from pythonjsonlogger import jsonlogger

# Matches obvious secret material in both structured fields and free text.
_SECRET_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|session|"
    r"access[_-]?key|private[_-]?key|credential|client[_-]?secret|bearer)",
    re.IGNORECASE,
)
_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9\-._~+/=]{8,}"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\b(\s*[=:]\s*)\S+"),
)
_REDACTED = "***redacted***"


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (_REDACTED if _SECRET_KEY_PATTERN.search(str(k)) else _redact_value(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    if isinstance(value, str):
        for pattern in _VALUE_PATTERNS:
            value = pattern.sub(_REDACTED, value)
        return value
    return value


class RedactingJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        # Never emit the raw formatted message if it interpolates a secret.
        log_record["message"] = _redact_value(log_record.get("message", record.getMessage()))
        for key in list(log_record):
            log_record[key] = _redact_value(log_record[key])


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(
            RedactingJsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                json_ensure_ascii=False,
                timestamp=True,
            )
        )
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn ships its own handlers; drop them so everything is redacted.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine", "httpx", "asyncio"):
        logger = logging.getLogger(noisy)
        logger.handlers.clear()
        logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
