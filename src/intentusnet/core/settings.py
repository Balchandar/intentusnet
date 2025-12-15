"""
Central configuration for IntentusNet.

Deliberately minimal:
- No schema enforcement
- No automatic coercion
- Explicit defaults
- Environment-driven only

This avoids heavy config dependencies in the runtime core.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, List


def _bool(env: str, default: bool = False) -> bool:
    v = os.getenv(env)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _int(env: str, default: int) -> int:
    try:
        return int(os.getenv(env, default))
    except ValueError:
        return default


def _list(env: str) -> List[str]:
    v = os.getenv(env)
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


# --------------------------------------------------
# Settings models (plain dataclasses)
# --------------------------------------------------

@dataclass(frozen=True)
class EMCLSettings:
    enabled: bool
    mode: str
    key: str


@dataclass(frozen=True)
class RuntimeSettings:
    trace_sink: str
    log_level: str
    max_worker_threads: int


@dataclass(frozen=True)
class IntentusSettings:
    emcl: EMCLSettings
    runtime: RuntimeSettings
    enabled_middlewares: List[str]


# --------------------------------------------------
# Loader
# --------------------------------------------------

@lru_cache(maxsize=1)
def get_settings() -> IntentusSettings:
    return IntentusSettings(
        emcl=EMCLSettings(
            enabled=_bool("INTENTUSNET_EMCL_ENABLED", False),
            mode=os.getenv("INTENTUSNET_EMCL_MODE", "aes-gcm"),
            key=os.getenv("INTENTUSNET_EMCL_KEY", ""),
        ),
        runtime=RuntimeSettings(
            trace_sink=os.getenv("INTENTUSNET_TRACE_SINK", "memory"),
            log_level=os.getenv("INTENTUSNET_LOG_LEVEL", "INFO"),
            max_worker_threads=_int("INTENTUSNET_MAX_WORKER_THREADS", 8),
        ),
        enabled_middlewares=_list("INTENTUSNET_MIDDLEWARES"),
    )
