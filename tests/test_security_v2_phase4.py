"""
Security Kernel v2.1 — Phase 4 Tests

Covers:
  - circuit_breaker_v2.py: CircuitBreaker state machine
  - capability_governor_v2.py: CapabilityGovernor
  - policy_engine_v2.py: PolicyEngineV2, PolicyDecisionV2
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time

import pytest

from intentusnet.security.circuit_breaker_v2 import (
    CircuitBreaker,
    CircuitState,
    CircuitTransition,
)
from intentusnet.security.capability_governor_v2 import (
    CapabilityGovernor,
    SuspensionEvent,
)
from intentusnet.security.policy_engine_v2 import (
    PolicyDecisionV2,
    PolicyEngineV2,
)
from intentusnet.security.policy_engine import EvaluationContext
from intentusnet.security.event_bus import SecurityEventBus, SecurityEventType
from intentusnet.security.signals import DecomposedSignalSet


# ===========================================================================
# Helpers
# ===========================================================================

def _signals(latency=0.0, error=0.0, behavior=0.0, policy=0.0) -> DecomposedSignalSet:
    return DecomposedSignalSet(
        latency_signal=latency,
        error_signal=error,
        behavior_signal=behavior,
        policy_signal=policy,
    )


def _ctx(intent="test.intent", agent=None, roles=None, tenant=None,
         subject="u", payload=None) -> EvaluationContext:
    return EvaluationContext(
        subject=subject,
        roles=list(roles or []),
        tenant=tenant,
        intent=intent,
        agent=agent,
        payload=dict(payload or {}),
        metadata={},
        tags=[],
    )


def _drain_bus(bus: SecurityEventBus, timeout: float = 0.5) -> None:
    deadline = time.time() + timeout
    while bus.queue_depth > 0 and time.time() < deadline:
        time.sleep(0.01)


# ===========================================================================
# CircuitBreaker — initial state
# ===========================================================================

class TestCircuitBreakerInitial:
    def test_allow_when_closed_initially(self):
        cb = CircuitBreaker()
        assert cb.allow("i1") is True

    def test_state_is_closed_initially(self):
        cb = CircuitBreaker()
        assert cb.get_state("i1") == CircuitState.CLOSED

    def test_known_intents_tracks_after_allow(self):
        cb = CircuitBreaker()
        cb.allow("a")
        cb.allow("b")
        assert set(cb.known_intents()) == {"a", "b"}

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record("i", _signals(error=0.1), success=False)
        cb.record("i", _signals(), success=True)
        # After success, 2 more failures should NOT open the circuit
        cb.record("i", _signals(error=0.1), success=False)
        cb.record("i", _signals(error=0.1), success=False)
        assert cb.get_state("i") == CircuitState.CLOSED


# ===========================================================================
# CircuitBreaker — opening
# ===========================================================================

class TestCircuitBreakerOpens:
    def test_opens_after_consecutive_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record("i", _signals(error=0.1), success=False)
        assert cb.get_state("i") == CircuitState.OPEN

    def test_allow_blocks_in_open(self):
        cb = CircuitBreaker(failure_threshold=2, timeout_seconds=60.0)
        cb.record("i", None, success=False)
        cb.record("i", None, success=False)
        assert cb.allow("i") is False

    def test_opens_immediately_on_high_combined_signal(self):
        cb = CircuitBreaker(failure_threshold=100, trip_signal_threshold=0.5)
        cb.record("i", _signals(error=0.9), success=False)
        assert cb.get_state("i") == CircuitState.OPEN

    def test_does_not_open_on_high_signal_when_success(self):
        cb = CircuitBreaker(trip_signal_threshold=0.5)
        cb.record("i", _signals(error=0.9), success=True)
        assert cb.get_state("i") == CircuitState.CLOSED

    def test_does_not_open_on_high_latency_below_weight(self):
        cb = CircuitBreaker(
            failure_threshold=100,
            trip_signal_threshold=0.5,
            latency_weight=0.1,
        )
        # latency 0.9 * 0.1 = 0.09 < 0.5 → no trip
        cb.record("i", _signals(latency=0.9), success=False)
        assert cb.get_state("i") == CircuitState.CLOSED


# ===========================================================================
# CircuitBreaker — half-open
# ===========================================================================

class TestCircuitBreakerHalfOpen:
    def test_allow_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
        cb.record("i", None, success=False)
        assert cb.get_state("i") == CircuitState.OPEN
        time.sleep(0.1)
        assert cb.allow("i") is True
        assert cb.get_state("i") == CircuitState.HALF_OPEN

    def test_one_probe_at_a_time(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
        cb.record("i", None, success=False)
        time.sleep(0.1)
        assert cb.allow("i") is True
        # Second call while probe is in flight returns False
        assert cb.allow("i") is False

    def test_half_open_probe_success_closes_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
        cb.record("i", None, success=False)
        time.sleep(0.1)
        cb.allow("i")
        cb.record("i", None, success=True)
        assert cb.get_state("i") == CircuitState.CLOSED

    def test_half_open_probe_failure_reopens_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
        cb.record("i", None, success=False)
        time.sleep(0.1)
        cb.allow("i")
        cb.record("i", None, success=False)
        assert cb.get_state("i") == CircuitState.OPEN

    def test_reopen_timer_resets(self):
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=0.05)
        cb.record("i", None, success=False)
        time.sleep(0.1)
        cb.allow("i")
        cb.record("i", None, success=False)     # re-open
        assert cb.allow("i") is False           # timer reset; not yet elapsed


# ===========================================================================
# CircuitBreaker — reset / observability
# ===========================================================================

class TestCircuitBreakerReset:
    def test_reset_moves_open_to_closed(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record("i", None, success=False)
        assert cb.get_state("i") == CircuitState.OPEN
        cb.reset("i")
        assert cb.get_state("i") == CircuitState.CLOSED

    def test_reset_all_closes_all(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record("a", None, success=False)
        cb.record("b", None, success=False)
        cb.reset_all()
        assert cb.get_state("a") == CircuitState.CLOSED
        assert cb.get_state("b") == CircuitState.CLOSED

    def test_reset_nonexistent_intent_noop(self):
        cb = CircuitBreaker()
        cb.reset("never-seen")     # must not raise


# ===========================================================================
# CircuitBreaker — events
# ===========================================================================

class TestCircuitBreakerEvents:
    def test_open_event_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.CIRCUIT_BREAKER_OPENED})
        cb = CircuitBreaker(failure_threshold=1, event_bus=bus)
        try:
            cb.record("i", None, success=False)
            _drain_bus(bus)
            assert any(
                e.event_type == SecurityEventType.CIRCUIT_BREAKER_OPENED
                for e in events
            )
        finally:
            bus.stop()

    def test_half_open_and_closed_events_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e))
        cb = CircuitBreaker(
            failure_threshold=1, timeout_seconds=0.05, event_bus=bus,
        )
        try:
            cb.record("i", None, success=False)       # opened
            time.sleep(0.1)
            cb.allow("i")                             # half-open
            cb.record("i", None, success=True)        # closed
            _drain_bus(bus)
            types = {e.event_type for e in events}
            assert SecurityEventType.CIRCUIT_BREAKER_OPENED in types
            assert SecurityEventType.CIRCUIT_BREAKER_HALF_OPEN in types
            assert SecurityEventType.CIRCUIT_BREAKER_CLOSED in types
        finally:
            bus.stop()

    def test_on_state_change_callback_invoked(self):
        transitions = []
        cb = CircuitBreaker(
            failure_threshold=1,
            on_state_change=lambda t: transitions.append(t),
        )
        cb.record("i", None, success=False)
        assert len(transitions) == 1
        assert transitions[0].to_state == CircuitState.OPEN
        assert isinstance(transitions[0], CircuitTransition)

    def test_on_state_change_callback_error_is_swallowed(self):
        def bad_cb(_t):
            raise RuntimeError("nope")
        cb = CircuitBreaker(failure_threshold=1, on_state_change=bad_cb)
        # must not raise
        cb.record("i", None, success=False)
        assert cb.get_state("i") == CircuitState.OPEN


# ===========================================================================
# CircuitBreaker — thread safety
# ===========================================================================

class TestCircuitBreakerThreadSafety:
    def test_parallel_record_does_not_corrupt(self):
        cb = CircuitBreaker(failure_threshold=10_000)
        def worker():
            for _ in range(200):
                cb.record("i", None, success=False)
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 5 * 200 = 1000 failures; threshold=10_000, circuit still CLOSED
        assert cb.get_state("i") == CircuitState.CLOSED


# ===========================================================================
# CapabilityGovernor — record / suspension
# ===========================================================================

class TestCapabilityGovernorRecord:
    def test_below_threshold_does_nothing(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        result = g.record("i", 0.5, exercised_capabilities=["cap1"])
        assert result == []
        assert g.is_allowed("i", "cap1") is True

    def test_above_threshold_suspends_capability(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        result = g.record("i", 0.9, exercised_capabilities=["cap1"])
        assert result == ["cap1"]
        assert g.is_allowed("i", "cap1") is False

    def test_multiple_capabilities_suspended(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        result = g.record("i", 0.9, exercised_capabilities=["a", "b"])
        assert set(result) == {"a", "b"}
        assert g.is_allowed("i", "a") is False
        assert g.is_allowed("i", "b") is False

    def test_duplicate_suspension_not_repeated(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("i", 0.9, exercised_capabilities=["cap"])
        second = g.record("i", 0.9, exercised_capabilities=["cap"])
        assert second == []

    def test_whole_intent_suspended_when_no_capabilities(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        result = g.record("i", 0.9)
        assert result == ["i"]
        assert g.is_intent_suspended("i") is True
        assert g.is_allowed("i", "anything") is False
        assert g.is_allowed("i") is False

    def test_empty_iterable_treated_as_whole_intent(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        result = g.record("i", 0.9, exercised_capabilities=[])
        assert result == ["i"]
        assert g.is_intent_suspended("i")

    def test_per_capability_does_not_block_other_caps(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("i", 0.9, exercised_capabilities=["cap1"])
        assert g.is_allowed("i", "cap1") is False
        assert g.is_allowed("i", "cap2") is True


# ===========================================================================
# CapabilityGovernor — queries
# ===========================================================================

class TestCapabilityGovernorQueries:
    def test_is_capability_suspended_true_when_whole_intent_suspended(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("i", 0.9)
        assert g.is_capability_suspended("i", "any") is True

    def test_is_capability_suspended_false_for_unknown_intent(self):
        g = CapabilityGovernor()
        assert g.is_capability_suspended("unknown", "cap") is False

    def test_get_suspensions_snapshot(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("i1", 0.9, exercised_capabilities=["capA"])
        g.record("i2", 0.9)
        snap = g.get_suspensions()
        assert snap["i1"] == ["capA"]
        assert snap["i2"] == ["i2"]

    def test_suspended_intents(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("a", 0.9, exercised_capabilities=["c"])
        g.record("b", 0.9)
        assert g.suspended_intents() == ["a", "b"]

    def test_history_records_events(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("i", 0.9, exercised_capabilities=["c"])
        hist = g.history()
        assert len(hist) == 1
        assert isinstance(hist[0], SuspensionEvent)
        assert hist[0].action == "suspend"
        assert hist[0].capability_id == "c"


# ===========================================================================
# CapabilityGovernor — manual intervention
# ===========================================================================

class TestCapabilityGovernorManual:
    def test_suspend_manual(self):
        g = CapabilityGovernor()
        assert g.suspend("i", "cap") is True
        assert g.is_allowed("i", "cap") is False

    def test_suspend_idempotent(self):
        g = CapabilityGovernor()
        g.suspend("i", "cap")
        assert g.suspend("i", "cap") is False

    def test_suspend_whole_intent(self):
        g = CapabilityGovernor()
        g.suspend("i")
        assert g.is_intent_suspended("i")
        assert g.is_allowed("i", "anything") is False

    def test_resume_capability(self):
        g = CapabilityGovernor()
        g.suspend("i", "cap")
        assert g.resume("i", "cap") is True
        assert g.is_allowed("i", "cap") is True

    def test_resume_whole_intent(self):
        g = CapabilityGovernor()
        g.suspend("i")
        assert g.resume("i") is True
        assert g.is_intent_suspended("i") is False

    def test_resume_unknown_noop(self):
        g = CapabilityGovernor()
        assert g.resume("i", "cap") is False

    def test_resume_does_not_remove_other_capability_suspensions(self):
        g = CapabilityGovernor()
        g.suspend("i", "a")
        g.suspend("i", "b")
        g.resume("i", "a")
        assert g.is_allowed("i", "a") is True
        assert g.is_allowed("i", "b") is False

    def test_reset_clears_intent(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("i", 0.9, exercised_capabilities=["c1", "c2"])
        g.reset("i")
        assert g.is_allowed("i", "c1") is True
        assert g.is_allowed("i", "c2") is True

    def test_reset_all_clears_everything(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        g.record("a", 0.9)
        g.record("b", 0.9, exercised_capabilities=["c"])
        g.reset_all()
        assert g.suspended_intents() == []


# ===========================================================================
# CapabilityGovernor — events
# ===========================================================================

class TestCapabilityGovernorEvents:
    def test_capability_violation_event_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.CAPABILITY_VIOLATION})
        g = CapabilityGovernor(behavior_threshold=0.8, event_bus=bus)
        try:
            g.record("i", 0.9, exercised_capabilities=["cap1"])
            _drain_bus(bus)
            assert len(events) == 1
            assert events[0].intent_name == "i"
            assert events[0].payload["capability_id"] == "cap1"
            assert events[0].payload["whole_intent"] is False
        finally:
            bus.stop()

    def test_whole_intent_marked_in_event_payload(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.CAPABILITY_VIOLATION})
        g = CapabilityGovernor(behavior_threshold=0.8, event_bus=bus)
        try:
            g.record("i", 0.9)
            _drain_bus(bus)
            assert events[0].payload["whole_intent"] is True
            assert events[0].payload["capability_id"] is None
        finally:
            bus.stop()

    def test_no_event_on_duplicate_suspension(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.CAPABILITY_VIOLATION})
        g = CapabilityGovernor(behavior_threshold=0.8, event_bus=bus)
        try:
            g.record("i", 0.9, exercised_capabilities=["cap"])
            g.record("i", 0.9, exercised_capabilities=["cap"])
            _drain_bus(bus)
            assert len(events) == 1
        finally:
            bus.stop()

    def test_no_event_on_resume(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.CAPABILITY_VIOLATION})
        g = CapabilityGovernor(event_bus=bus)
        try:
            g.suspend("i", "cap")
            g.resume("i", "cap")
            _drain_bus(bus)
            # Only one event — from suspend, not resume
            assert len(events) == 1
        finally:
            bus.stop()


# ===========================================================================
# CapabilityGovernor — thread safety
# ===========================================================================

class TestCapabilityGovernorThreadSafety:
    def test_parallel_record_no_corruption(self):
        g = CapabilityGovernor(behavior_threshold=0.8)
        def worker(idx):
            g.record(f"i{idx}", 0.9, exercised_capabilities=[f"c{idx}"])
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(g.suspended_intents()) == 10


# ===========================================================================
# PolicyEngineV2 — construction & evaluation
# ===========================================================================

class TestPolicyEngineV2Basic:
    def test_from_dict_allow(self):
        engine = PolicyEngineV2.from_dict({"default": "allow", "rules": []})
        dec = engine.evaluate(_ctx())
        assert isinstance(dec, PolicyDecisionV2)
        assert dec.allowed is True

    def test_from_dict_deny(self):
        engine = PolicyEngineV2.from_dict({"default": "deny", "rules": []})
        dec = engine.evaluate(_ctx())
        assert dec.allowed is False

    def test_rule_matching(self):
        engine = PolicyEngineV2.from_dict({
            "default": "deny",
            "rules": [{
                "id": "allow-research",
                "action": "allow",
                "intents": ["research.query"],
            }],
        })
        dec = engine.evaluate(_ctx(intent="research.query"))
        assert dec.allowed is True
        assert dec.decision.matched_rule.id == "allow-research"

    def test_policy_version_attached(self):
        engine = PolicyEngineV2.from_dict(
            {"default": "allow", "rules": []},
            policy_id="my-policy",
            version=5,
        )
        dec = engine.evaluate(_ctx())
        assert dec.policy_version.policy_id == "my-policy"
        assert dec.policy_version.version == 5
        assert len(dec.policy_version.policy_hash) == 64

    def test_policy_hash_deterministic(self):
        data = {"default": "allow", "rules": [{"id": "r1", "action": "allow"}]}
        e1 = PolicyEngineV2.from_dict(data, policy_id="p")
        e2 = PolicyEngineV2.from_dict(data, policy_id="p")
        assert e1.policy_version.policy_hash == e2.policy_version.policy_hash

    def test_decision_to_dict(self):
        engine = PolicyEngineV2.from_dict({
            "default": "deny",
            "rules": [{"id": "r1", "action": "allow",
                       "intents": ["research.query"]}],
        }, policy_id="pid")
        dec = engine.evaluate(_ctx(intent="research.query"))
        d = dec.to_dict()
        assert d["allowed"] is True
        assert d["rule_id"] == "r1"
        assert d["policy_id"] == "pid"
        assert "policy_hash" in d


# ===========================================================================
# PolicyEngineV2 — file-backed + reload
# ===========================================================================

class TestPolicyEngineV2File:
    def test_from_file_loads_policy(self, tmp_path):
        path = tmp_path / "policy.json"
        path.write_text(json.dumps({"default": "allow", "rules": []}))
        engine = PolicyEngineV2.from_file(str(path))
        dec = engine.evaluate(_ctx())
        assert dec.allowed is True
        assert engine.source_path == str(path)

    def test_default_policy_id_from_filename(self, tmp_path):
        path = tmp_path / "prod-policy.json"
        path.write_text(json.dumps({"default": "allow", "rules": []}))
        engine = PolicyEngineV2.from_file(str(path))
        assert engine.policy_version.policy_id == "prod-policy"

    def test_reload_noop_when_unchanged(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"default": "allow", "rules": []}))
        engine = PolicyEngineV2.from_file(str(path))
        assert engine.reload() is False

    def test_reload_picks_up_changes(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"default": "allow", "rules": []}))
        engine = PolicyEngineV2.from_file(str(path))
        v1 = engine.policy_version.version

        # Advance mtime and change content
        time.sleep(0.05)
        new_data = {"default": "deny", "rules": []}
        path.write_text(json.dumps(new_data))
        # Force mtime advance (some filesystems have 1s resolution)
        future = time.time() + 2.0
        os.utime(str(path), (future, future))

        assert engine.reload() is True
        assert engine.policy_version.version == v1 + 1
        dec = engine.evaluate(_ctx())
        assert dec.allowed is False

    def test_reload_preserves_old_on_parse_error(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"default": "deny", "rules": []}))
        engine = PolicyEngineV2.from_file(str(path))
        path.write_text("{not valid json")
        future = time.time() + 2.0
        os.utime(str(path), (future, future))
        assert engine.reload() is False
        # Old policy still active
        dec = engine.evaluate(_ctx())
        assert dec.allowed is False

    def test_reload_no_source_returns_false(self):
        engine = PolicyEngineV2.from_dict({"default": "allow", "rules": []})
        assert engine.reload() is False

    def test_reload_same_content_new_mtime_not_bumped(self, tmp_path):
        path = tmp_path / "p.json"
        data = {"default": "allow", "rules": []}
        path.write_text(json.dumps(data))
        engine = PolicyEngineV2.from_file(str(path))
        v1 = engine.policy_version.version

        future = time.time() + 2.0
        os.utime(str(path), (future, future))
        # No content change → version should not advance
        assert engine.reload() is False
        assert engine.policy_version.version == v1


# ===========================================================================
# PolicyEngineV2 — events
# ===========================================================================

class TestPolicyEngineV2Events:
    def test_policy_violation_event_on_deny(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.POLICY_VIOLATION})
        engine = PolicyEngineV2.from_dict(
            {"default": "deny", "rules": []},
            policy_id="pol",
            event_bus=bus,
        )
        try:
            engine.evaluate(_ctx(intent="some.intent"))
            _drain_bus(bus)
            assert len(events) == 1
            assert events[0].intent_name == "some.intent"
            assert events[0].payload["policy_id"] == "pol"
        finally:
            bus.stop()

    def test_no_event_on_allow(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.POLICY_VIOLATION})
        engine = PolicyEngineV2.from_dict(
            {"default": "allow", "rules": []},
            event_bus=bus,
        )
        try:
            engine.evaluate(_ctx())
            _drain_bus(bus)
            assert events == []
        finally:
            bus.stop()

    def test_event_carries_rule_id(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.POLICY_VIOLATION})
        engine = PolicyEngineV2.from_dict({
            "default": "allow",
            "rules": [{
                "id": "deny-admin",
                "action": "deny",
                "intents": ["admin.reset"],
            }],
        }, event_bus=bus)
        try:
            engine.evaluate(_ctx(intent="admin.reset"))
            _drain_bus(bus)
            assert events[0].payload["rule_id"] == "deny-admin"
        finally:
            bus.stop()


# ===========================================================================
# PolicyEngineV2 — thread safety
# ===========================================================================

class TestPolicyEngineV2ThreadSafety:
    def test_parallel_evaluate_and_reload(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"default": "allow", "rules": []}))
        engine = PolicyEngineV2.from_file(str(path))

        stop = threading.Event()
        errors = []

        def reader():
            while not stop.is_set():
                try:
                    engine.evaluate(_ctx())
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()

        for i in range(5):
            time.sleep(0.02)
            new = {"default": "allow", "rules": [{"id": f"r{i}", "action": "allow"}]}
            path.write_text(json.dumps(new))
            future = time.time() + i + 1
            os.utime(str(path), (future, future))
            engine.reload()

        stop.set()
        for t in threads:
            t.join()
        assert not errors
