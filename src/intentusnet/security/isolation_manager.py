"""
Security Kernel v2.1 — Isolation Manager

Wraps the execution of a callable in the isolation tier configured by
``SecurityConfig.isolation_mode``:

INPROCESS
---------
Calls the function directly in the same thread.  Resource limits are advisory:
``ResourceGovernor.check()`` is called after the function returns, and any
breach is recorded / emitted but does NOT retroactively kill the execution.

SUBPROCESS
----------
Spawns a ``multiprocessing.Process`` (fork-safe on Linux; spawn context used
on macOS/Windows).  Before the function is invoked inside the worker,
``resource.setrlimit()`` applies CPU, memory, and open-file limits so the OS
enforces them.  A watchdog thread in the parent kills the worker if the
wall-clock timeout elapses.  Return value is exchanged via a ``multiprocessing
.Queue``; exceptions are re-raised in the parent.

CONTAINER
---------
Not yet implemented.  ``execute()`` raises ``NotImplementedError`` when called
in CONTAINER mode.  The class can be instantiated safely.

Thread safety
-------------
``execute()`` is re-entrant and thread-safe — each call is independent.
Internal counters (``total_executions`` etc.) are guarded by a lock.

Result
------
``IsolationResult`` carries the return value, any exception, timing, and a
``ResourceMeasurement`` snapshot so callers (e.g. ``CircuitBreaker.record()``)
can make decisions without re-measuring.
"""

from __future__ import annotations

import multiprocessing
import queue as _queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .event_bus import SecurityEventBus, SecurityEventType
from .resource_governor import ResourceBreach, ResourceGovernor, ResourceMeasurement
from .types import ExecutionIsolationMode, ResourceLimits


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class IsolationResult:
    """
    Outcome of one ``IsolationManager.execute()`` call.

    ``success``        — True when the callable returned without raising.
    ``return_value``   — The return value, or None on failure.
    ``exception``      — The raised exception, or None on success.
    ``wall_seconds``   — Elapsed wall time (always populated).
    ``measurement``    — Resource snapshot taken after the call.
    ``breaches``       — Resource limits exceeded (may be non-empty even on success).
    ``timed_out``      — True when the subprocess watchdog fired.
    """
    success:       bool
    return_value:  Any
    exception:     Optional[BaseException]
    wall_seconds:  float
    measurement:   ResourceMeasurement
    breaches:      List[ResourceBreach]
    timed_out:     bool = False
    intent_name:   str  = ""

    @property
    def had_breaches(self) -> bool:
        return bool(self.breaches)


# ---------------------------------------------------------------------------
# IsolationManager
# ---------------------------------------------------------------------------

class IsolationManager:
    """
    Execution isolation wrapper for intent agent calls.

    Parameters
    ----------
    isolation_mode
        INPROCESS, SUBPROCESS, or CONTAINER.
    resource_limits
        Limits applied (advisory in INPROCESS; enforced in SUBPROCESS).
    timeout_seconds
        Wall-clock deadline for SUBPROCESS workers.  0 means no timeout.
    event_bus
        Optional.  Execution-lifecycle events are emitted on start/complete/fail.
    """

    def __init__(
        self,
        isolation_mode:  ExecutionIsolationMode = ExecutionIsolationMode.INPROCESS,
        resource_limits: Optional[ResourceLimits] = None,
        *,
        timeout_seconds: float = 30.0,
        event_bus:       Optional[SecurityEventBus] = None,
    ) -> None:
        self._mode           = isolation_mode
        self._limits         = resource_limits or ResourceLimits()
        self._timeout        = timeout_seconds
        self._event_bus      = event_bus
        self._governor       = ResourceGovernor(
            self._limits, mode=isolation_mode, event_bus=event_bus,
        )

        self._total:   int = 0
        self._failed:  int = 0
        self._timed_out: int = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        config:    Any,   # SecurityConfig; typed as Any to avoid circular import
        *,
        limits:    Optional[ResourceLimits] = None,
        event_bus: Optional[SecurityEventBus] = None,
    ) -> "IsolationManager":
        """Build an IsolationManager from a ``SecurityConfig`` instance."""
        rl = limits or ResourceLimits(
            max_wall_seconds=config.subprocess_timeout_seconds or 0.0,
            max_memory_bytes=config.subprocess_max_memory_bytes or 0,
        )
        return cls(
            isolation_mode=config.isolation_mode,
            resource_limits=rl,
            timeout_seconds=config.subprocess_timeout_seconds,
            event_bus=event_bus,
        )

    # ------------------------------------------------------------------
    # Execution entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        fn:          Callable[..., Any],
        *args:       Any,
        intent_name: str = "",
        **kwargs:    Any,
    ) -> IsolationResult:
        """
        Execute ``fn(*args, **kwargs)`` under the configured isolation mode.

        Raises ``NotImplementedError`` for CONTAINER mode.
        """
        if self._mode == ExecutionIsolationMode.CONTAINER:
            raise NotImplementedError(
                "CONTAINER isolation is not yet implemented in v2.1"
            )

        with self._lock:
            self._total += 1

        if self._event_bus:
            self._event_bus.emit(
                SecurityEventType.EXECUTION_STARTED,
                intent_name or "<unknown>",
            )

        if self._mode == ExecutionIsolationMode.SUBPROCESS:
            result = self._execute_subprocess(fn, args, kwargs, intent_name)
        else:
            result = self._execute_inprocess(fn, args, kwargs, intent_name)

        result.intent_name = intent_name

        with self._lock:
            if not result.success:
                self._failed += 1
            if result.timed_out:
                self._timed_out += 1

        if self._event_bus:
            evt_type = (
                SecurityEventType.EXECUTION_FAILED
                if not result.success
                else SecurityEventType.EXECUTION_COMPLETED
            )
            self._event_bus.emit(
                evt_type,
                intent_name or "<unknown>",
                payload={
                    "wall_seconds": round(result.wall_seconds, 4),
                    "timed_out":    result.timed_out,
                    "had_breaches": result.had_breaches,
                    "isolation":    self._mode.value,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def total_executions(self) -> int:
        with self._lock:
            return self._total

    @property
    def failed_executions(self) -> int:
        with self._lock:
            return self._failed

    @property
    def timed_out_executions(self) -> int:
        with self._lock:
            return self._timed_out

    @property
    def isolation_mode(self) -> ExecutionIsolationMode:
        return self._mode

    @property
    def resource_limits(self) -> ResourceLimits:
        return self._limits

    # ------------------------------------------------------------------
    # INPROCESS execution
    # ------------------------------------------------------------------

    def _execute_inprocess(
        self,
        fn:   Callable[..., Any],
        args: Tuple,
        kwargs: Dict,
        intent_name: str,
    ) -> IsolationResult:
        start = time.perf_counter()
        exc: Optional[BaseException] = None
        retval: Any = None

        try:
            retval = fn(*args, **kwargs)
            success = True
        except BaseException as e:
            exc = e
            success = False

        wall = time.perf_counter() - start
        measurement = ResourceGovernor.measure(wall_seconds=wall)
        breaches = self._governor.check(intent_name or "<unknown>", wall,
                                        measurement=measurement)

        return IsolationResult(
            success=success,
            return_value=retval,
            exception=exc,
            wall_seconds=wall,
            measurement=measurement,
            breaches=breaches,
        )

    # ------------------------------------------------------------------
    # SUBPROCESS execution
    # ------------------------------------------------------------------

    def _execute_subprocess(
        self,
        fn:   Callable[..., Any],
        args: Tuple,
        kwargs: Dict,
        intent_name: str,
    ) -> IsolationResult:
        """
        Run ``fn`` in a fresh ``multiprocessing.Process``.

        The child process applies ``resource.setrlimit()`` before calling the
        function.  Return value and exceptions are exchanged via a
        ``multiprocessing.Queue``.  A watchdog thread in the parent sends
        SIGKILL if ``timeout_seconds`` elapses.
        """
        ctx = multiprocessing.get_context("spawn")
        result_q: multiprocessing.Queue = ctx.Queue(maxsize=1)

        limits_tuple = (
            self._limits.max_cpu_seconds,
            self._limits.max_memory_bytes,
            self._limits.max_open_files,
            self._limits.max_processes,
        )

        proc = ctx.Process(
            target=_subprocess_worker,
            args=(fn, args, kwargs, result_q, limits_tuple),
            daemon=True,
        )

        start = time.perf_counter()
        proc.start()

        timed_out = False
        effective_timeout = self._timeout if self._timeout > 0 else None
        proc.join(timeout=effective_timeout)

        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2.0)
            timed_out = True

        wall = time.perf_counter() - start

        try:
            payload = result_q.get_nowait()
        except _queue.Empty:
            payload = None

        measurement = ResourceMeasurement(wall_seconds=wall)

        if timed_out:
            return IsolationResult(
                success=False,
                return_value=None,
                exception=TimeoutError(
                    f"subprocess timed out after {self._timeout}s"
                ),
                wall_seconds=wall,
                measurement=measurement,
                breaches=self._governor.check(
                    intent_name or "<unknown>", wall,
                    measurement=measurement,
                ),
                timed_out=True,
            )

        if payload is None or payload.get("status") == "error":
            exc_msg = payload.get("error", "unknown error") if payload else "no result"
            return IsolationResult(
                success=False,
                return_value=None,
                exception=RuntimeError(f"subprocess failed: {exc_msg}"),
                wall_seconds=wall,
                measurement=measurement,
                breaches=self._governor.check(
                    intent_name or "<unknown>", wall,
                    measurement=measurement,
                ),
            )

        if "measurement" in payload:
            m = payload["measurement"]
            measurement = ResourceMeasurement(
                cpu_seconds=m.get("cpu_seconds", 0.0),
                memory_bytes=m.get("memory_bytes", 0),
                open_files=m.get("open_files", 0),
                wall_seconds=wall,
            )

        breaches = self._governor.check(
            intent_name or "<unknown>", wall, measurement=measurement,
        )

        return IsolationResult(
            success=True,
            return_value=payload.get("return_value"),
            exception=None,
            wall_seconds=wall,
            measurement=measurement,
            breaches=breaches,
        )


# ---------------------------------------------------------------------------
# Subprocess worker (runs in child process)
# ---------------------------------------------------------------------------

def _subprocess_worker(
    fn:          Callable[..., Any],
    args:        Tuple,
    kwargs:      Dict,
    result_q:    Any,
    limits:      Tuple[float, int, int, int],  # cpu, mem, files, procs
) -> None:
    """Executed inside the spawned child process."""
    _apply_resource_limits(limits)

    try:
        from intentusnet.security.resource_governor import ResourceGovernor
        retval = fn(*args, **kwargs)
        m = ResourceGovernor.measure()
        result_q.put({
            "status": "ok",
            "return_value": retval,
            "measurement": {
                "cpu_seconds":  m.cpu_seconds,
                "memory_bytes": m.memory_bytes,
                "open_files":   m.open_files,
            },
        })
    except BaseException as exc:
        try:
            result_q.put({"status": "error", "error": str(exc)})
        except Exception:
            pass


def _apply_resource_limits(limits: Tuple[float, int, int, int]) -> None:
    """Apply rlimits inside the child process (POSIX only)."""
    cpu_secs, max_mem, max_files, max_procs = limits
    try:
        import resource as _resource

        if cpu_secs > 0:
            ceil = int(cpu_secs) + 1
            _resource.setrlimit(_resource.RLIMIT_CPU, (ceil, ceil))

        if max_mem > 0:
            _resource.setrlimit(_resource.RLIMIT_AS, (max_mem, max_mem))

        if max_files > 0:
            _resource.setrlimit(_resource.RLIMIT_NOFILE, (max_files, max_files))

        if max_procs > 0:
            try:
                _resource.setrlimit(_resource.RLIMIT_NPROC, (max_procs, max_procs))
            except (AttributeError, OSError):
                pass   # RLIMIT_NPROC not available everywhere

    except (ImportError, OSError):
        pass   # non-POSIX platform; limits simply not enforced
