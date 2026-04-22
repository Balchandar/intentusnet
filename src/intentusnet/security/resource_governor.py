"""
Security Kernel v2.1 — Resource Governor

Measures in-process resource consumption and checks it against a
``ResourceLimits`` spec.  In INPROCESS isolation mode the limits are
advisory: breaches are recorded and emitted as events but execution is
never killed.  In SUBPROCESS mode the limits are enforced by the OS via
``resource.setrlimit()`` inside the worker process (see isolation_manager.py);
this component still records post-hoc measurements for audit.

Resource measurement
--------------------
``ResourceGovernor.measure()`` is a pure static helper that takes a snapshot
of the *current process* using ``resource.getrusage(RUSAGE_SELF)`` (POSIX) or
a zero-filled fallback on platforms where the module is unavailable (Windows).
Open-file count is read from ``/proc/self/fd`` on Linux; a ``os.scandir``
based fallback is used elsewhere.

Thread safety
-------------
``check()`` is stateless with respect to instance state — it does not mutate
``self`` and may be called from any thread concurrently.  Event emissions go
through ``SecurityEventBus`` which is itself thread-safe.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .event_bus import SecurityEventBus, SecurityEventType
from .types import ExecutionIsolationMode, ResourceLimits


# ---------------------------------------------------------------------------
# Measurement snapshot
# ---------------------------------------------------------------------------

@dataclass
class ResourceMeasurement:
    """
    Point-in-time resource usage snapshot for the current process.

    All times are in seconds; memory is in bytes.  A value of ``-1`` means
    the metric was not available on this platform.
    """
    cpu_seconds:  float  = 0.0   # user + system CPU time
    memory_bytes: int    = 0     # RSS (best effort)
    open_files:   int    = 0     # open file descriptors
    wall_seconds: float  = 0.0   # elapsed wall time (caller-supplied)


# ---------------------------------------------------------------------------
# Breach record
# ---------------------------------------------------------------------------

@dataclass
class ResourceBreach:
    """
    One limit exceeded during a ``check()`` call.

    ``resource_name`` is one of ``"cpu"``, ``"memory"``, ``"open_files"``, or
    ``"wall_time"``.  ``measured`` and ``limit`` are in the same unit as the
    ``ResourceLimits`` field (seconds or bytes).
    """
    resource_name: str
    measured:      float
    limit:         float
    intent_name:   str
    timestamp:     float = field(default_factory=time.time)

    @property
    def ratio(self) -> float:
        """measured / limit — how far over the limit we are."""
        return self.measured / self.limit if self.limit > 0 else 0.0


# ---------------------------------------------------------------------------
# ResourceGovernor
# ---------------------------------------------------------------------------

class ResourceGovernor:
    """
    Advisory resource-limit checker for INPROCESS execution.

    Parameters
    ----------
    limits
        The ``ResourceLimits`` spec to check against.
    mode
        The active ``ExecutionIsolationMode``.  In SUBPROCESS mode this class
        still performs post-hoc measurement for audit but logs the breach as
        "post-hoc" rather than advisory.
    event_bus
        Optional.  When set, a ``SIDE_EFFECT_BLOCKED`` event is emitted for
        each breach detected.  (Re-used event type: no dedicated resource-breach
        type exists until Phase 8.)
    """

    def __init__(
        self,
        limits:    ResourceLimits,
        *,
        mode:      ExecutionIsolationMode = ExecutionIsolationMode.INPROCESS,
        event_bus: Optional[SecurityEventBus] = None,
    ) -> None:
        self._limits    = limits
        self._mode      = mode
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def check(
        self,
        intent_name:  str,
        wall_seconds: float,
        *,
        measurement:  Optional[ResourceMeasurement] = None,
    ) -> List[ResourceBreach]:
        """
        Compare a resource measurement against configured limits.

        ``measurement`` may be supplied by the caller (e.g. from a subprocess
        result); when omitted ``measure()`` is called automatically.

        Returns a list of ``ResourceBreach`` objects (empty when all limits
        pass or when no limits are set).  Each breach is also emitted as a
        security event when ``event_bus`` is configured.
        """
        if not self._limits.any_limit_set():
            return []

        if measurement is None:
            measurement = self.measure(wall_seconds=wall_seconds)

        breaches: List[ResourceBreach] = []

        if (self._limits.max_cpu_seconds > 0
                and measurement.cpu_seconds > self._limits.max_cpu_seconds):
            breaches.append(ResourceBreach(
                resource_name="cpu",
                measured=measurement.cpu_seconds,
                limit=self._limits.max_cpu_seconds,
                intent_name=intent_name,
            ))

        if (self._limits.max_memory_bytes > 0
                and measurement.memory_bytes > self._limits.max_memory_bytes):
            breaches.append(ResourceBreach(
                resource_name="memory",
                measured=float(measurement.memory_bytes),
                limit=float(self._limits.max_memory_bytes),
                intent_name=intent_name,
            ))

        if (self._limits.max_open_files > 0
                and measurement.open_files > self._limits.max_open_files):
            breaches.append(ResourceBreach(
                resource_name="open_files",
                measured=float(measurement.open_files),
                limit=float(self._limits.max_open_files),
                intent_name=intent_name,
            ))

        if (self._limits.max_wall_seconds > 0
                and wall_seconds > self._limits.max_wall_seconds):
            breaches.append(ResourceBreach(
                resource_name="wall_time",
                measured=wall_seconds,
                limit=self._limits.max_wall_seconds,
                intent_name=intent_name,
            ))

        for breach in breaches:
            self._emit(breach)

        return breaches

    # ------------------------------------------------------------------
    # Static measurement
    # ------------------------------------------------------------------

    @staticmethod
    def measure(wall_seconds: float = 0.0) -> ResourceMeasurement:
        """
        Snapshot the current process's resource usage.

        Safe to call on any platform; falls back to zeros where OS support
        is missing.
        """
        cpu = _get_cpu_seconds()
        mem = _get_memory_bytes()
        fds = _get_open_files()
        return ResourceMeasurement(
            cpu_seconds=cpu,
            memory_bytes=mem,
            open_files=fds,
            wall_seconds=wall_seconds,
        )

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def limits(self) -> ResourceLimits:
        return self._limits

    @property
    def mode(self) -> ExecutionIsolationMode:
        return self._mode

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, breach: ResourceBreach) -> None:
        if self._event_bus is None:
            return
        self._event_bus.emit(
            SecurityEventType.SIDE_EFFECT_BLOCKED,
            breach.intent_name,
            payload={
                "type":          "resource_breach",
                "resource_name": breach.resource_name,
                "measured":      breach.measured,
                "limit":         breach.limit,
                "ratio":         round(breach.ratio, 4),
                "isolation_mode": self._mode.value,
                "advisory":      self._mode == ExecutionIsolationMode.INPROCESS,
            },
        )


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _get_cpu_seconds() -> float:
    try:
        import resource as _resource
        ru = _resource.getrusage(_resource.RUSAGE_SELF)
        return ru.ru_utime + ru.ru_stime
    except (ImportError, OSError):
        return 0.0


def _get_memory_bytes() -> int:
    """Best-effort RSS in bytes."""
    # Try /proc/self/status (Linux)
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return kb * 1024
    except (OSError, ValueError, IndexError):
        pass

    # Fall back to resource module (macOS gives blocks, not bytes; skip)
    try:
        import resource as _resource
        import sys
        ru = _resource.getrusage(_resource.RUSAGE_SELF)
        if sys.platform == "linux":
            return ru.ru_maxrss * 1024
        # macOS ru_maxrss is already in bytes
        return int(ru.ru_maxrss)
    except (ImportError, OSError):
        pass

    return 0


def _get_open_files() -> int:
    """Count open file descriptors for the current process."""
    # Linux: /proc/self/fd is fastest
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        pass

    # Generic POSIX: scan fd range
    try:
        import resource as _resource
        nofile_soft, _ = _resource.getrlimit(_resource.RLIMIT_NOFILE)
        count = 0
        for fd in range(nofile_soft):
            try:
                os.fstat(fd)
                count += 1
            except OSError:
                pass
        return count
    except (ImportError, OSError):
        pass

    return 0
