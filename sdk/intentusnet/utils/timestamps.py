"""
Timestamp utilities used across IntentusNet:
- ISO-8601 timestamp generator
- UTC datetime helpers
- Monotonic millisecond timer (for latency)
"""

from __future__ import annotations
import datetime as _dt
import time


def utc_now() -> _dt.datetime:
    """Return a timezone-aware UTC datetime."""
    return _dt.datetime.now(tz=_dt.timezone.utc)


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with Z suffix."""
    return utc_now().isoformat().replace("+00:00", "Z")


def monotonic_ms() -> int:
    """
    Returns a monotonic millisecond counter.
    Useful for measuring latency independent of system clock changes.
    """
    return int(time.monotonic() * 1000)
