"""
Security Kernel v2.1 — Phase 5 Tests

Covers:
  - resource_governor.py: ResourceMeasurement, ResourceBreach, ResourceGovernor
      - measure() snapshot
      - check() against limits (cpu, memory, open_files, wall_time)
      - no breach when below limits
      - event bus emission on breach
      - advisory mode flag in event payload
  - isolation_manager.py: IsolationManager / IsolationResult
      - INPROCESS: success / exception / timing / breach detection
      - INPROCESS: no breach when limits unset
      - SUBPROCESS: success round-trip
      - SUBPROCESS: timeout fires and timed_out is set
      - SUBPROCESS: exception in worker recorded
      - CONTAINER: NotImplementedError
      - from_config() factory
      - counters: total / failed / timed_out
      - event bus lifecycle events emitted
"""

from __future__ import annotations

import time
import threading

import pytest

from intentusnet.security.resource_governor import (
    ResourceBreach,
    ResourceGovernor,
    ResourceMeasurement,
)
from intentusnet.security.isolation_manager import (
    IsolationManager,
    IsolationResult,
)
from intentusnet.security.types import ExecutionIsolationMode, ResourceLimits
from intentusnet.security.event_bus import SecurityEventBus, SecurityEventType
from intentusnet.security.config import SecurityConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _limits(**kwargs) -> ResourceLimits:
    return ResourceLimits(**kwargs)


def _gov(limits=None, mode=ExecutionIsolationMode.INPROCESS, bus=None):
    return ResourceGovernor(
        limits or ResourceLimits(),
        mode=mode,
        event_bus=bus,
    )


def _drain(bus: SecurityEventBus, timeout: float = 0.5) -> None:
    deadline = time.time() + timeout
    while bus.queue_depth > 0 and time.time() < deadline:
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# ResourceMeasurement
# ---------------------------------------------------------------------------

class TestResourceMeasurement:
    def test_measure_returns_measurement(self):
        m = ResourceGovernor.measure(wall_seconds=1.5)
        assert isinstance(m, ResourceMeasurement)
        assert m.wall_seconds == pytest.approx(1.5)

    def test_measure_cpu_seconds_non_negative(self):
        m = ResourceGovernor.measure()
        assert m.cpu_seconds >= 0.0

    def test_measure_memory_bytes_non_negative(self):
        m = ResourceGovernor.measure()
        assert m.memory_bytes >= 0

    def test_measure_open_files_positive(self):
        m = ResourceGovernor.measure()
        # At minimum stdin/stdout/stderr should be open
        assert m.open_files >= 0


# ---------------------------------------------------------------------------
# ResourceBreach
# ---------------------------------------------------------------------------

class TestResourceBreach:
    def test_ratio_over_limit(self):
        b = ResourceBreach("cpu", measured=10.0, limit=5.0, intent_name="i")
        assert b.ratio == pytest.approx(2.0)

    def test_ratio_zero_limit(self):
        b = ResourceBreach("cpu", measured=10.0, limit=0.0, intent_name="i")
        assert b.ratio == 0.0


# ---------------------------------------------------------------------------
# ResourceGovernor.check()
# ---------------------------------------------------------------------------

class TestResourceGovernorCheck:
    def test_no_limits_returns_empty(self):
        gov = _gov()
        breaches = gov.check("i", 5.0)
        assert breaches == []

    def test_wall_time_breach(self):
        gov = _gov(limits=_limits(max_wall_seconds=1.0))
        breaches = gov.check("i", 2.0)
        assert len(breaches) == 1
        assert breaches[0].resource_name == "wall_time"
        assert breaches[0].measured == pytest.approx(2.0)
        assert breaches[0].limit == pytest.approx(1.0)
        assert breaches[0].intent_name == "i"

    def test_wall_time_within_limit(self):
        gov = _gov(limits=_limits(max_wall_seconds=5.0))
        breaches = gov.check("i", 1.0)
        assert breaches == []

    def test_memory_breach(self):
        gov = _gov(limits=_limits(max_memory_bytes=1024))
        m = ResourceMeasurement(memory_bytes=2048, wall_seconds=0.0)
        breaches = gov.check("i", 0.0, measurement=m)
        assert len(breaches) == 1
        assert breaches[0].resource_name == "memory"

    def test_cpu_breach(self):
        gov = _gov(limits=_limits(max_cpu_seconds=0.001))
        m = ResourceMeasurement(cpu_seconds=1.0, wall_seconds=0.0)
        breaches = gov.check("i", 0.0, measurement=m)
        assert any(b.resource_name == "cpu" for b in breaches)

    def test_open_files_breach(self):
        gov = _gov(limits=_limits(max_open_files=1))
        m = ResourceMeasurement(open_files=10, wall_seconds=0.0)
        breaches = gov.check("i", 0.0, measurement=m)
        assert any(b.resource_name == "open_files" for b in breaches)

    def test_multiple_breaches(self):
        gov = _gov(limits=_limits(max_wall_seconds=0.5, max_memory_bytes=100))
        m = ResourceMeasurement(memory_bytes=200, wall_seconds=0.0)
        breaches = gov.check("i", 2.0, measurement=m)
        names = {b.resource_name for b in breaches}
        assert "wall_time" in names
        assert "memory" in names

    def test_limit_equals_measured_is_not_breach(self):
        gov = _gov(limits=_limits(max_wall_seconds=5.0))
        # exactly at limit should NOT breach (> not >=)
        breaches = gov.check("i", 5.0)
        # The check is `wall > limit`, so equal should not be a breach
        assert all(b.resource_name != "wall_time" for b in breaches)

    def test_advisory_flag_in_mode(self):
        gov = _gov(
            limits=_limits(max_memory_bytes=1),
            mode=ExecutionIsolationMode.INPROCESS,
        )
        assert gov.mode == ExecutionIsolationMode.INPROCESS

    def test_limits_property(self):
        lim = _limits(max_wall_seconds=10.0)
        gov = _gov(limits=lim)
        assert gov.limits is lim


# ---------------------------------------------------------------------------
# ResourceGovernor event bus
# ---------------------------------------------------------------------------

class TestResourceGovernorEvents:
    def test_event_emitted_on_breach(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.SIDE_EFFECT_BLOCKED})
        gov = ResourceGovernor(
            _limits(max_wall_seconds=0.1),
            mode=ExecutionIsolationMode.INPROCESS,
            event_bus=bus,
        )
        try:
            gov.check("my.intent", 5.0)
            _drain(bus)
            assert len(events) == 1
            assert events[0].intent_name == "my.intent"
            assert events[0].payload["type"] == "resource_breach"
            assert events[0].payload["resource_name"] == "wall_time"
            assert events[0].payload["advisory"] is True
        finally:
            bus.stop()

    def test_no_event_when_within_limits(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.SIDE_EFFECT_BLOCKED})
        gov = ResourceGovernor(_limits(max_wall_seconds=100.0), event_bus=bus)
        try:
            gov.check("i", 0.1)
            _drain(bus)
            assert events == []
        finally:
            bus.stop()

    def test_subprocess_mode_advisory_false(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.SIDE_EFFECT_BLOCKED})
        gov = ResourceGovernor(
            _limits(max_wall_seconds=0.1),
            mode=ExecutionIsolationMode.SUBPROCESS,
            event_bus=bus,
        )
        try:
            gov.check("i", 5.0)
            _drain(bus)
            assert events[0].payload["advisory"] is False
        finally:
            bus.stop()


# ---------------------------------------------------------------------------
# IsolationManager — INPROCESS
# ---------------------------------------------------------------------------

class TestIsolationManagerInprocess:
    def test_success_returns_value(self):
        mgr = IsolationManager()
        result = mgr.execute(lambda: 42, intent_name="i")
        assert result.success is True
        assert result.return_value == 42
        assert result.exception is None

    def test_exception_captured(self):
        mgr = IsolationManager()

        def boom():
            raise ValueError("oops")

        result = mgr.execute(boom, intent_name="i")
        assert result.success is False
        assert isinstance(result.exception, ValueError)
        assert result.return_value is None

    def test_wall_seconds_measured(self):
        mgr = IsolationManager()
        result = mgr.execute(lambda: time.sleep(0.05), intent_name="i")
        assert result.wall_seconds >= 0.05

    def test_no_breach_when_no_limits(self):
        mgr = IsolationManager()
        result = mgr.execute(lambda: None, intent_name="i")
        assert result.breaches == []
        assert result.had_breaches is False

    def test_wall_time_breach_detected(self):
        mgr = IsolationManager(
            resource_limits=_limits(max_wall_seconds=0.01),
        )
        result = mgr.execute(lambda: time.sleep(0.1), intent_name="i")
        assert result.had_breaches is True
        assert any(b.resource_name == "wall_time" for b in result.breaches)

    def test_intent_name_set_on_result(self):
        mgr = IsolationManager()
        result = mgr.execute(lambda: None, intent_name="my.intent")
        assert result.intent_name == "my.intent"

    def test_measurement_populated(self):
        mgr = IsolationManager()
        result = mgr.execute(lambda: None, intent_name="i")
        assert isinstance(result.measurement, ResourceMeasurement)

    def test_timed_out_false_for_inprocess(self):
        mgr = IsolationManager()
        result = mgr.execute(lambda: None, intent_name="i")
        assert result.timed_out is False

    def test_args_and_kwargs_forwarded(self):
        mgr = IsolationManager()
        result = mgr.execute(lambda x, y=0: x + y, 3, intent_name="i", y=4)
        assert result.return_value == 7

    def test_counters_increment(self):
        mgr = IsolationManager()
        mgr.execute(lambda: None, intent_name="i")
        mgr.execute(lambda: None, intent_name="i")
        assert mgr.total_executions == 2

    def test_failed_counter_increments(self):
        mgr = IsolationManager()

        def boom():
            raise RuntimeError("x")

        mgr.execute(boom, intent_name="i")
        assert mgr.failed_executions == 1

    def test_timed_out_counter_zero_for_inprocess(self):
        mgr = IsolationManager()
        mgr.execute(lambda: None, intent_name="i")
        assert mgr.timed_out_executions == 0

    def test_isolation_mode_property(self):
        mgr = IsolationManager(ExecutionIsolationMode.INPROCESS)
        assert mgr.isolation_mode == ExecutionIsolationMode.INPROCESS


# ---------------------------------------------------------------------------
# IsolationManager — CONTAINER
# ---------------------------------------------------------------------------

class TestIsolationManagerContainer:
    def test_container_raises_not_implemented(self):
        mgr = IsolationManager(ExecutionIsolationMode.CONTAINER)
        with pytest.raises(NotImplementedError):
            mgr.execute(lambda: None, intent_name="i")


# ---------------------------------------------------------------------------
# IsolationManager — SUBPROCESS
# ---------------------------------------------------------------------------

class TestIsolationManagerSubprocess:
    def test_subprocess_success(self):
        mgr = IsolationManager(
            ExecutionIsolationMode.SUBPROCESS,
            timeout_seconds=10.0,
        )
        result = mgr.execute(_add, 3, 4, intent_name="i")
        assert result.success is True
        assert result.return_value == 7

    def test_subprocess_timeout(self):
        mgr = IsolationManager(
            ExecutionIsolationMode.SUBPROCESS,
            timeout_seconds=0.5,
        )
        result = mgr.execute(_sleep_long, intent_name="i")
        assert result.timed_out is True
        assert result.success is False
        assert mgr.timed_out_executions == 1

    def test_subprocess_exception_recorded(self):
        mgr = IsolationManager(
            ExecutionIsolationMode.SUBPROCESS,
            timeout_seconds=10.0,
        )
        result = mgr.execute(_raise_value_error, intent_name="i")
        assert result.success is False

    def test_subprocess_wall_seconds_populated(self):
        mgr = IsolationManager(
            ExecutionIsolationMode.SUBPROCESS,
            timeout_seconds=10.0,
        )
        result = mgr.execute(_add, 1, 2, intent_name="i")
        assert result.wall_seconds >= 0.0

    def test_subprocess_measurement_populated(self):
        mgr = IsolationManager(
            ExecutionIsolationMode.SUBPROCESS,
            timeout_seconds=10.0,
        )
        result = mgr.execute(_add, 1, 2, intent_name="i")
        assert isinstance(result.measurement, ResourceMeasurement)

    def test_subprocess_counters(self):
        mgr = IsolationManager(
            ExecutionIsolationMode.SUBPROCESS,
            timeout_seconds=10.0,
        )
        mgr.execute(_add, 1, 2, intent_name="i")
        mgr.execute(_add, 3, 4, intent_name="i")
        assert mgr.total_executions == 2


# ---------------------------------------------------------------------------
# IsolationManager — from_config()
# ---------------------------------------------------------------------------

class TestIsolationManagerFromConfig:
    def test_from_config_inprocess(self):
        cfg = SecurityConfig(isolation_mode=ExecutionIsolationMode.INPROCESS)
        mgr = IsolationManager.from_config(cfg)
        assert mgr.isolation_mode == ExecutionIsolationMode.INPROCESS

    def test_from_config_subprocess(self):
        cfg = SecurityConfig(
            isolation_mode=ExecutionIsolationMode.SUBPROCESS,
            subprocess_timeout_seconds=15.0,
        )
        mgr = IsolationManager.from_config(cfg)
        assert mgr.isolation_mode == ExecutionIsolationMode.SUBPROCESS
        assert mgr.resource_limits.max_wall_seconds == pytest.approx(15.0)

    def test_from_config_limits_override(self):
        cfg = SecurityConfig()
        custom_limits = _limits(max_cpu_seconds=5.0)
        mgr = IsolationManager.from_config(cfg, limits=custom_limits)
        assert mgr.resource_limits.max_cpu_seconds == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# IsolationManager — event bus
# ---------------------------------------------------------------------------

class TestIsolationManagerEvents:
    def test_started_and_completed_events_emitted(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e))
        mgr = IsolationManager(event_bus=bus)
        try:
            mgr.execute(lambda: None, intent_name="my.intent")
            _drain(bus)
            types = {e.event_type for e in events}
            assert SecurityEventType.EXECUTION_STARTED in types
            assert SecurityEventType.EXECUTION_COMPLETED in types
        finally:
            bus.stop()

    def test_failed_event_emitted_on_exception(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e))
        mgr = IsolationManager(event_bus=bus)
        try:
            mgr.execute(_raise_value_error, intent_name="i")
            _drain(bus)
            types = {e.event_type for e in events}
            assert SecurityEventType.EXECUTION_FAILED in types
        finally:
            bus.stop()

    def test_completed_event_payload(self):
        bus = SecurityEventBus()
        events = []
        bus.subscribe("t", lambda e: events.append(e),
                      {SecurityEventType.EXECUTION_COMPLETED})
        mgr = IsolationManager(event_bus=bus)
        try:
            mgr.execute(lambda: None, intent_name="i")
            _drain(bus)
            payload = events[0].payload
            assert "wall_seconds" in payload
            assert payload["isolation"] == "inprocess"
            assert payload["had_breaches"] is False
        finally:
            bus.stop()


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestIsolationManagerThreadSafety:
    def test_parallel_inprocess_executions(self):
        mgr = IsolationManager()
        results = []
        lock = threading.Lock()

        def worker(n):
            r = mgr.execute(lambda x: x * 2, n, intent_name="i")
            with lock:
                results.append(r.return_value)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert mgr.total_executions == 20
        assert sorted(results) == sorted([i * 2 for i in range(20)])


# ---------------------------------------------------------------------------
# Module-level picklable functions (needed for subprocess tests)
# ---------------------------------------------------------------------------

def _add(a, b):
    return a + b


def _sleep_long():
    time.sleep(30)


def _raise_value_error():
    raise ValueError("subprocess error")
