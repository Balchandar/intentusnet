"""
Security Kernel v2.1 — Phase 7 Tests

Covers:
  - trust_anchor_v2.py:
      ITrustAnchorAdapter, TrustAnchorConfirmation, AnchorStatus,
      TrustAnchorManager — registration, anchor(), status(), quorum,
      partial failure, all-fail, event bus, from_config()
  - wal_sampler.py:
      WALSampler — run_once(), sampling fraction, failure detection,
      background thread start/stop, event bus, from_config()
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from intentusnet.security.trust_anchor_v2 import (
    AnchorStatus,
    ITrustAnchorAdapter,
    TrustAnchorConfirmation,
    TrustAnchorManager,
)
from intentusnet.security.wal_sampler import (
    SamplerPassResult,
    WALSampler,
)
from intentusnet.security.event_bus import SecurityEventBus, SecurityEventType
from intentusnet.security.config import SecurityConfig


# ---------------------------------------------------------------------------
# Helpers — anchor adapters
# ---------------------------------------------------------------------------

class _OkAnchor(ITrustAnchorAdapter):
    def __init__(self, anchor_id: str, delay: float = 0.0) -> None:
        self._id    = anchor_id
        self._delay = delay

    @property
    def anchor_id(self) -> str:
        return self._id

    def confirm(self, execution_id: str, entry_hash: str) -> TrustAnchorConfirmation:
        if self._delay > 0:
            time.sleep(self._delay)
        return TrustAnchorConfirmation(
            anchor_id=self._id,
            execution_id=execution_id,
            entry_hash=entry_hash,
            external_id=f"ext-{self._id}",
        )


class _FailAnchor(ITrustAnchorAdapter):
    def __init__(self, anchor_id: str) -> None:
        self._id = anchor_id

    @property
    def anchor_id(self) -> str:
        return self._id

    def confirm(self, execution_id: str, entry_hash: str) -> TrustAnchorConfirmation:
        raise RuntimeError(f"anchor {self._id} unavailable")


def _drain(bus: SecurityEventBus, timeout: float = 1.0) -> None:
    deadline = time.time() + timeout
    while bus.queue_depth > 0 and time.time() < deadline:
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Helpers — WAL file factory
# ---------------------------------------------------------------------------

def _write_valid_wal(wal_dir: Path, execution_id: str, n_entries: int = 3) -> None:
    """Write a minimal valid WAL file."""
    from intentusnet.wal.models import WALEntry, WALEntryType
    from intentusnet.utils.timestamps import now_iso

    entries = []
    prev_hash = None
    for seq in range(1, n_entries + 1):
        e = WALEntry(
            seq=seq,
            execution_id=execution_id,
            timestamp_iso=now_iso(),
            entry_type=WALEntryType.EXECUTION_STARTED,
            payload={"step": seq},
            prev_hash=prev_hash,
        )
        e.entry_hash = e.compute_hash()
        prev_hash = e.entry_hash
        entries.append(e)

    wal_path = wal_dir / f"{execution_id}.wal"
    with open(wal_path, "w") as f:
        for e in entries:
            f.write(json.dumps(e.to_dict()) + "\n")


def _write_corrupt_wal(wal_dir: Path, execution_id: str) -> None:
    """Write a WAL file with a broken hash chain."""
    from intentusnet.wal.models import WALEntry, WALEntryType
    from intentusnet.utils.timestamps import now_iso

    e1 = WALEntry(
        seq=1,
        execution_id=execution_id,
        timestamp_iso=now_iso(),
        entry_type=WALEntryType.EXECUTION_STARTED,
        payload={},
        prev_hash=None,
    )
    e1.entry_hash = e1.compute_hash()

    e2 = WALEntry(
        seq=2,
        execution_id=execution_id,
        timestamp_iso=now_iso(),
        entry_type=WALEntryType.EXECUTION_COMPLETED,
        payload={},
        prev_hash="deadbeef" * 8,  # wrong prev_hash → chain break
    )
    e2.entry_hash = e2.compute_hash()

    wal_path = wal_dir / f"{execution_id}.wal"
    with open(wal_path, "w") as f:
        for e in [e1, e2]:
            f.write(json.dumps(e.to_dict()) + "\n")


# ===========================================================================
# TrustAnchorManager — registration
# ===========================================================================

class TestTrustAnchorManagerRegistration:
    def test_register_adapter(self):
        mgr = TrustAnchorManager()
        mgr.register(_OkAnchor("a"))
        assert "a" in mgr.registered_ids()

    def test_duplicate_register_raises(self):
        mgr = TrustAnchorManager()
        mgr.register(_OkAnchor("a"))
        with pytest.raises(ValueError):
            mgr.register(_OkAnchor("a"))

    def test_unregister(self):
        mgr = TrustAnchorManager()
        mgr.register(_OkAnchor("a"))
        mgr.unregister("a")
        assert "a" not in mgr.registered_ids()

    def test_unregister_nonexistent_noop(self):
        mgr = TrustAnchorManager()
        mgr.unregister("ghost")   # must not raise

    def test_registered_ids_sorted(self):
        mgr = TrustAnchorManager()
        mgr.register(_OkAnchor("c"))
        mgr.register(_OkAnchor("a"))
        mgr.register(_OkAnchor("b"))
        assert mgr.registered_ids() == ["a", "b", "c"]


# ===========================================================================
# TrustAnchorManager — anchor() / status()
# ===========================================================================

class TestTrustAnchorManagerAnchor:
    def test_pending_before_anchor(self):
        mgr = TrustAnchorManager(quorum_size=1)
        assert mgr.status("exec-1", "hash-1") == AnchorStatus.PENDING

    def test_fully_anchored_single_adapter(self):
        mgr = TrustAnchorManager(quorum_size=1)
        mgr.register(_OkAnchor("a"))
        result = mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        assert result == AnchorStatus.FULLY_ANCHORED
        assert mgr.is_fully_anchored("exec-1", "hash-1")

    def test_fully_anchored_quorum_met(self):
        mgr = TrustAnchorManager(quorum_size=2)
        mgr.register(_OkAnchor("a"))
        mgr.register(_OkAnchor("b"))
        result = mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        assert result == AnchorStatus.FULLY_ANCHORED

    def test_partially_anchored_below_quorum(self):
        mgr = TrustAnchorManager(quorum_size=3)
        mgr.register(_OkAnchor("a"))
        mgr.register(_OkAnchor("b"))
        result = mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        assert result == AnchorStatus.PARTIALLY_ANCHORED

    def test_failed_all_adapters_fail(self):
        mgr = TrustAnchorManager(quorum_size=1)
        mgr.register(_FailAnchor("bad"))
        result = mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        assert result == AnchorStatus.FAILED

    def test_partial_failure_one_ok_one_fail(self):
        mgr = TrustAnchorManager(quorum_size=2)
        mgr.register(_OkAnchor("ok"))
        mgr.register(_FailAnchor("bad"))
        result = mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        # 1 confirmed, quorum=2 → partially anchored
        assert result == AnchorStatus.PARTIALLY_ANCHORED

    def test_no_adapters_returns_pending(self):
        mgr = TrustAnchorManager(quorum_size=1)
        result = mgr.anchor("exec-1", "hash-1")
        assert result == AnchorStatus.PENDING

    def test_confirmations_recorded(self):
        mgr = TrustAnchorManager(quorum_size=1)
        mgr.register(_OkAnchor("a"))
        mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        confs = mgr.confirmations("exec-1", "hash-1")
        assert len(confs) == 1
        assert confs[0].anchor_id == "a"
        assert confs[0].entry_hash == "hash-1"
        assert confs[0].external_id == "ext-a"

    def test_failures_recorded(self):
        mgr = TrustAnchorManager(quorum_size=1)
        mgr.register(_FailAnchor("bad"))
        mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        fails = mgr.failures("exec-1", "hash-1")
        assert len(fails) == 1
        assert fails[0][0] == "bad"

    def test_anchor_entries_batch(self):
        mgr = TrustAnchorManager(quorum_size=1)
        mgr.register(_OkAnchor("a"))
        results = mgr.anchor_entries(
            "exec-1", ["h1", "h2", "h3"], timeout_seconds=5.0,
        )
        assert all(v == AnchorStatus.FULLY_ANCHORED for v in results.values())
        assert set(results.keys()) == {"h1", "h2", "h3"}

    def test_is_fully_anchored_false_for_unknown(self):
        mgr = TrustAnchorManager(quorum_size=1)
        assert not mgr.is_fully_anchored("x", "y")

    def test_quorum_zero_treated_as_one(self):
        mgr = TrustAnchorManager(quorum_size=0)
        mgr.register(_OkAnchor("a"))
        result = mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
        assert result == AnchorStatus.FULLY_ANCHORED


# ===========================================================================
# TrustAnchorManager — events
# ===========================================================================

class TestTrustAnchorManagerEvents:
    def test_confirmed_event_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.TRUST_ANCHOR_CONFIRMED})
        mgr = TrustAnchorManager(quorum_size=1, event_bus=bus)
        mgr.register(_OkAnchor("a"))
        try:
            mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
            _drain(bus)
            assert len(events) >= 1
            assert events[0].event_type == SecurityEventType.TRUST_ANCHOR_CONFIRMED
            assert events[0].payload["entry_hash"] == "hash-1"
        finally:
            bus.stop()

    def test_failed_event_emitted_when_all_fail(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.TRUST_ANCHOR_FAILED})
        mgr = TrustAnchorManager(quorum_size=1, event_bus=bus)
        mgr.register(_FailAnchor("bad"))
        try:
            mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
            _drain(bus)
            assert len(events) >= 1
            assert events[0].event_type == SecurityEventType.TRUST_ANCHOR_FAILED
        finally:
            bus.stop()

    def test_no_confirmed_event_below_quorum(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.TRUST_ANCHOR_CONFIRMED})
        mgr = TrustAnchorManager(quorum_size=3, event_bus=bus)
        mgr.register(_OkAnchor("a"))
        mgr.register(_OkAnchor("b"))
        try:
            mgr.anchor("exec-1", "hash-1", timeout_seconds=5.0)
            _drain(bus)
            # quorum=3 but only 2 adapters → PARTIALLY_ANCHORED, no confirmed event
            assert events == []
        finally:
            bus.stop()


# ===========================================================================
# TrustAnchorManager — from_config()
# ===========================================================================

class TestTrustAnchorManagerFromConfig:
    def test_quorum_from_config(self):
        cfg = SecurityConfig(
            trust_anchoring_enabled=True,
            anchor_quorum_size=2,
            anchor_total_adapters=3,
        )
        mgr = TrustAnchorManager.from_config(cfg)
        assert mgr._quorum == 2


# ===========================================================================
# TrustAnchorManager — thread safety
# ===========================================================================

class TestTrustAnchorManagerThreadSafety:
    def test_parallel_anchors(self):
        mgr = TrustAnchorManager(quorum_size=1)
        mgr.register(_OkAnchor("a"))
        results = {}
        lock = threading.Lock()

        def worker(n):
            s = mgr.anchor(f"exec-{n}", f"hash-{n}", timeout_seconds=5.0)
            with lock:
                results[n] = s

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert all(v == AnchorStatus.FULLY_ANCHORED for v in results.values())


# ===========================================================================
# WALSampler — run_once()
# ===========================================================================

class TestWALSamplerRunOnce:
    def test_empty_dir_no_failures(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        result = s.run_once()
        assert result.ok is True
        assert result.files_total == 0
        assert result.files_sampled == 0

    def test_nonexistent_dir_no_crash(self, tmp_path):
        s = WALSampler(str(tmp_path / "ghost"), sample_fraction=1.0)
        result = s.run_once()
        assert result.ok is True

    def test_valid_wal_no_failure(self, tmp_path):
        _write_valid_wal(tmp_path, "exec-1")
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        result = s.run_once()
        assert result.ok is True
        assert result.files_total == 1
        assert result.files_sampled == 1

    def test_corrupt_wal_detected(self, tmp_path):
        _write_corrupt_wal(tmp_path, "exec-bad")
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        result = s.run_once()
        assert result.ok is False
        assert len(result.failures) == 1
        assert result.failures[0][0] == "exec-bad"

    def test_mixed_valid_and_corrupt(self, tmp_path):
        _write_valid_wal(tmp_path, "exec-good")
        _write_corrupt_wal(tmp_path, "exec-bad")
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        result = s.run_once()
        assert result.files_total == 2
        assert len(result.failures) == 1

    def test_sample_fraction_limits_files(self, tmp_path):
        for i in range(10):
            _write_valid_wal(tmp_path, f"exec-{i}")
        s = WALSampler(str(tmp_path), sample_fraction=0.2)
        result = s.run_once()
        assert result.files_total == 10
        # 20% of 10 = 2, but minimum 1
        assert 1 <= result.files_sampled <= 3

    def test_zero_fraction_samples_nothing(self, tmp_path):
        _write_valid_wal(tmp_path, "exec-1")
        s = WALSampler(str(tmp_path), sample_fraction=0.0)
        result = s.run_once()
        assert result.files_sampled == 0

    def test_result_has_duration(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        result = s.run_once()
        assert result.duration_seconds >= 0.0

    def test_to_dict(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        result = s.run_once()
        d = result.to_dict()
        assert "files_sampled" in d
        assert "ok" in d
        assert "failure_count" in d


# ===========================================================================
# WALSampler — counters and history
# ===========================================================================

class TestWALSamplerObservability:
    def test_total_passes_increments(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        s.run_once()
        s.run_once()
        assert s.total_passes == 2

    def test_total_failures_increments(self, tmp_path):
        _write_corrupt_wal(tmp_path, "exec-bad")
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        s.run_once()
        assert s.total_failures == 1

    def test_history_stored(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        s.run_once()
        s.run_once()
        hist = s.history()
        assert len(hist) == 2
        assert all(isinstance(r, SamplerPassResult) for r in hist)

    def test_last_result(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        assert s.last_result() is None
        s.run_once()
        assert s.last_result() is not None

    def test_history_is_copy(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        s.run_once()
        h1 = s.history()
        s.run_once()
        h2 = s.history()
        assert len(h1) == 1
        assert len(h2) == 2


# ===========================================================================
# WALSampler — background thread
# ===========================================================================

class TestWALSamplerBackground:
    def test_start_and_stop(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        s.start(interval_seconds=0.05)
        assert s.is_running is True
        time.sleep(0.2)
        s.stop()
        assert s.is_running is False
        assert s.total_passes >= 1

    def test_start_idempotent(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        s.start(interval_seconds=60.0)
        worker1 = s._worker
        s.start(interval_seconds=60.0)   # second call is a no-op
        worker2 = s._worker
        try:
            assert worker1 is worker2
        finally:
            s.stop()

    def test_context_manager(self, tmp_path):
        with WALSampler(str(tmp_path), sample_fraction=1.0) as s:
            s.start(interval_seconds=0.05)
            time.sleep(0.15)
        assert s.is_running is False

    def test_stop_without_start_noop(self, tmp_path):
        s = WALSampler(str(tmp_path), sample_fraction=1.0)
        s.stop()   # must not raise


# ===========================================================================
# WALSampler — event bus
# ===========================================================================

class TestWALSamplerEvents:
    def test_integrity_failure_event_emitted(self, tmp_path):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.WAL_INTEGRITY_FAILURE})
        _write_corrupt_wal(tmp_path, "exec-bad")
        s = WALSampler(str(tmp_path), sample_fraction=1.0, event_bus=bus)
        try:
            s.run_once()
            _drain(bus)
            assert len(events) == 1
            assert events[0].intent_name == "exec-bad"
            assert events[0].event_type == SecurityEventType.WAL_INTEGRITY_FAILURE
        finally:
            bus.stop()

    def test_no_event_for_valid_wal(self, tmp_path):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.WAL_INTEGRITY_FAILURE})
        _write_valid_wal(tmp_path, "exec-good")
        s = WALSampler(str(tmp_path), sample_fraction=1.0, event_bus=bus)
        try:
            s.run_once()
            _drain(bus)
            assert events == []
        finally:
            bus.stop()


# ===========================================================================
# WALSampler — from_config()
# ===========================================================================

class TestWALSamplerFromConfig:
    def test_fraction_from_config(self, tmp_path):
        cfg = SecurityConfig(
            continuous_wal_monitor=True,
            wal_sample_fraction=0.15,
            wal_verify_interval_seconds=30.0,
        )
        s = WALSampler.from_config(cfg, str(tmp_path))
        assert s._fraction == pytest.approx(0.15)
