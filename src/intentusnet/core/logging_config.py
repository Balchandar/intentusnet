from __future__ import annotations

import json
import logging
import sys
from typing import Optional

from .settings import get_settings


class JsonLogFormatter(logging.Formatter):
    """
    Very simple JSON log formatter.

    Produces log lines like:
    {"level":"INFO","name":"intentusnet.router","msg":"...","extra":{...}}
    """

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra attributes if present
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in ("args", "msg", "levelname", "levelno", "exc_info", "exc_text", "stack_info", "created", "msecs",
                       "relativeCreated", "thread", "threadName", "processName", "process", "name"):
                continue
            base[key] = value

        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(base, ensure_ascii=False)


def configure_logging(explicit_level: Optional[str] = None) -> None:
    """
    Configure root logging according to settings.runtime.log_level
    and settings.runtime.trace_sink / preferences.

    Call once at app startup (e.g. in main or __init__).
    """
    settings = get_settings()

    level_str = explicit_level or settings.runtime.log_level
    level = getattr(logging, level_str.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove default handlers (if any)
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)

    # Simple heuristic: if trace_sink == "stdout-json", use JSON logs
    if settings.runtime.trace_sink.lower() in ("stdout-json", "json"):
        formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)
