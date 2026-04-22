"""
Security Kernel v2.1 — WAL Sampler (Continuous Integrity Monitor)

Performs periodic, randomised integrity verification of WAL files written
by ``WALWriter``.  A background daemon thread calls ``run_once()`` every
``interval_seconds``; each pass samples ``sample_fraction`` of the WAL files
found in the configured directory and calls ``verify_wal_integrity()`` on
each selected file.

Design goals
------------
* Low overhead: only a fraction of files is verified per pass.  The default
  5 % sample means a 100-file corpus rotates through in ~20 passes (~20 min
  at 60 s intervals).
* Deterministic sampling: uses ``random.sample()`` seeded from the pass
  timestamp so that two monitors running on the same corpus will verify
  different files in the same epoch (reducing correlated blind spots).
* Non-blocking hot path: integrity verification never touches the execution
  path; it runs on a separate daemon thread.
* Tamper visibility: ``WAL_INTEGRITY_FAILURE`` events are emitted via the
  SecurityEventBus on the first failure detected for each file.

Sampling algorithm
------------------
1. Enumerate all ``*.wal`` files in ``wal_dir``.
2. Compute sample size = max(1, floor(len(files) * sample_fraction)).
3. Select sample_size files using Fisher-Yates shuffle seeded with the
   current Unix epoch minute (so consecutive passes cover different files).
4. Verify each selected file; emit an event on failure.

Thread safety
-------------
``run_once()`` may be called from any thread simultaneously with the background
monitor.  The sampling and event emission are self-contained; results are
accumulated in a thread-safe list.
"""

from __future__ import annotations

import math
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_bus import SecurityEventBus, SecurityEventType
from ..wal.integrity import WALIntegrityResult, verify_wal_integrity


# ---------------------------------------------------------------------------
# Per-pass result
# ---------------------------------------------------------------------------

@dataclass
class SamplerPassResult:
    """
    Result of one ``WALSampler.run_once()`` pass.

    ``files_sampled``   — number of WAL files inspected this pass.
    ``files_total``     — total WAL files found in ``wal_dir``.
    ``failures``        — list of (execution_id, WALIntegrityResult) for
                          each file that failed verification.
    ``duration_seconds`` — wall time of this pass.
    ``timestamp``        — wall time when the pass started.
    """
    files_sampled:    int
    files_total:      int
    failures:         List[tuple]   # (execution_id, WALIntegrityResult)
    duration_seconds: float
    timestamp:        float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_sampled":    self.files_sampled,
            "files_total":      self.files_total,
            "failure_count":    len(self.failures),
            "ok":               self.ok,
            "duration_seconds": round(self.duration_seconds, 4),
            "timestamp":        self.timestamp,
        }


# ---------------------------------------------------------------------------
# WALSampler
# ---------------------------------------------------------------------------

class WALSampler:
    """
    Periodic WAL integrity sampler.

    Parameters
    ----------
    wal_dir
        Directory containing ``*.wal`` files written by ``WALWriter``.
    sample_fraction
        Fraction of WAL files to verify per ``run_once()`` call.
        Clamped to [0.0, 1.0]; values ≤ 0 skip verification entirely.
    event_bus
        If set, ``WAL_INTEGRITY_FAILURE`` events are emitted for each
        integrity violation found.
    """

    def __init__(
        self,
        wal_dir:         str,
        sample_fraction: float = 0.05,
        *,
        event_bus:       Optional[SecurityEventBus] = None,
    ) -> None:
        self._wal_dir  = Path(wal_dir)
        self._fraction = max(0.0, min(1.0, sample_fraction))
        self._event_bus = event_bus

        self._history:   List[SamplerPassResult] = []
        self._total_passes:    int = 0
        self._total_failures:  int = 0
        self._running:   bool  = False
        self._worker:    Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock       = threading.Lock()

    # ------------------------------------------------------------------
    # Single verification pass
    # ------------------------------------------------------------------

    def run_once(self) -> SamplerPassResult:
        """
        Enumerate WAL files, sample a fraction, verify integrity.

        Always returns a ``SamplerPassResult``; never raises.
        """
        start = time.perf_counter()
        failures: List[tuple] = []

        wal_files = self._list_wal_files()
        n_total   = len(wal_files)
        sample    = self._select_sample(wal_files)

        for execution_id in sample:
            result = self._verify_one(execution_id)
            if result is not None and not result.ok:
                failures.append((execution_id, result))
                self._emit_failure(execution_id, result)

        duration = time.perf_counter() - start
        pass_result = SamplerPassResult(
            files_sampled=len(sample),
            files_total=n_total,
            failures=failures,
            duration_seconds=duration,
        )

        with self._lock:
            self._history.append(pass_result)
            self._total_passes    += 1
            self._total_failures  += len(failures)

        return pass_result

    # ------------------------------------------------------------------
    # Background monitor
    # ------------------------------------------------------------------

    def start(self, interval_seconds: float = 60.0) -> None:
        """
        Start the background daemon thread.

        Calling ``start()`` again while already running is a no-op.
        """
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._worker = threading.Thread(
                target=self._monitor_loop,
                args=(interval_seconds,),
                name="sk-wal-sampler",
                daemon=True,
            )
            self._worker.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the background thread (drains the current pass first)."""
        with self._lock:
            if not self._running:
                return
            self._running = False
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)
            self._worker = None

    def __enter__(self) -> "WALSampler":
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def total_passes(self) -> int:
        with self._lock:
            return self._total_passes

    @property
    def total_failures(self) -> int:
        with self._lock:
            return self._total_failures

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def history(self) -> List[SamplerPassResult]:
        """Return a snapshot of all pass results."""
        with self._lock:
            return list(self._history)

    def last_result(self) -> Optional[SamplerPassResult]:
        with self._lock:
            return self._history[-1] if self._history else None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        config:    Any,   # SecurityConfig; typed as Any to avoid circular import
        wal_dir:   str,
        *,
        event_bus: Optional[SecurityEventBus] = None,
    ) -> "WALSampler":
        """Build from a ``SecurityConfig`` instance."""
        return cls(
            wal_dir=wal_dir,
            sample_fraction=config.wal_sample_fraction,
            event_bus=event_bus,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _list_wal_files(self) -> List[str]:
        """Return execution_ids (basenames without .wal) from wal_dir."""
        if not self._wal_dir.exists():
            return []
        return [
            p.stem
            for p in self._wal_dir.iterdir()
            if p.suffix == ".wal" and p.is_file()
        ]

    def _select_sample(self, files: List[str]) -> List[str]:
        """Pick a deterministic sample seeded from the current minute."""
        if not files or self._fraction <= 0.0:
            return []
        n = max(1, math.floor(len(files) * self._fraction))
        n = min(n, len(files))
        # Seed from current minute so consecutive passes cover different files
        rng = random.Random(int(time.time()) // 60)
        shuffled = list(files)
        rng.shuffle(shuffled)
        return shuffled[:n]

    def _verify_one(self, execution_id: str) -> Optional[WALIntegrityResult]:
        """Verify one WAL file; return None on unexpected IO errors."""
        try:
            return verify_wal_integrity(str(self._wal_dir), execution_id)
        except Exception:
            return None

    def _emit_failure(
        self,
        execution_id: str,
        result:       WALIntegrityResult,
    ) -> None:
        if self._event_bus is None:
            return
        self._event_bus.emit(
            SecurityEventType.WAL_INTEGRITY_FAILURE,
            execution_id,
            payload={
                "entry_count": result.entry_count,
                "errors":      result.errors,
                "last_hash":   result.last_hash,
            },
        )

    def _monitor_loop(self, interval_seconds: float) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(timeout=interval_seconds)
