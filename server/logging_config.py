"""Structured logging configuration for TALK."""

from __future__ import annotations

import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from server.db import LOG_LEVEL, LOG_PATH

_ROOT_DIR = Path(__file__).resolve().parent.parent


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    _skip_fields = {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
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

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in self._skip_fields:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Configure root logging once with JSON file + console handlers."""
    root_logger = logging.getLogger()
    if getattr(root_logger, "_talk_logging_configured", False):
        return

    log_path = LOG_PATH if LOG_PATH.is_absolute() else (_ROOT_DIR / LOG_PATH)
    log_path = log_path.resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = JsonFormatter()
    level = getattr(logging, LOG_LEVEL, logging.INFO)

    file_handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger._talk_logging_configured = True  # type: ignore[attr-defined]
