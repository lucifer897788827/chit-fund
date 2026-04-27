from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

APP_LOGGER_NAME = "app"
REDACTED_VALUE = "[REDACTED]"
SENSITIVE_LOG_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "password_hash",
    "jwt",
    "secret",
}

STANDARD_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def _prune_closed_stream_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        stream = getattr(handler, "stream", None)
        if stream is not None and getattr(stream, "closed", False):
            logger.removeHandler(handler)


def resolve_structured_logging(app_env: str, configured_value: bool | None) -> bool:
    if configured_value is not None:
        return configured_value
    return app_env.strip().lower() in {"production", "prod"}


def _is_sensitive_log_key(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in SENSITIVE_LOG_KEYS or normalized.endswith("_token") or normalized.endswith("_password")


def _coerce_json_safe(value: Any, key: Any | None = None) -> Any:
    if key is not None and _is_sensitive_log_key(key):
        return REDACTED_VALUE
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(item_key): _coerce_json_safe(item, item_key) for item_key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce_json_safe(item) for item in value]
    return str(value)


def build_log_payload(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }

    if record.exc_info:
        payload["exception"] = "".join(traceback.format_exception(*record.exc_info)).strip()

    extras = {
        key: _coerce_json_safe(value, key)
        for key, value in record.__dict__.items()
        if key not in STANDARD_LOG_RECORD_ATTRS and not key.startswith("_")
    }

    if "event" not in extras:
        extras["event"] = payload["message"]

    payload.update(extras)
    return payload


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(build_log_payload(record), separators=(",", ":"), default=_coerce_json_safe)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = build_log_payload(record)
        ordered_keys = [
            "timestamp",
            "level",
            "logger",
            "event",
            "job_name",
            "status",
            "task_id",
            "message",
            "request_id",
            "method",
            "path",
            "endpoint",
            "user_id",
            "success",
            "status_code",
            "duration_ms",
            "total_ms",
            "lockout_check_ms",
            "db_fetch_ms",
            "hash_verify_ms",
            "refresh_token_ms",
            "profile_fetch_ms",
            "jwt_ms",
            "commit_ms",
            "db_query_ms",
            "processing_ms",
            "threshold_ms",
            "metadata",
            "app_env",
            "exception",
        ]
        segments = [f"{key}={payload[key]}" for key in ordered_keys if key in payload]
        return " ".join(segments)


def log_job_event(
    logger: logging.Logger,
    *,
    event: str,
    job_name: str,
    status: str,
    task_id: str | None = None,
    duration_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
    level: int = logging.INFO,
    exc_info: bool | tuple[Any, Any, Any] | None = None,
) -> None:
    extra: dict[str, Any] = {
        "event": event,
        "job_name": job_name,
        "status": status,
    }
    if task_id is not None:
        extra["task_id"] = task_id
    if duration_ms is not None:
        extra["duration_ms"] = round(duration_ms, 2)
    if metadata is not None:
        extra["metadata"] = metadata

    _prune_closed_stream_handlers(logger)
    logger.log(level, event, exc_info=exc_info, extra=extra)


def configure_logging(
    *,
    app_env: str | None = None,
    structured_logging: bool | None = None,
    level: str | int | None = None,
) -> logging.Logger:
    resolved_app_env = app_env or settings.app_env
    resolved_structured_logging = resolve_structured_logging(resolved_app_env, structured_logging)
    resolved_level = level or settings.log_level
    if isinstance(resolved_level, int):
        resolved_level_value = resolved_level
    else:
        resolved_level_value = logging._nameToLevel.get(str(resolved_level).upper(), logging.INFO)

    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(resolved_level_value)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(resolved_level_value)
    handler.setFormatter(JsonFormatter() if resolved_structured_logging else PlainFormatter())
    logger.addHandler(handler)
    return logger
