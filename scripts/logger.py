"""Structured logging for OpsClaw runtime utilities."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "refresh_token",
    "access_token",
    "api_key",
    "client_secret",
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if key.lower() in SENSITIVE_KEYS else _sanitize(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Render logs as newline-delimited JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _utc_timestamp(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = _sanitize(record.event)
        if hasattr(record, "correlation_id"):
            payload["correlationId"] = record.correlation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logger(name: str = "opsclaw", level: int = logging.INFO) -> logging.Logger:
    """Create or update a logger configured for JSON output."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.handlers.clear()
        logger.addHandler(handler)

    return logger


def get_logger(name: str = "opsclaw") -> logging.Logger:
    """Return a configured logger, creating one if needed."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return configure_logger(name)
    return logger
