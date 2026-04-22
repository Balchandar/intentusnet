"""
Security Kernel v2.1 — Phase 6 Tests

Covers:
  - side_effect_stubs.py
      NullSideEffectAdapter, RecordingStubAdapter, FixedResponseStubAdapter,
      ErrorStubAdapter, SideEffectInterceptor
  - replay_engine.py
      SecurityReplayEngine: compare(), execute()
      ReplayMode.SHADOW / AUDIT / ENFORCE
      ReplayDivergenceError, ReplayComparisonResult
      event bus emission, audit log writes, from_config()
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import pytest

from intentusnet.security.side_effect_stubs import (
    ErrorStubAdapter,
    FixedResponseStubAdapter,
    NullSideEffectAdapter,
    RecordingStubAdapter,
    SideEffectCall,
    SideEffectInterceptor,
)
from intentusnet.security.side_effects import SideEffectQuarantine
from intentusnet.security.replay_engine import (
    ReplayComparisonResult,
    ReplayDivergenceError,
    SecurityReplayEngine,
)
from intentusnet.security.audit import ForensicAuditLog
from intentusnet.security.event_bus import SecurityEventBus, SecurityEventType
from intentusnet.security.types import ReplayMode
from intentusnet.security.config import SecurityConfig, ExecutionIsolationMode
from intentusnet.recording.models import (
    ExecutionHeader,
    ExecutionRecord,
    stable_hash,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(
    final_response: Any = None,
    intent: str = "test.intent",
    execution_id: str = "exec-1",
) -> ExecutionRecord:
    rec = ExecutionRecord.new(
        execution_id=execution_id,
        created_utc_iso=datetime.now(timezone.utc).isoformat(),
        env={"intent": intent, "payload": {}},
        replayable=True,
    )
    rec.finalResponse = final_response
    return rec


def _drain(bus: SecurityEventBus, timeout: float = 0.5) -> None:
    deadline = time.time() + timeout
    while bus.queue_depth > 0 and time.time() < deadline:
        time.sleep(0.01)


def _quarantine_with(*adapter_ids: str) -> SideEffectQuarantine:
    q = SideEffectQuarantine(strict_mode=False)
    for aid in adapter_ids:
        q.register(NullSideEffectAdapter(aid))
    return q


# ===========================================================================
# NullSideEffectAdapter
# ===========================================================================

class TestNullSideEffectAdapter:
    def test_execute_returns_none(self):
        a = NullSideEffectAdapter("email")
        assert a.execute({"to": "x"}) is None

    def test_adapter_id(self):
        a = NullSideEffectAdapter("sms")
        assert a.adapter_id == "sms"

    def test_execute_does_not_raise(self):
        a = NullSideEffectAdapter("db")
        a.execute({})   # must not raise


# ===========================================================================
# RecordingStubAdapter
# ===========================================================================

class TestRecordingStubAdapter:
    def test_records_call(self):
        a = RecordingStubAdapter("email")
        a.execute({"to": "user@example.com"})
        assert a.call_count == 1
        assert a.calls[0].payload == {"to": "user@example.com"}
        assert a.calls[0].adapter_id == "email"

    def test_returns_configured_value(self):
        a = RecordingStubAdapter("rpc", return_value={"status": "ok"})
        result = a.execute({})
        assert result == {"status": "ok"}

    def test_default_return_value_is_none(self):
        a = RecordingStubAdapter("x")
        assert a.execute({}) is None

    def test_multiple_calls_ordered_by_seq(self):
        a = RecordingStubAdapter("x")
        a.execute({"n": 1})
        a.execute({"n": 2})
        a.execute({"n": 3})
        assert [c.payload["n"] for c in a.calls] == [1, 2, 3]

    def test_seq_monotonically_increasing(self):
        a = RecordingStubAdapter("x")
        a.execute({})
        a.execute({})
        seqs = [c.seq for c in a.calls]
        assert seqs == sorted(seqs)
        assert seqs[0] < seqs[1]

    def test_reset_clears_calls(self):
        a = RecordingStubAdapter("x")
        a.execute({"k": "v"})
        a.reset()
        assert a.call_count == 0
        assert a.calls == []

    def test_calls_returns_snapshot(self):
        a = RecordingStubAdapter("x")
        a.execute({})
        snapshot = a.calls
        a.execute({})
        assert len(snapshot) == 1    # snapshot not affected by later call

    def test_thread_safe_call_recording(self):
        a = RecordingStubAdapter("x")
        def worker():
            for _ in range(50):
                a.execute({"t": threading.get_ident()})
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert a.call_count == 200


# ===========================================================================
# FixedResponseStubAdapter
# ===========================================================================

class TestFixedResponseStubAdapter:
    def test_returns_fixed_value(self):
        a = FixedResponseStubAdapter("lookup", return_value=42)
        assert a.execute({}) == 42
        assert a.execute({"x": 1}) == 42

    def test_adapter_id(self):
        a = FixedResponseStubAdapter("cache", return_value=None)
        assert a.adapter_id == "cache"


# ===========================================================================
# ErrorStubAdapter
# ===========================================================================

class TestErrorStubAdapter:
    def test_raises_on_execute(self):
        a = ErrorStubAdapter("flaky")
        with pytest.raises(RuntimeError):
            a.execute({})

    def test_custom_exception_instance(self):
        exc = ValueError("boom")
        a = ErrorStubAdapter("flaky", exception=exc)
        with pytest.raises(ValueError, match="boom"):
            a.execute({})

    def test_custom_exception_type(self):
        a = ErrorStubAdapter("flaky", exception_type=ConnectionError,
                             message="net unreachable")
        with pytest.raises(ConnectionError):
            a.execute({})

    def test_adapter_id(self):
        a = ErrorStubAdapter("err-adapter")
        assert a.adapter_id == "err-adapter"


# ===========================================================================
# SideEffectInterceptor
# ===========================================================================

class TestSideEffectInterceptor:
    def test_intercepts_calls(self):
        q = _quarantine_with("email")
        with SideEffectInterceptor(q) as intr:
            q.execute("email", "SendEmail", ["email"], {"to": "a@b.com"})
            assert intr.call_count() == 1
            assert intr.calls_for("email")[0].payload == {"to": "a@b.com"}

    def test_restores_originals_on_exit(self):
        null = NullSideEffectAdapter("db")
        q = SideEffectQuarantine(strict_mode=False)
        q.register(null)
        with SideEffectInterceptor(q):
            pass
        # After context exit, original adapter restored
        assert q._registry["db"].adapter is null

    def test_multiple_adapters(self):
        q = _quarantine_with("email", "sms", "push")
        with SideEffectInterceptor(q) as intr:
            q.execute("email", "i", ["email"], {})
            q.execute("sms", "i", ["sms"], {})
            assert intr.call_count() == 2
            assert intr.call_count("email") == 1
            assert intr.call_count("sms") == 1

    def test_all_calls_ordered_by_seq(self):
        q = _quarantine_with("a", "b")
        with SideEffectInterceptor(q) as intr:
            q.execute("a", "i", ["a"], {"n": 1})
            q.execute("b", "i", ["b"], {"n": 2})
            q.execute("a", "i", ["a"], {"n": 3})
            all_calls = intr.all_calls()
        assert [c.payload["n"] for c in all_calls] == [1, 2, 3]

    def test_return_value_forwarded(self):
        q = _quarantine_with("rpc")
        with SideEffectInterceptor(q, return_value={"result": "stub"}) as intr:
            result = q.execute("rpc", "i", ["rpc"], {})
        assert result == {"result": "stub"}

    def test_no_side_effects_after_context(self):
        q = _quarantine_with("email")
        with SideEffectInterceptor(q):
            pass
        # After context, interceptor is no longer active — original null adapter
        result = q.execute("email", "i", ["email"], {})
        assert result is None   # NullSideEffectAdapter returns None

    def test_calls_for_unknown_adapter(self):
        q = _quarantine_with("email")
        with SideEffectInterceptor(q) as intr:
            assert intr.calls_for("nonexistent") == []


# ===========================================================================
# SecurityReplayEngine — compare() SHADOW
# ===========================================================================

class TestReplayEngineShadowCompare:
    def test_matched_when_responses_equal(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response={"answer": 42})
        result = engine.compare(rec, {"answer": 42})
        assert isinstance(result, ReplayComparisonResult)
        assert result.matched is True
        assert result.mode == ReplayMode.SHADOW

    def test_divergence_when_responses_differ(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response={"answer": 42})
        result = engine.compare(rec, {"answer": 99})
        assert result.matched is False

    def test_shadow_does_not_raise_on_divergence(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response="hello")
        engine.compare(rec, "world")  # must not raise

    def test_result_contains_hashes(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response={"x": 1})
        result = engine.compare(rec, {"x": 2})
        assert len(result.original_hash) == 64
        assert len(result.replay_hash) == 64
        assert result.original_hash != result.replay_hash

    def test_hashes_match_stable_hash(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        resp = {"data": [1, 2, 3]}
        rec = _record(final_response=resp)
        result = engine.compare(rec, resp)
        assert result.original_hash == stable_hash(resp)
        assert result.replay_hash == stable_hash(resp)

    def test_intent_name_extracted_from_envelope(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response="ok", intent="research.query")
        result = engine.compare(rec, "ok")
        assert result.intent_name == "research.query"

    def test_execution_id_in_result(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response="ok", execution_id="xid-42")
        result = engine.compare(rec, "ok")
        assert result.execution_id == "xid-42"

    def test_wall_seconds_forwarded(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response="ok")
        result = engine.compare(rec, "different", wall_seconds=1.23)
        assert result.wall_seconds == pytest.approx(1.23)

    def test_to_dict(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response={"k": "v"})
        result = engine.compare(rec, {"k": "v"})
        d = result.to_dict()
        assert d["matched"] is True
        assert d["mode"] == "shadow"
        assert "original_hash" in d

    def test_key_order_irrelevant_for_match(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response={"a": 1, "b": 2})
        result = engine.compare(rec, {"b": 2, "a": 1})
        assert result.matched is True


# ===========================================================================
# SecurityReplayEngine — compare() ENFORCE
# ===========================================================================

class TestReplayEngineEnforce:
    def test_enforce_raises_on_divergence(self):
        engine = SecurityReplayEngine(mode=ReplayMode.ENFORCE)
        rec = _record(final_response="hello")
        with pytest.raises(ReplayDivergenceError) as exc_info:
            engine.compare(rec, "world")
        assert exc_info.value.result.matched is False

    def test_enforce_does_not_raise_when_matched(self):
        engine = SecurityReplayEngine(mode=ReplayMode.ENFORCE)
        rec = _record(final_response={"ok": True})
        result = engine.compare(rec, {"ok": True})
        assert result.matched is True

    def test_divergence_error_carries_result(self):
        engine = SecurityReplayEngine(mode=ReplayMode.ENFORCE)
        rec = _record(final_response=1)
        with pytest.raises(ReplayDivergenceError) as exc_info:
            engine.compare(rec, 2)
        err = exc_info.value
        assert isinstance(err.result, ReplayComparisonResult)
        assert len(err.result.original_hash) == 64

    def test_error_str_includes_hashes(self):
        engine = SecurityReplayEngine(mode=ReplayMode.ENFORCE)
        rec = _record(final_response="a")
        with pytest.raises(ReplayDivergenceError) as exc_info:
            engine.compare(rec, "b")
        assert "original_hash" in str(exc_info.value)


# ===========================================================================
# SecurityReplayEngine — compare() AUDIT
# ===========================================================================

class TestReplayEngineAudit:
    def test_audit_writes_entry_on_divergence(self):
        log = ForensicAuditLog()
        engine = SecurityReplayEngine(mode=ReplayMode.AUDIT, audit_log=log)
        rec = _record(final_response="hello", intent="audit.test")
        engine.compare(rec, "world")
        entries = log.export()
        assert len(entries) == 1
        assert entries[0]["decision"] == "replay"
        assert entries[0]["validation_result"] == "replay_divergence"

    def test_audit_no_entry_on_match(self):
        log = ForensicAuditLog()
        engine = SecurityReplayEngine(mode=ReplayMode.AUDIT, audit_log=log)
        rec = _record(final_response={"v": 1})
        engine.compare(rec, {"v": 1})
        assert len(log.export()) == 0

    def test_audit_does_not_raise_on_divergence(self):
        log = ForensicAuditLog()
        engine = SecurityReplayEngine(mode=ReplayMode.AUDIT, audit_log=log)
        rec = _record(final_response="a")
        engine.compare(rec, "b")   # must not raise


# ===========================================================================
# SecurityReplayEngine — events
# ===========================================================================

class TestReplayEngineEvents:
    def test_divergence_event_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.REPLAY_DIVERGENCE})
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW, event_bus=bus)
        rec = _record(final_response="x")
        try:
            engine.compare(rec, "y")
            _drain(bus)
            assert len(events) == 1
            assert events[0].event_type == SecurityEventType.REPLAY_DIVERGENCE
            assert "original_hash" in events[0].payload
            assert "replay_hash" in events[0].payload
        finally:
            bus.stop()

    def test_no_event_on_match(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.REPLAY_DIVERGENCE})
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW, event_bus=bus)
        rec = _record(final_response={"same": True})
        try:
            engine.compare(rec, {"same": True})
            _drain(bus)
            assert events == []
        finally:
            bus.stop()

    def test_event_includes_intent_name(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.REPLAY_DIVERGENCE})
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW, event_bus=bus)
        rec = _record(final_response="x", intent="data.transform")
        try:
            engine.compare(rec, "y")
            _drain(bus)
            assert events[0].intent_name == "data.transform"
        finally:
            bus.stop()


# ===========================================================================
# SecurityReplayEngine — execute()
# ===========================================================================

class TestReplayEngineExecute:
    def test_execute_match(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response=42)
        result = engine.execute(rec, lambda: 42)
        assert result.matched is True

    def test_execute_divergence_shadow(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response=42)
        result = engine.execute(rec, lambda: 99)
        assert result.matched is False

    def test_execute_enforce_raises(self):
        engine = SecurityReplayEngine(mode=ReplayMode.ENFORCE)
        rec = _record(final_response="original")
        with pytest.raises(ReplayDivergenceError):
            engine.execute(rec, lambda: "different")

    def test_execute_exception_treated_as_divergence(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response="ok")
        with pytest.raises(RuntimeError):
            engine.execute(rec, _raise_runtime)

    def test_execute_args_forwarded(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response=10)
        result = engine.execute(rec, lambda x, y: x + y, 3, y=7)
        assert result.matched is True

    def test_execute_wall_seconds_populated(self):
        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response=None)
        result = engine.execute(rec, lambda: None)
        assert result.wall_seconds >= 0.0


# ===========================================================================
# SecurityReplayEngine — from_config()
# ===========================================================================

class TestReplayEngineFromConfig:
    def test_from_config_mode(self):
        cfg = SecurityConfig(
            replay_mode=ReplayMode.AUDIT,
            isolation_mode=ExecutionIsolationMode.INPROCESS,
        )
        engine = SecurityReplayEngine.from_config(cfg)
        assert engine.mode == ReplayMode.AUDIT

    def test_from_config_shadow(self):
        cfg = SecurityConfig(replay_mode=ReplayMode.SHADOW)
        engine = SecurityReplayEngine.from_config(cfg)
        assert engine.mode == ReplayMode.SHADOW


# ===========================================================================
# Integration: stubs + replay
# ===========================================================================

class TestReplayWithStubs:
    def test_null_stub_allows_replay_without_io(self):
        """Agent that calls a side effect can be replayed with null stubs."""
        q = SideEffectQuarantine(strict_mode=False)
        q.register(NullSideEffectAdapter("email"))

        def agent_fn():
            q.execute("email", "Notify", ["email"], {"to": "x"})
            return {"notified": True}

        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response={"notified": True})
        result = engine.execute(rec, agent_fn)
        assert result.matched is True

    def test_recording_stub_captures_replay_side_effects(self):
        """RecordingStubAdapter accumulates calls made during replay."""
        q = SideEffectQuarantine(strict_mode=False)
        stub = RecordingStubAdapter("db", return_value={"rows": []})
        q.register(stub)

        def agent_fn():
            q.execute("db", "Query", ["db"], {"sql": "SELECT 1"})
            return "done"

        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response="done")
        engine.execute(rec, agent_fn)
        assert stub.call_count == 1
        assert stub.calls[0].payload["sql"] == "SELECT 1"

    def test_interceptor_with_replay(self):
        """SideEffectInterceptor works as a per-replay sandbox."""
        q = _quarantine_with("sms")

        def agent_fn():
            q.execute("sms", "Alert", ["sms"], {"msg": "hi"})
            return "sent"

        engine = SecurityReplayEngine(mode=ReplayMode.SHADOW)
        rec = _record(final_response="sent")

        with SideEffectInterceptor(q) as intr:
            result = engine.execute(rec, agent_fn)

        assert result.matched is True
        assert intr.call_count() == 1


# ---------------------------------------------------------------------------
# Module-level picklable helper for execute() exception test
# ---------------------------------------------------------------------------

def _raise_runtime():
    raise RuntimeError("agent error")
