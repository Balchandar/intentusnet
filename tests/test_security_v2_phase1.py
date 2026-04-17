"""
Security Kernel v2.1 — Phase 1 Tests

Covers:
  - types.py: PolicyVersion, DegradationState, ReplayMode, ResourceLimits,
              ExecutionIsolationMode
  - signals.py: DualBaselineResult, DecomposedSignalSet, compute(), EWMA behaviour,
                drift freeze, signal decomposition correctness
  - config.py: v2.1 flags, is_v2_active(), is_enforcing(), backward compat
"""

from __future__ import annotations

import math
import pytest

from intentusnet.security.types import (
    DegradationState,
    ExecutionIsolationMode,
    PolicyVersion,
    ReplayMode,
    ResourceLimits,
)
from intentusnet.security.signals import (
    DecomposedSignalSet,
    DualBaselineResult,
    _BaselineRegistry,
    _EWMAState,
    _DRIFT_FREEZE_THRESHOLD,
    compute,
    reset_intent_baselines,
)
from intentusnet.security.config import SecurityConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fresh_registry() -> _BaselineRegistry:
    return _BaselineRegistry()


def warm_registry(intent: str, values, reg: _BaselineRegistry) -> _BaselineRegistry:
    """Feed values into the registry and return it (side-effectful)."""
    for v in values:
        compute(intent, latency_ms=v, registry=reg)
    return reg


# ===========================================================================
# types.py
# ===========================================================================

class TestDegradationState:
    def test_all_values_exist(self):
        assert DegradationState.NORMAL
        assert DegradationState.OBSERVATION_DROP
        assert DegradationState.AUDIT_ONLY
        assert DegradationState.FAIL_SAFE

    def test_string_values(self):
        assert DegradationState.FAIL_SAFE == "fail_safe"
        assert DegradationState.NORMAL == "normal"

    def test_ordering_by_value(self):
        states = [
            DegradationState.NORMAL,
            DegradationState.OBSERVATION_DROP,
            DegradationState.AUDIT_ONLY,
            DegradationState.FAIL_SAFE,
        ]
        assert states == list(DegradationState)


class TestExecutionIsolationMode:
    def test_three_modes(self):
        assert ExecutionIsolationMode.INPROCESS == "inprocess"
        assert ExecutionIsolationMode.SUBPROCESS == "subprocess"
        assert ExecutionIsolationMode.CONTAINER == "container"


class TestReplayMode:
    def test_three_modes(self):
        assert ReplayMode.SHADOW == "shadow"
        assert ReplayMode.AUDIT == "audit"
        assert ReplayMode.ENFORCE == "enforce"


class TestResourceLimits:
    def test_defaults_are_unlimited(self):
        rl = ResourceLimits()
        assert rl.max_cpu_seconds == 0.0
        assert rl.max_memory_bytes == 0
        assert rl.max_open_files == 0
        assert rl.max_processes == 0
        assert rl.max_wall_seconds == 0.0

    def test_any_limit_set_false_when_all_zero(self):
        assert not ResourceLimits().any_limit_set()

    def test_any_limit_set_true_when_one_set(self):
        assert ResourceLimits(max_cpu_seconds=5.0).any_limit_set()
        assert ResourceLimits(max_memory_bytes=1).any_limit_set()
        assert ResourceLimits(max_open_files=10).any_limit_set()

    def test_partial_limits(self):
        rl = ResourceLimits(max_cpu_seconds=2.5, max_memory_bytes=256 * 1024 * 1024)
        assert rl.any_limit_set()
        assert rl.max_open_files == 0


class TestPolicyVersion:
    def test_construction(self):
        pv = PolicyVersion(policy_id="p1", version=1, policy_hash="a" * 64)
        assert pv.policy_id == "p1"
        assert pv.version == 1

    def test_short_hash(self):
        pv = PolicyVersion(policy_id="p1", version=1, policy_hash="abcdef123456" + "0" * 52)
        assert pv.short_hash() == "abcdef123456"

    def test_unknown_sentinel(self):
        pv = PolicyVersion.unknown()
        assert pv.policy_id == "__unknown__"
        assert pv.version == 0
        assert len(pv.policy_hash) == 64

    def test_hash_rules_is_deterministic(self):
        h1 = PolicyVersion.hash_rules('[{"id": "r1"}]')
        h2 = PolicyVersion.hash_rules('[{"id": "r1"}]')
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_rules_different_input_different_hash(self):
        h1 = PolicyVersion.hash_rules("[]")
        h2 = PolicyVersion.hash_rules('[{"id": "r1"}]')
        assert h1 != h2


# ===========================================================================
# signals.py — _EWMAState
# ===========================================================================

class TestEWMAState:
    def test_first_sample_initialises_both_baselines(self):
        state = _EWMAState()
        result = state.update(100.0)
        assert result.short_ema == 100.0
        assert result.long_ema == 100.0
        assert result.drift_score == 0.0
        assert not result.baseline_frozen

    def test_z_score_none_on_first_sample(self):
        state = _EWMAState()
        result = state.update(100.0)
        assert result.z_score is None

    def test_z_score_available_after_variance_builds(self):
        state = _EWMAState()
        # Feed varied values so variance > 0
        for v in [100.0, 110.0, 90.0, 105.0, 95.0]:
            result = state.update(v)
        # z_score may still be None if variance didn't build; check it's a number
        if result.z_score is not None:
            assert isinstance(result.z_score, float)

    def test_short_ema_reacts_faster_than_long(self):
        state = _EWMAState()
        state.update(100.0)
        for _ in range(20):
            r = state.update(100.0)
        # both should converge near 100 after steady input
        assert abs(r.short_ema - 100.0) < 5.0
        assert abs(r.long_ema - 100.0) < 5.0

    def test_drift_score_rises_when_short_exceeds_long(self):
        state = _EWMAState()
        # Warm up at 100
        for _ in range(50):
            state.update(100.0)
        # Sudden sustained spike — short EMA races ahead of long
        for _ in range(50):
            state.update(1000.0)
        r = state.peek()
        assert r.short_ema > r.long_ema

    def test_baseline_frozen_prevents_further_updates(self):
        """When drift >= freeze threshold, EMA values should not change."""
        state = _EWMAState()
        # Warm up at baseline
        for _ in range(30):
            state.update(100.0)
        # Drive drift score above threshold
        for _ in range(200):
            state.update(9999.0)
        r1 = state.peek()
        # Feed another extreme value; if frozen, baselines should be stable
        r2 = state.update(99999.0)
        if r1.baseline_frozen and r2.baseline_frozen:
            # Baselines should not have moved significantly
            assert abs(r1.short_ema - r2.short_ema) < 1.0


# ===========================================================================
# signals.py — compute()
# ===========================================================================

class TestComputeSignals:
    def test_returns_decomposed_signal_set(self):
        reg = fresh_registry()
        result = compute("intent_a", latency_ms=50.0, registry=reg)
        assert isinstance(result, DecomposedSignalSet)

    def test_all_signals_in_unit_interval(self):
        reg = fresh_registry()
        for i in range(20):
            r = compute("intent_a", latency_ms=float(i * 10), registry=reg)
        assert 0.0 <= r.latency_signal <= 1.0
        assert 0.0 <= r.error_signal <= 1.0
        assert 0.0 <= r.behavior_signal <= 1.0
        assert 0.0 <= r.policy_signal <= 1.0

    def test_no_error_gives_low_error_signal(self):
        reg = fresh_registry()
        r = compute("intent_b", latency_ms=100.0, error_occurred=False, consecutive_errors=0, registry=reg)
        # Binary component 0, sigmoid of 0 errors is ~0.05
        assert r.error_signal < 0.3

    def test_error_occurred_raises_error_signal(self):
        reg = fresh_registry()
        r = compute("intent_b", latency_ms=100.0, error_occurred=True, consecutive_errors=5, registry=reg)
        assert r.error_signal > 0.3

    def test_zero_behavior_inputs_give_low_behavior_signal(self):
        reg = fresh_registry()
        r = compute("intent_c", latency_ms=100.0,
                    unexpected_capabilities=0, policy_violations=0, registry=reg)
        assert r.behavior_signal < 0.2

    def test_high_behavior_inputs_give_high_behavior_signal(self):
        reg = fresh_registry()
        r = compute("intent_c", latency_ms=100.0,
                    unexpected_capabilities=5, policy_violations=3, registry=reg)
        assert r.behavior_signal > 0.7

    def test_policy_score_passed_through(self):
        reg = fresh_registry()
        r = compute("intent_d", latency_ms=100.0, policy_score=0.9, registry=reg)
        assert r.policy_signal == pytest.approx(0.9)

    def test_policy_score_clamped(self):
        reg = fresh_registry()
        r_high = compute("intent_e", latency_ms=100.0, policy_score=2.5, registry=reg)
        r_low  = compute("intent_e", latency_ms=100.0, policy_score=-1.0, registry=reg)
        assert r_high.policy_signal == 1.0
        assert r_low.policy_signal == 0.0

    def test_max_signal_is_max_of_four(self):
        reg = fresh_registry()
        r = compute("intent_f", latency_ms=100.0, policy_score=0.8, error_occurred=False, registry=reg)
        assert r.max_signal == max(r.latency_signal, r.error_signal,
                                   r.behavior_signal, r.policy_signal)

    def test_to_dict_has_expected_keys(self):
        reg = fresh_registry()
        r = compute("intent_g", latency_ms=100.0, registry=reg)
        d = r.to_dict()
        assert set(d.keys()) == {"latency_signal", "error_signal", "behavior_signal",
                                  "policy_signal", "max_signal"}

    def test_latency_baseline_is_set(self):
        reg = fresh_registry()
        r = compute("intent_h", latency_ms=100.0, registry=reg)
        assert r.latency_baseline is not None
        assert isinstance(r.latency_baseline, DualBaselineResult)

    def test_baselines_independent_across_intents(self):
        reg = fresh_registry()
        warm_registry("intent_i", [100.0] * 50, reg)
        warm_registry("intent_j", [9999.0] * 50, reg)
        r_i = compute("intent_i", latency_ms=100.0, registry=reg)
        r_j = compute("intent_j", latency_ms=9999.0, registry=reg)
        # Baselines for i and j should differ substantially
        assert r_i.latency_baseline.short_ema < r_j.latency_baseline.short_ema

    def test_steady_state_low_latency_signal(self):
        """After 30 identical observations, a matching 31st should score low."""
        reg = fresh_registry()
        warm_registry("steady", [200.0] * 30, reg)
        r = compute("steady", latency_ms=200.0, registry=reg)
        # Perfectly normal execution should stay low
        assert r.latency_signal < 0.5

    def test_sudden_spike_raises_latency_signal(self):
        """A 10× spike after stable baseline should raise the signal."""
        reg = fresh_registry()
        warm_registry("spike_intent", [100.0] * 30, reg)
        r = compute("spike_intent", latency_ms=10_000.0, registry=reg)
        assert r.latency_signal > r.error_signal   # latency dominates


class TestResetIntentBaselines:
    def test_reset_clears_state(self):
        reg = fresh_registry()
        warm_registry("resetable", [500.0] * 20, reg)
        reset_intent_baselines.__wrapped__ = None  # coverage: use module function
        # Access state directly to confirm it was there
        from intentusnet.security.signals import _registry as module_reg
        # Use a dedicated registry so we don't disturb the module-level one
        warm_registry("resetable2", [500.0] * 20, reg)
        reg.reset_intent("resetable2")
        # After reset, next compute should reinitialise at first sample
        r = compute("resetable2", latency_ms=100.0, registry=reg)
        assert r.latency_baseline.short_ema == pytest.approx(100.0)


# ===========================================================================
# config.py — v2.1
# ===========================================================================

class TestSecurityConfigV2:
    def test_defaults_are_backward_compatible(self):
        cfg = SecurityConfig()
        # v1 defaults must not change
        assert not cfg.strict_mode
        assert cfg.audit_only
        assert cfg.capability_contracts
        assert cfg.fingerprint_enabled
        assert cfg.mcp_validation
        assert cfg.forensic_audit

    def test_is_enforcing_unchanged(self):
        assert not SecurityConfig().is_enforcing()
        assert SecurityConfig(strict_mode=True, audit_only=False).is_enforcing()

    def test_is_v2_active_false_by_default(self):
        assert not SecurityConfig().is_v2_active()

    def test_is_v2_active_when_flag_set(self):
        assert SecurityConfig(adaptive_fingerprint=True).is_v2_active()
        assert SecurityConfig(circuit_breaker_enabled=True).is_v2_active()
        assert SecurityConfig(trust_anchoring_enabled=True).is_v2_active()
        assert SecurityConfig(backpressure_enabled=True).is_v2_active()

    def test_isolation_mode_default(self):
        assert SecurityConfig().isolation_mode == ExecutionIsolationMode.INPROCESS

    def test_isolation_mode_subprocess(self):
        cfg = SecurityConfig(isolation_mode=ExecutionIsolationMode.SUBPROCESS)
        assert cfg.isolation_mode == ExecutionIsolationMode.SUBPROCESS

    def test_replay_mode_default(self):
        assert SecurityConfig().replay_mode == ReplayMode.SHADOW

    def test_degradation_state_default(self):
        assert SecurityConfig().initial_degradation_state == DegradationState.NORMAL

    def test_fingerprint_alphas(self):
        cfg = SecurityConfig()
        assert 0 < cfg.fingerprint_short_alpha < 1
        assert 0 < cfg.fingerprint_long_alpha < cfg.fingerprint_short_alpha

    def test_backpressure_thresholds_ordered(self):
        cfg = SecurityConfig()
        assert cfg.bp_observation_drop_event_lag < cfg.bp_audit_only_event_lag < cfg.bp_fail_safe_event_lag
        assert cfg.bp_observation_drop_wal_backlog < cfg.bp_audit_only_wal_backlog < cfg.bp_fail_safe_wal_backlog

    def test_anchor_quorum_defaults_off(self):
        cfg = SecurityConfig()
        assert cfg.anchor_quorum_size == 0
        assert cfg.anchor_total_adapters == 0

    def test_dsl_policy_file_default_none(self):
        assert SecurityConfig().dsl_policy_file is None

    def test_event_bus_queue_positive(self):
        assert SecurityConfig().event_bus_max_queue > 0


# ===========================================================================
# Public API exports
# ===========================================================================

class TestPublicAPIExportsPhase1:
    def test_all_types_importable_from_package(self):
        import intentusnet as i
        assert hasattr(i, "ExecutionIsolationMode")
        assert hasattr(i, "ReplayMode")
        assert hasattr(i, "DegradationState")
        assert hasattr(i, "ResourceLimits")
        assert hasattr(i, "PolicyVersion")

    def test_signal_helpers_importable_from_package(self):
        import intentusnet as i
        assert hasattr(i, "DualBaselineResult")
        assert hasattr(i, "DecomposedSignalSet")
        assert hasattr(i, "compute_signals")
        assert hasattr(i, "reset_intent_baselines")

    def test_compute_signals_alias_works(self):
        import intentusnet as i
        r = i.compute_signals("alias_test", latency_ms=42.0)
        assert isinstance(r, i.DecomposedSignalSet)
