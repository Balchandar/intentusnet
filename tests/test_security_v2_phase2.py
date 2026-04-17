"""
Security Kernel v2.1 — Phase 2 Tests

Covers:
  - event_bus.py: SecurityEventType, SecurityEvent, SecurityEventBus
      (Lamport clock, subscribe/emit/dispatch, queue full drop, stop/drain,
       context manager, subscriber filter, error isolation)
  - causality_index.py: ExecutionNode, CausalityIndex
      (derivation, add/get/children/lineage, segmentation, cycle guard,
       duplicate guard, thread safety)
  - backpressure.py: BackpressureMetrics, BackpressureTransition,
      BackpressureManager
      (state machine transitions, hysteresis, recovery, on_transition callback,
       from_config factory, history cap)
"""

from __future__ import annotations

import time
import threading
import pytest

from intentusnet.security.event_bus import (
    SecurityEvent,
    SecurityEventBus,
    SecurityEventType,
)
from intentusnet.security.causality_index import (
    CausalityIndex,
    ExecutionNode,
)
from intentusnet.security.backpressure import (
    BackpressureManager,
    BackpressureMetrics,
    BackpressureTransition,
    from_config,
)
from intentusnet.security.types import DegradationState
from intentusnet.security.config import SecurityConfig


# ===========================================================================
# event_bus.py — SecurityEvent
# ===========================================================================

class TestSecurityEvent:
    def test_unique_event_ids(self):
        e1 = SecurityEvent(
            event_type=SecurityEventType.ANOMALY_DETECTED,
            intent_name="i", execution_id=None,
            lamport_clock=0, timestamp=0.0,
        )
        e2 = SecurityEvent(
            event_type=SecurityEventType.ANOMALY_DETECTED,
            intent_name="i", execution_id=None,
            lamport_clock=1, timestamp=0.0,
        )
        assert e1.event_id != e2.event_id

    def test_to_dict_has_all_keys(self):
        e = SecurityEvent(
            event_type=SecurityEventType.POLICY_VIOLATION,
            intent_name="order", execution_id="exec-1",
            lamport_clock=5, timestamp=1000.0,
            payload={"rule": "deny-all"},
        )
        d = e.to_dict()
        assert d["event_type"] == "policy_violation"
        assert d["intent_name"] == "order"
        assert d["lamport_clock"] == 5
        assert d["payload"]["rule"] == "deny-all"

    def test_payload_defaults_to_empty_dict(self):
        e = SecurityEvent(
            event_type=SecurityEventType.EXECUTION_STARTED,
            intent_name="i", execution_id=None,
            lamport_clock=0, timestamp=0.0,
        )
        assert e.payload == {}


class TestSecurityEventType:
    def test_all_lifecycle_events_exist(self):
        assert SecurityEventType.EXECUTION_STARTED
        assert SecurityEventType.EXECUTION_COMPLETED
        assert SecurityEventType.EXECUTION_FAILED

    def test_circuit_breaker_events(self):
        assert SecurityEventType.CIRCUIT_BREAKER_OPENED
        assert SecurityEventType.CIRCUIT_BREAKER_HALF_OPEN
        assert SecurityEventType.CIRCUIT_BREAKER_CLOSED

    def test_degradation_event(self):
        assert SecurityEventType.DEGRADATION_STATE_CHANGED


# ===========================================================================
# event_bus.py — SecurityEventBus
# ===========================================================================

class TestSecurityEventBusLamport:
    def test_lamport_starts_at_zero(self):
        bus = SecurityEventBus()
        assert bus.lamport_clock == 0
        bus.stop()

    def test_lamport_increments_on_emit(self):
        with SecurityEventBus() as bus:
            e1 = bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            e2 = bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            assert e1.lamport_clock == 0
            assert e2.lamport_clock == 1
            assert bus.lamport_clock == 2

    def test_lamport_monotonic_under_concurrency(self):
        clocks = []
        with SecurityEventBus() as bus:
            def emit_many():
                for _ in range(20):
                    e = bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
                    clocks.append(e.lamport_clock)
            threads = [threading.Thread(target=emit_many) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        # All 100 clocks should be unique
        assert len(set(clocks)) == 100


class TestSecurityEventBusSubscribe:
    def test_subscriber_receives_event(self):
        received = []
        with SecurityEventBus() as bus:
            bus.subscribe("s1", lambda e: received.append(e))
            bus.emit(SecurityEventType.ANOMALY_DETECTED, "intent_a",
                     execution_id="exec-1", payload={"score": 0.9})
            bus.stop()
        assert len(received) == 1
        assert received[0].intent_name == "intent_a"

    def test_subscriber_filter_by_event_type(self):
        anomaly_events = []
        other_events = []
        with SecurityEventBus() as bus:
            bus.subscribe("anomaly-sub", lambda e: anomaly_events.append(e),
                          event_types={SecurityEventType.ANOMALY_DETECTED})
            bus.subscribe("all-sub", lambda e: other_events.append(e))
            bus.emit(SecurityEventType.ANOMALY_DETECTED, "i")
            bus.emit(SecurityEventType.POLICY_VIOLATION, "i")
            bus.stop()
        assert len(anomaly_events) == 1
        assert len(other_events) == 2

    def test_unsubscribe_stops_delivery(self):
        received = []
        first_received = threading.Event()
        def handler(e):
            received.append(e)
            first_received.set()
        with SecurityEventBus() as bus:
            bus.subscribe("s", handler)
            bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            first_received.wait(timeout=2.0)   # wait until first event dispatched
            bus.unsubscribe("s")
            bus.emit(SecurityEventType.EXECUTION_COMPLETED, "i")
            bus.stop()
        assert len(received) == 1

    def test_subscriber_exception_does_not_kill_bus(self):
        good = []
        def bad_handler(e):
            raise RuntimeError("handler crash")
        def good_handler(e):
            good.append(e)
        with SecurityEventBus() as bus:
            bus.subscribe("bad", bad_handler)
            bus.subscribe("good", good_handler)
            bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            bus.stop()
        assert len(good) == 1

    def test_multiple_subscribers_all_notified(self):
        counts = {"a": 0, "b": 0, "c": 0}
        with SecurityEventBus() as bus:
            for name in counts:
                n = name
                bus.subscribe(n, lambda e, x=n: counts.__setitem__(x, counts[x] + 1))
            for _ in range(5):
                bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            bus.stop()
        assert counts == {"a": 5, "b": 5, "c": 5}


class TestSecurityEventBusBackpressure:
    def test_queue_full_drops_events(self):
        # Use a blocking subscriber so the dispatcher is occupied and
        # the queue fills up, causing subsequent emits to be dropped.
        started = threading.Event()
        unblock = threading.Event()
        def slow_handler(e):
            started.set()
            unblock.wait()
        with SecurityEventBus(max_queue=2) as bus:
            bus.subscribe("slow", slow_handler)
            bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            started.wait(timeout=2.0)   # dispatcher is now in slow_handler
            for _ in range(8):          # queue (2) fills and overflows
                bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            assert bus.dropped_events > 0
            unblock.set()

    def test_queue_depth_observable(self):
        # Pause the dispatcher, emit events, verify depth is readable.
        started = threading.Event()
        unblock = threading.Event()
        def slow_handler(e):
            started.set()
            unblock.wait()
        with SecurityEventBus(max_queue=100) as bus:
            bus.subscribe("slow", slow_handler)
            bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            started.wait(timeout=2.0)
            for _ in range(4):
                bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
            assert bus.queue_depth >= 4
            unblock.set()


class TestSecurityEventBusLifecycle:
    def test_context_manager_stops_bus(self):
        with SecurityEventBus() as bus:
            bus.emit(SecurityEventType.EXECUTION_STARTED, "i")
        assert not bus._running

    def test_stop_idempotent(self):
        bus = SecurityEventBus()
        bus.stop()
        bus.stop()   # should not raise
        assert not bus._running

    def test_emit_event_prebuilt(self):
        received = []
        with SecurityEventBus() as bus:
            bus.subscribe("s", lambda e: received.append(e))
            event = SecurityEvent(
                event_type=SecurityEventType.WAL_INTEGRITY_FAILURE,
                intent_name="wal_intent",
                execution_id=None,
                lamport_clock=99,
                timestamp=time.time(),
            )
            bus.emit_event(event)
            bus.stop()
        assert len(received) == 1
        assert received[0].lamport_clock == 99   # preserved as-is


# ===========================================================================
# causality_index.py — Derivation helpers
# ===========================================================================

class TestDerivation:
    def test_deterministic(self):
        id1 = CausalityIndex.derive_execution_id("parent", "agent-a", 0)
        id2 = CausalityIndex.derive_execution_id("parent", "agent-a", 0)
        assert id1 == id2

    def test_different_step_different_id(self):
        id0 = CausalityIndex.derive_execution_id("p", "a", 0)
        id1 = CausalityIndex.derive_execution_id("p", "a", 1)
        assert id0 != id1

    def test_different_agent_different_id(self):
        id_a = CausalityIndex.derive_execution_id("p", "agent-a", 0)
        id_b = CausalityIndex.derive_execution_id("p", "agent-b", 0)
        assert id_a != id_b

    def test_different_parent_different_id(self):
        id_x = CausalityIndex.derive_execution_id("parent-x", "a", 0)
        id_y = CausalityIndex.derive_execution_id("parent-y", "a", 0)
        assert id_x != id_y

    def test_output_is_hex64(self):
        eid = CausalityIndex.derive_execution_id("p", "a", 0)
        assert len(eid) == 64
        int(eid, 16)   # must be valid hex

    def test_root_id_deterministic(self):
        r1 = CausalityIndex.derive_root_id("agent-a", "nonce-1")
        r2 = CausalityIndex.derive_root_id("agent-a", "nonce-1")
        assert r1 == r2

    def test_root_id_different_nonce(self):
        r1 = CausalityIndex.derive_root_id("agent-a", "nonce-1")
        r2 = CausalityIndex.derive_root_id("agent-a", "nonce-2")
        assert r1 != r2


# ===========================================================================
# causality_index.py — CausalityIndex CRUD
# ===========================================================================

def _make_root(agent_id: str = "agent-a", nonce: str = "n1") -> ExecutionNode:
    eid = CausalityIndex.derive_root_id(agent_id, nonce)
    return ExecutionNode(
        execution_id=eid, agent_id=agent_id, step_seq=0, depth=0, parent_id=None
    )

def _make_child(parent: ExecutionNode, agent_id: str, step_seq: int) -> ExecutionNode:
    eid = CausalityIndex.derive_execution_id(parent.execution_id, agent_id, step_seq)
    return ExecutionNode(
        execution_id=eid, agent_id=agent_id, step_seq=step_seq,
        depth=parent.depth + 1, parent_id=parent.execution_id,
    )


class TestCausalityIndexCRUD:
    def test_add_and_get_root(self):
        idx = CausalityIndex()
        root = _make_root()
        idx.add_node(root)
        retrieved = idx.get_node(root.execution_id)
        assert retrieved is not None
        assert retrieved.execution_id == root.execution_id

    def test_get_missing_returns_none(self):
        idx = CausalityIndex()
        assert idx.get_node("nonexistent") is None

    def test_has_node(self):
        idx = CausalityIndex()
        root = _make_root()
        assert not idx.has_node(root.execution_id)
        idx.add_node(root)
        assert idx.has_node(root.execution_id)

    def test_node_count(self):
        idx = CausalityIndex()
        for i in range(5):
            root = _make_root(nonce=str(i))
            idx.add_node(root)
        assert idx.node_count == 5

    def test_duplicate_raises(self):
        idx = CausalityIndex()
        root = _make_root()
        idx.add_node(root)
        with pytest.raises(ValueError, match="already indexed"):
            idx.add_node(root)


class TestCausalityIndexChildren:
    def test_no_children(self):
        idx = CausalityIndex()
        root = _make_root()
        idx.add_node(root)
        assert idx.get_children(root.execution_id) == []

    def test_children_returned_in_insertion_order(self):
        idx = CausalityIndex()
        root = _make_root()
        idx.add_node(root)
        c0 = _make_child(root, "agent-b", 0)
        c1 = _make_child(root, "agent-b", 1)
        idx.add_node(c0)
        idx.add_node(c1)
        children = idx.get_children(root.execution_id)
        assert [c.execution_id for c in children] == [c0.execution_id, c1.execution_id]

    def test_children_of_unknown_parent_empty(self):
        idx = CausalityIndex()
        assert idx.get_children("ghost") == []


class TestCausalityIndexLineage:
    def test_lineage_of_root_is_just_root(self):
        idx = CausalityIndex()
        root = _make_root()
        idx.add_node(root)
        lineage = idx.get_lineage(root.execution_id)
        assert len(lineage) == 1
        assert lineage[0].execution_id == root.execution_id

    def test_lineage_three_levels(self):
        idx = CausalityIndex()
        root  = _make_root()
        child = _make_child(root, "b", 0)
        grand = _make_child(child, "c", 0)
        for n in [root, child, grand]:
            idx.add_node(n)
        lineage = idx.get_lineage(grand.execution_id)
        assert [n.execution_id for n in lineage] == [
            root.execution_id, child.execution_id, grand.execution_id
        ]

    def test_lineage_of_missing_is_empty(self):
        idx = CausalityIndex()
        assert idx.get_lineage("ghost") == []

    def test_lineage_order_root_to_leaf(self):
        idx = CausalityIndex()
        root = _make_root()
        idx.add_node(root)
        prev = root
        for i in range(10):
            node = _make_child(prev, "a", i)
            idx.add_node(node)
            prev = node
        lineage = idx.get_lineage(prev.execution_id)
        assert len(lineage) == 11   # root + 10 children (prev IS the last child)
        assert lineage[0].parent_id is None
        for a, b in zip(lineage, lineage[1:]):
            assert b.parent_id == a.execution_id


class TestCausalityIndexSegmentation:
    def test_segments_split_at_threshold(self):
        idx = CausalityIndex(segment_size=5)
        for i in range(7):
            root = _make_root(nonce=str(i))
            idx.add_node(root)
        assert idx.segment_count == 2
        sizes = idx.segment_sizes()
        assert sum(sizes) == 7
        assert max(sizes) <= 5

    def test_first_segment_full(self):
        idx = CausalityIndex(segment_size=3)
        for i in range(3):
            idx.add_node(_make_root(nonce=str(i)))
        assert idx.segment_sizes() == [3]
        # Adding one more should open a second segment
        idx.add_node(_make_root(nonce="extra"))
        assert idx.segment_count == 2


class TestCausalityIndexThreadSafety:
    def test_concurrent_adds_no_duplicates(self):
        idx = CausalityIndex()
        errors = []
        def add_roots(start):
            for i in range(20):
                try:
                    idx.add_node(_make_root(nonce=f"{start}-{i}"))
                except Exception as e:
                    errors.append(e)
        threads = [threading.Thread(target=add_roots, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert idx.node_count == 100


# ===========================================================================
# backpressure.py — BackpressureMetrics / Transition
# ===========================================================================

class TestBackpressureMetrics:
    def test_defaults_zero(self):
        m = BackpressureMetrics()
        assert m.event_bus_lag == 0
        assert m.wal_backlog == 0
        assert m.anchor_backlog == 0

    def test_observed_at_set(self):
        before = time.time()
        m = BackpressureMetrics()
        assert m.observed_at >= before


class TestBackpressureTransition:
    def test_is_degradation(self):
        t = BackpressureTransition(
            from_state=DegradationState.NORMAL,
            to_state=DegradationState.OBSERVATION_DROP,
            reason="test",
            metrics=BackpressureMetrics(),
        )
        assert t.is_degradation
        assert not t.is_recovery

    def test_is_recovery(self):
        t = BackpressureTransition(
            from_state=DegradationState.AUDIT_ONLY,
            to_state=DegradationState.OBSERVATION_DROP,
            reason="test",
            metrics=BackpressureMetrics(),
        )
        assert t.is_recovery
        assert not t.is_degradation


# ===========================================================================
# backpressure.py — BackpressureManager state machine
# ===========================================================================

def _manager(hysteresis: float = 0.0, **kwargs) -> BackpressureManager:
    """Create a BackpressureManager with zero hysteresis for deterministic tests."""
    return BackpressureManager(
        observation_drop_thresholds=(100, 50, 0),
        audit_only_thresholds=(200, 100, 0),
        fail_safe_thresholds=(500, 200, 0),
        hysteresis_seconds=hysteresis,
        **kwargs,
    )


class TestBackpressureStateMachine:
    def test_initial_state_normal(self):
        mgr = _manager()
        assert mgr.current_state == DegradationState.NORMAL

    def test_no_transition_below_all_thresholds(self):
        mgr = _manager()
        result = mgr.update(BackpressureMetrics(event_bus_lag=10))
        assert result is None
        assert mgr.current_state == DegradationState.NORMAL

    def test_advance_to_observation_drop(self):
        mgr = _manager()
        result = mgr.update(BackpressureMetrics(event_bus_lag=150))
        assert result is not None
        assert result.to_state == DegradationState.OBSERVATION_DROP

    def test_advance_to_audit_only(self):
        mgr = _manager()
        result = mgr.update(BackpressureMetrics(event_bus_lag=250))
        assert result.to_state == DegradationState.AUDIT_ONLY

    def test_advance_to_fail_safe(self):
        mgr = _manager()
        result = mgr.update(BackpressureMetrics(event_bus_lag=600))
        assert result.to_state == DegradationState.FAIL_SAFE

    def test_advance_skips_intermediate_tiers(self):
        """If pressure immediately hits FAIL_SAFE level, skip OBSERVATION_DROP."""
        mgr = _manager()
        result = mgr.update(BackpressureMetrics(event_bus_lag=600))
        assert result.to_state == DegradationState.FAIL_SAFE
        assert mgr.current_state == DegradationState.FAIL_SAFE

    def test_wal_backlog_triggers_degradation(self):
        mgr = _manager()
        result = mgr.update(BackpressureMetrics(wal_backlog=75))
        assert result is not None
        assert result.to_state == DegradationState.OBSERVATION_DROP

    def test_recovery_with_zero_hysteresis(self):
        """With hysteresis=0, each call with low pressure recovers one tier."""
        mgr = _manager(hysteresis=0.0)
        mgr.update(BackpressureMetrics(event_bus_lag=600))
        assert mgr.current_state == DegradationState.FAIL_SAFE
        # 3 tiers to recover (FAIL_SAFE → AUDIT_ONLY → OBS_DROP → NORMAL)
        for _ in range(3):
            mgr.update(BackpressureMetrics())
        assert mgr.current_state == DegradationState.NORMAL

    def test_recovery_one_tier_at_a_time(self):
        mgr = _manager(hysteresis=0.0)
        mgr.update(BackpressureMetrics(event_bus_lag=600))
        assert mgr.current_state == DegradationState.FAIL_SAFE
        mgr.update(BackpressureMetrics())
        assert mgr.current_state == DegradationState.AUDIT_ONLY
        mgr.update(BackpressureMetrics())
        assert mgr.current_state == DegradationState.OBSERVATION_DROP
        mgr.update(BackpressureMetrics())
        assert mgr.current_state == DegradationState.NORMAL

    def test_hysteresis_delays_recovery(self):
        """With hysteresis=10s, recovery should not happen immediately."""
        mgr = _manager(hysteresis=10.0)
        mgr.update(BackpressureMetrics(event_bus_lag=600))
        # Pressure drops but hysteresis window hasn't elapsed
        result = mgr.update(BackpressureMetrics())
        assert result is None
        assert mgr.current_state == DegradationState.FAIL_SAFE

    def test_no_recovery_if_pressure_resumes(self):
        """If pressure returns during the hysteresis window, timer resets."""
        mgr = _manager(hysteresis=5.0)
        mgr.update(BackpressureMetrics(event_bus_lag=600))
        # Drop pressure — starts recovery timer
        mgr.update(BackpressureMetrics())
        # Pressure spikes again — timer should reset
        mgr.update(BackpressureMetrics(event_bus_lag=600))
        assert mgr.current_state == DegradationState.FAIL_SAFE

    def test_on_transition_callback_fired(self):
        transitions = []
        mgr = _manager(on_transition=transitions.append)
        mgr.update(BackpressureMetrics(event_bus_lag=150))
        assert len(transitions) == 1
        assert transitions[0].to_state == DegradationState.OBSERVATION_DROP

    def test_on_transition_exception_does_not_crash(self):
        def bad_cb(t):
            raise RuntimeError("oops")
        mgr = _manager(on_transition=bad_cb)
        mgr.update(BackpressureMetrics(event_bus_lag=600))   # should not raise
        assert mgr.current_state == DegradationState.FAIL_SAFE

    def test_history_records_transitions(self):
        mgr = _manager(hysteresis=0.0)
        mgr.update(BackpressureMetrics(event_bus_lag=600))  # → FAIL_SAFE
        mgr.update(BackpressureMetrics())                   # → AUDIT_ONLY
        assert len(mgr.history) == 2

    def test_history_capped(self):
        mgr = _manager(hysteresis=0.0, max_history=3)
        for _ in range(10):
            mgr.update(BackpressureMetrics(event_bus_lag=600))
            mgr.update(BackpressureMetrics())
        assert len(mgr.history) <= 3

    def test_reset_forces_normal(self):
        mgr = _manager()
        mgr.update(BackpressureMetrics(event_bus_lag=600))
        mgr.reset(DegradationState.NORMAL)
        assert mgr.current_state == DegradationState.NORMAL

    def test_reset_to_arbitrary_state(self):
        mgr = _manager()
        mgr.reset(DegradationState.AUDIT_ONLY)
        assert mgr.current_state == DegradationState.AUDIT_ONLY

    def test_initial_state_respected(self):
        mgr = _manager(initial_state=DegradationState.OBSERVATION_DROP)
        assert mgr.current_state == DegradationState.OBSERVATION_DROP


class TestBackpressureFromConfig:
    def test_from_config_factory(self):
        cfg = SecurityConfig(
            bp_observation_drop_event_lag=1000,
            bp_observation_drop_wal_backlog=500,
            bp_audit_only_event_lag=2000,
            bp_audit_only_wal_backlog=1000,
            bp_fail_safe_event_lag=5000,
            bp_fail_safe_wal_backlog=4000,
            bp_recovery_hysteresis_seconds=0.0,
            initial_degradation_state=DegradationState.NORMAL,
        )
        mgr = from_config(cfg)
        assert mgr.current_state == DegradationState.NORMAL
        result = mgr.update(BackpressureMetrics(event_bus_lag=1500))
        assert result.to_state == DegradationState.OBSERVATION_DROP


# ===========================================================================
# Public API exports (Phase 2)
# ===========================================================================

class TestPublicAPIExportsPhase2:
    def test_event_bus_importable(self):
        import intentusnet as i
        assert hasattr(i, "SecurityEventType")
        assert hasattr(i, "SecurityEvent")
        assert hasattr(i, "SecurityEventBus")

    def test_causality_importable(self):
        import intentusnet as i
        assert hasattr(i, "ExecutionNode")
        assert hasattr(i, "CausalityIndex")

    def test_backpressure_importable(self):
        import intentusnet as i
        assert hasattr(i, "BackpressureMetrics")
        assert hasattr(i, "BackpressureTransition")
        assert hasattr(i, "BackpressureManager")
        assert hasattr(i, "backpressure_from_config")
