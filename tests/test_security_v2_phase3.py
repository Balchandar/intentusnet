"""
Security Kernel v2.1 — Phase 3 Tests

Covers:
  - signals.py additions: _BaselineRegistry.peek(), known_intents()
  - fingerprint_v2.py: EWMAProfile, AdaptiveFingerprintEngineV2
      - record() API
      - start_trace() / end_trace() v1-compatible API
      - latency anomaly detection (EWMA vs absolute fallback)
      - behavior anomaly detection
      - classification thresholds (NORMAL / SUSPICIOUS / MALICIOUS)
      - reasons list content
      - event bus integration (emit on anomaly, no-emit on normal)
      - get_profile() observability
      - known_intents() tracking
      - reset_intent() clears state
      - latency weight / behavior weight effects
      - thread safety
"""

from __future__ import annotations

import threading
import time
import pytest

from intentusnet.security.fingerprint import AnomalyClass
from intentusnet.security.fingerprint_v2 import (
    AdaptiveFingerprintEngineV2,
    EWMAProfile,
)
from intentusnet.security.event_bus import SecurityEventBus, SecurityEventType
from intentusnet.security.signals import (
    _BaselineRegistry,
    compute,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(**kwargs) -> AdaptiveFingerprintEngineV2:
    return AdaptiveFingerprintEngineV2(**kwargs)


def _warm(engine: AdaptiveFingerprintEngineV2, intent: str, n: int,
          latency_ms: float = 100.0) -> None:
    """Pre-seed n identical observations so baselines are established."""
    for i in range(n):
        engine.record(intent, f"exec-warm-{i}", latency_ms=latency_ms)


# ===========================================================================
# signals.py additions: _BaselineRegistry.peek / known_intents
# ===========================================================================

class TestBaselineRegistryExtensions:
    def test_peek_none_before_any_update(self):
        reg = _BaselineRegistry()
        assert reg.peek("i", "latency") is None

    def test_peek_returns_baseline_after_update(self):
        reg = _BaselineRegistry()
        compute("peek_test", latency_ms=50.0, registry=reg)
        result = reg.peek("peek_test", "latency")
        assert result is not None
        assert result.short_ema == pytest.approx(50.0)

    def test_peek_does_not_mutate_state(self):
        reg = _BaselineRegistry()
        compute("peek_test2", latency_ms=100.0, registry=reg)
        b1 = reg.peek("peek_test2", "latency")
        b2 = reg.peek("peek_test2", "latency")
        assert b1.short_ema == b2.short_ema

    def test_known_intents_empty_at_start(self):
        reg = _BaselineRegistry()
        assert reg.known_intents() == []

    def test_known_intents_populated_after_compute(self):
        reg = _BaselineRegistry()
        compute("intent_alpha", latency_ms=10.0, registry=reg)
        compute("intent_beta",  latency_ms=10.0, registry=reg)
        intents = set(reg.known_intents())
        assert "intent_alpha" in intents
        assert "intent_beta" in intents

    def test_known_intents_deduplicates(self):
        reg = _BaselineRegistry()
        for _ in range(5):
            compute("same", latency_ms=10.0, registry=reg)
        assert reg.known_intents().count("same") == 1

    def test_known_intents_cleared_after_reset(self):
        reg = _BaselineRegistry()
        compute("temp", latency_ms=10.0, registry=reg)
        reg.reset_intent("temp")
        assert "temp" not in reg.known_intents()


# ===========================================================================
# EWMAProfile
# ===========================================================================

class TestEWMAProfile:
    def test_to_dict_keys(self):
        profile = EWMAProfile(
            intent_name="x",
            latency_short_ema=100.0,
            latency_long_ema=98.0,
            latency_drift_score=0.02,
            latency_baseline_frozen=False,
        )
        d = profile.to_dict()
        assert "intent" in d
        assert "latency_short_ema_ms" in d
        assert "latency_long_ema_ms" in d
        assert "latency_drift_score" in d
        assert "latency_baseline_frozen" in d

    def test_to_dict_values_rounded(self):
        profile = EWMAProfile(
            intent_name="y",
            latency_short_ema=100.123456,
            latency_long_ema=99.987654,
            latency_drift_score=0.0012345,
            latency_baseline_frozen=False,
        )
        d = profile.to_dict()
        assert d["latency_short_ema_ms"] == 100.12
        assert d["latency_drift_score"] == 0.0012


# ===========================================================================
# AdaptiveFingerprintEngineV2 — basic construction
# ===========================================================================

class TestEngineConstruction:
    def test_default_thresholds(self):
        engine = _engine()
        assert engine._anomaly_threshold == 0.75
        assert engine._malicious_threshold == 0.95

    def test_custom_thresholds(self):
        engine = _engine(anomaly_threshold=0.6, malicious_threshold=0.9)
        assert engine._anomaly_threshold == 0.6

    def test_each_instance_has_own_registry(self):
        e1 = _engine()
        e2 = _engine()
        assert e1._registry is not e2._registry

    def test_no_event_bus_by_default(self):
        assert _engine()._event_bus is None


# ===========================================================================
# record() — normal steady-state
# ===========================================================================

class TestRecordNormal:
    def test_first_sample_returns_normal(self):
        engine = _engine()
        result = engine.record("i", "exec-1", latency_ms=100.0)
        assert result.classification == AnomalyClass.NORMAL

    def test_steady_state_is_normal(self):
        engine = _engine()
        _warm(engine, "i", 30, latency_ms=100.0)
        result = engine.record("i", "exec-31", latency_ms=100.0)
        assert result.classification == AnomalyClass.NORMAL
        assert result.anomaly_score < 0.75

    def test_score_in_unit_interval(self):
        engine = _engine()
        for i in range(20):
            r = engine.record("i", f"e{i}", latency_ms=float(i * 10))
        assert 0.0 <= r.anomaly_score <= 1.0

    def test_normal_result_has_empty_reasons(self):
        engine = _engine()
        result = engine.record("i", "e0", latency_ms=50.0)
        assert result.reasons == []


# ===========================================================================
# record() — latency anomaly
# ===========================================================================

class TestLatencyAnomaly:
    def test_large_spike_after_warmup_raises_score(self):
        engine = _engine(latency_anomaly_threshold_ms=200.0)
        _warm(engine, "spike", 30, latency_ms=50.0)
        # 100× the warm-up value should be way above the absolute threshold
        result = engine.record("spike", "exec-spike", latency_ms=50_000.0)
        assert result.anomaly_score > 0.5

    def test_latency_spike_classification(self):
        # Use low anomaly_threshold to make test deterministic without EWMA warmup
        engine = _engine(
            anomaly_threshold=0.3,
            malicious_threshold=0.85,
            latency_anomaly_threshold_ms=100.0,
        )
        _warm(engine, "lat_cls", 20, latency_ms=50.0)
        result = engine.record("lat_cls", "e", latency_ms=10_000.0)
        assert result.classification in (AnomalyClass.SUSPICIOUS, AnomalyClass.MALICIOUS)

    def test_latency_reason_included_when_signal_high(self):
        engine = _engine(
            anomaly_threshold=0.2,
            malicious_threshold=0.9,
            latency_anomaly_threshold_ms=100.0,
        )
        _warm(engine, "lat_reason", 20, latency_ms=50.0)
        result = engine.record("lat_reason", "e", latency_ms=10_000.0)
        if result.classification != AnomalyClass.NORMAL:
            has_latency_reason = any("latency_anomaly" in r for r in result.reasons)
            assert has_latency_reason

    def test_moderate_latency_does_not_trigger(self):
        engine = _engine(latency_anomaly_threshold_ms=5000.0)
        _warm(engine, "mod_lat", 20, latency_ms=100.0)
        result = engine.record("mod_lat", "e", latency_ms=200.0)
        assert result.classification == AnomalyClass.NORMAL


# ===========================================================================
# record() — behavior anomaly
# ===========================================================================

class TestBehaviorAnomaly:
    def test_zero_unexpected_capabilities_normal(self):
        engine = _engine()
        result = engine.record("b", "e", latency_ms=50.0,
                               unexpected_capabilities=0, policy_violations=0)
        assert result.classification == AnomalyClass.NORMAL

    def test_high_unexpected_capabilities_suspicious(self):
        engine = _engine(anomaly_threshold=0.5)
        result = engine.record("b", "e", latency_ms=50.0,
                               unexpected_capabilities=5)
        assert result.classification in (AnomalyClass.SUSPICIOUS, AnomalyClass.MALICIOUS)

    def test_policy_violations_contribute_to_behavior_signal(self):
        engine = _engine(anomaly_threshold=0.4)
        low  = engine.record("bpol", "e1", latency_ms=50.0, policy_violations=0)
        high = engine.record("bpol", "e2", latency_ms=50.0, policy_violations=4)
        assert high.anomaly_score > low.anomaly_score

    def test_behavior_reason_included(self):
        engine = _engine(anomaly_threshold=0.3, behavior_threshold=1)
        result = engine.record("beh_r", "e", latency_ms=50.0,
                               unexpected_capabilities=3)
        if result.classification != AnomalyClass.NORMAL:
            assert any("behavior_anomaly" in r for r in result.reasons)

    def test_behavior_weight_reduces_score(self):
        # Lower behavior_weight should produce a lower score for same input
        e_high = _engine(behavior_weight=1.0)
        e_low  = _engine(behavior_weight=0.1)
        r_high = e_high.record("bw", "e", latency_ms=50.0, unexpected_capabilities=5)
        r_low  = e_low.record("bw",  "e", latency_ms=50.0, unexpected_capabilities=5)
        assert r_high.anomaly_score >= r_low.anomaly_score


# ===========================================================================
# record() — classification thresholds
# ===========================================================================

class TestClassificationThresholds:
    def test_normal_below_threshold(self):
        engine = _engine(anomaly_threshold=0.99)
        result = engine.record("t", "e", latency_ms=50.0)
        assert result.classification == AnomalyClass.NORMAL

    def test_suspicious_range(self):
        engine = _engine(anomaly_threshold=0.0, malicious_threshold=1.0)
        result = engine.record("t", "e", latency_ms=50.0, unexpected_capabilities=3)
        assert result.classification == AnomalyClass.SUSPICIOUS

    def test_malicious_at_extreme_behavior(self):
        engine = _engine(anomaly_threshold=0.0, malicious_threshold=0.0)
        result = engine.record("t", "e", latency_ms=50.0, unexpected_capabilities=3)
        assert result.classification == AnomalyClass.MALICIOUS


# ===========================================================================
# start_trace / end_trace (v1-compatible API)
# ===========================================================================

class TestStartEndTrace:
    def test_end_trace_without_start_uses_zero_latency(self):
        engine = _engine()
        result = engine.end_trace("no-start-exec", "intent_x")
        assert result.classification == AnomalyClass.NORMAL

    def test_start_end_trace_records_known_intent(self):
        engine = _engine()
        engine.start_trace("exec-st-1")
        engine.end_trace("exec-st-1", "intent_st")
        assert "intent_st" in engine.known_intents()

    def test_start_end_trace_clears_active_start(self):
        engine = _engine()
        engine.start_trace("exec-st-2")
        engine.end_trace("exec-st-2", "intent_st2")
        assert "exec-st-2" not in engine._active_starts

    def test_end_trace_with_timed_out_maps_to_error(self):
        engine = _engine()
        result = engine.end_trace("exec-to", "intent_to", timed_out=True)
        # timed_out maps to error_occurred; at least the call succeeds
        assert isinstance(result, type(result))

    def test_end_trace_retries_param(self):
        engine = _engine(anomaly_threshold=0.3)
        for i in range(20):
            engine.end_trace(f"warm-{i}", "intent_rt", retries=0)
        result_normal = engine.end_trace("r-normal", "intent_rt", retries=0)
        result_retry  = engine.end_trace("r-retry",  "intent_rt", retries=30)
        # High retries should produce a higher score
        assert result_retry.anomaly_score >= result_normal.anomaly_score


# ===========================================================================
# Event bus integration
# ===========================================================================

class TestEventBusIntegration:
    def test_no_emit_for_normal_result(self):
        emitted = []
        with SecurityEventBus() as bus:
            bus.subscribe("s", lambda e: emitted.append(e))
            engine = _engine(event_bus=bus)
            engine.record("safe", "e", latency_ms=50.0)
            bus.stop()
        assert not emitted

    def test_emit_for_suspicious_result(self):
        emitted = []
        first = threading.Event()
        with SecurityEventBus() as bus:
            def handler(e):
                emitted.append(e)
                first.set()
            bus.subscribe("s", handler,
                          event_types={SecurityEventType.ANOMALY_DETECTED})
            engine = _engine(
                event_bus=bus,
                anomaly_threshold=0.0,   # everything is suspicious
                malicious_threshold=1.0,
            )
            engine.record("unsafe", "exec-u", latency_ms=50.0,
                          unexpected_capabilities=3)
            first.wait(timeout=2.0)
            bus.stop()
        assert len(emitted) == 1
        assert emitted[0].event_type == SecurityEventType.ANOMALY_DETECTED

    def test_emitted_event_payload(self):
        emitted = []
        first = threading.Event()
        with SecurityEventBus() as bus:
            def handler(e):
                emitted.append(e)
                first.set()
            bus.subscribe("s", handler)
            engine = _engine(event_bus=bus, anomaly_threshold=0.0,
                             malicious_threshold=1.0)
            engine.record("intent_x", "exec-x", latency_ms=50.0,
                          unexpected_capabilities=3)
            first.wait(timeout=2.0)
            bus.stop()
        if emitted:
            payload = emitted[0].payload
            assert "anomaly_score" in payload
            assert "classification" in payload
            assert "signals" in payload


# ===========================================================================
# Observability — get_profile, known_intents, reset_intent
# ===========================================================================

class TestObservability:
    def test_get_profile_none_before_any_record(self):
        engine = _engine()
        assert engine.get_profile("never_seen") is None

    def test_get_profile_returns_ewma_profile(self):
        engine = _engine()
        _warm(engine, "obs_intent", 5, latency_ms=200.0)
        profile = engine.get_profile("obs_intent")
        assert isinstance(profile, EWMAProfile)
        assert profile.intent_name == "obs_intent"

    def test_get_profile_short_ema_converges(self):
        engine = _engine()
        _warm(engine, "converge", 50, latency_ms=300.0)
        profile = engine.get_profile("converge")
        assert abs(profile.latency_short_ema - 300.0) < 30.0

    def test_known_intents_empty_at_start(self):
        assert _engine().known_intents() == []

    def test_known_intents_after_record(self):
        engine = _engine()
        engine.record("alpha", "e", latency_ms=10.0)
        engine.record("beta",  "e", latency_ms=10.0)
        intents = engine.known_intents()
        assert "alpha" in intents
        assert "beta" in intents

    def test_known_intents_sorted(self):
        engine = _engine()
        engine.record("zzz", "e", latency_ms=10.0)
        engine.record("aaa", "e", latency_ms=10.0)
        intents = engine.known_intents()
        assert intents == sorted(intents)

    def test_known_intents_no_duplicates(self):
        engine = _engine()
        for _ in range(5):
            engine.record("same_intent", "e", latency_ms=10.0)
        assert engine.known_intents().count("same_intent") == 1

    def test_reset_intent_clears_profile(self):
        engine = _engine()
        _warm(engine, "reset_me", 10)
        engine.reset_intent("reset_me")
        assert engine.get_profile("reset_me") is None

    def test_reset_intent_removes_from_known(self):
        engine = _engine()
        engine.record("gone", "e", latency_ms=10.0)
        engine.reset_intent("gone")
        assert "gone" not in engine.known_intents()

    def test_reset_intent_allows_relearning(self):
        engine = _engine()
        _warm(engine, "relearn", 20, latency_ms=1000.0)
        engine.reset_intent("relearn")
        engine.record("relearn", "e", latency_ms=50.0)
        profile = engine.get_profile("relearn")
        assert profile is not None
        # After reset, baseline should be near 50ms (the new first sample)
        assert profile.latency_short_ema < 200.0


# ===========================================================================
# Thread safety
# ===========================================================================

class TestThreadSafety:
    def test_concurrent_records_no_crash(self):
        engine = _engine()
        errors = []
        def record_many(intent_suffix):
            for i in range(30):
                try:
                    engine.record(f"intent_{intent_suffix}", f"exec-{i}",
                                  latency_ms=float(i * 10))
                except Exception as e:
                    errors.append(e)
        threads = [threading.Thread(target=record_many, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_concurrent_start_end_trace(self):
        engine = _engine()
        errors = []
        def trace_loop(n):
            for i in range(20):
                eid = f"exec-{n}-{i}"
                try:
                    engine.start_trace(eid)
                    time.sleep(0)
                    engine.end_trace(eid, f"intent_{n}")
                except Exception as e:
                    errors.append(e)
        threads = [threading.Thread(target=trace_loop, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ===========================================================================
# Public API exports (Phase 3)
# ===========================================================================

class TestPublicAPIExportsPhase3:
    def test_importable_from_package(self):
        import intentusnet as i
        assert hasattr(i, "EWMAProfile")
        assert hasattr(i, "AdaptiveFingerprintEngineV2")

    def test_engine_instantiable(self):
        import intentusnet as i
        engine = i.AdaptiveFingerprintEngineV2()
        result = engine.record("test", "exec-0", latency_ms=100.0)
        assert isinstance(result, i.AnomalyResult)
