"""
Security Kernel Configuration — Feature Flags

Default posture: audit_only=True, strict_mode=False.
Zero breaking changes on upgrade — all enforcement is opt-in.

To harden:
    cfg = SecurityConfig(strict_mode=True, audit_only=False)

v2.1 additions are grouped at the bottom; all default to non-enforcing so
upgrading from v1.5.2 → v2.x requires no configuration changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Import lazily-referenced types so that this file remains importable even
# when the rest of the v2 modules are not yet installed.
from .types import DegradationState, ExecutionIsolationMode, ReplayMode


@dataclass
class SecurityConfig:
    """
    Feature flags for the IntentusNet Security Kernel (v1 + v2.1).

    Enforcement levels
    ------------------
    audit_only=True  (default): log violations, never block
    strict_mode=True + audit_only=False: enforce and block

    All v2.1 flags default to off / passive so that the upgrade is
    backwards-compatible.
    """

    # -----------------------------------------------------------------------
    # Core enforcement mode (v1)
    # -----------------------------------------------------------------------
    strict_mode: bool = False
    audit_only: bool = True

    # -----------------------------------------------------------------------
    # Module toggles (v1)
    # -----------------------------------------------------------------------
    capability_contracts: bool = True
    state_transition_enforcement: bool = True
    wal_precommit: bool = True
    idempotency_enabled: bool = True
    fingerprint_enabled: bool = True
    side_effect_quarantine: bool = False   # off by default; enable per-deployment
    mcp_validation: bool = True
    forensic_audit: bool = True

    # -----------------------------------------------------------------------
    # Fingerprint thresholds (v1)
    # -----------------------------------------------------------------------
    anomaly_threshold: float = 0.75     # score >= this → suspicious
    malicious_threshold: float = 0.95   # score >= this → malicious
    fingerprint_window: int = 100       # sliding window size (samples)

    # -----------------------------------------------------------------------
    # Idempotency (v1)
    # -----------------------------------------------------------------------
    idempotency_ttl_seconds: int = 3600

    # -----------------------------------------------------------------------
    # v2.1 — Execution Isolation
    # -----------------------------------------------------------------------
    isolation_mode: ExecutionIsolationMode = ExecutionIsolationMode.INPROCESS
    # Maximum wall-clock seconds for a subprocess worker (0 = unlimited)
    subprocess_timeout_seconds: float = 30.0
    # Maximum RSS for subprocess workers in bytes (0 = unlimited)
    subprocess_max_memory_bytes: int = 0

    # -----------------------------------------------------------------------
    # v2.1 — Trust Anchoring
    # -----------------------------------------------------------------------
    trust_anchoring_enabled: bool = False
    # Minimum number of external anchors that must confirm before a chain
    # segment is considered FULLY_ANCHORED (0 = feature off)
    anchor_quorum_size: int = 0
    # Total number of available external anchor adapters
    anchor_total_adapters: int = 0

    # -----------------------------------------------------------------------
    # v2.1 — Causality Tracking
    # -----------------------------------------------------------------------
    causality_tracking_enabled: bool = False
    # Number of execution nodes per causality graph segment (affects I/O)
    causality_segment_size: int = 1000

    # -----------------------------------------------------------------------
    # v2.1 — Continuous WAL Monitor
    # -----------------------------------------------------------------------
    continuous_wal_monitor: bool = False
    # Fraction of historical entries sampled per verification pass (0.05 = 5%)
    wal_sample_fraction: float = 0.05
    # Seconds between verification passes (0 = disabled)
    wal_verify_interval_seconds: float = 60.0

    # -----------------------------------------------------------------------
    # v2.1 — Adaptive Fingerprint (dual-baseline EWMA)
    # -----------------------------------------------------------------------
    adaptive_fingerprint: bool = False
    # α for short-term EWMA (spike detection)
    fingerprint_short_alpha: float = 0.10
    # α for long-term EWMA (drift detection)
    fingerprint_long_alpha: float = 0.01
    # drift_score >= this → freeze baselines to prevent poisoning
    fingerprint_drift_freeze: float = 0.50

    # -----------------------------------------------------------------------
    # v2.1 — Active Defence
    # -----------------------------------------------------------------------
    active_defense_enabled: bool = False

    # Circuit breaker (uses latency + error signals)
    circuit_breaker_enabled: bool = False
    # Number of consecutive failures before opening the circuit
    circuit_breaker_failure_threshold: int = 5
    # Seconds the circuit stays open before moving to half-open
    circuit_breaker_timeout_seconds: float = 30.0

    # Kill switch — administrator-operated; kills specific intents
    kill_switch_enabled: bool = False

    # Capability governor (uses behavior signal only)
    capability_governor_enabled: bool = False
    # behavior_signal >= this → suspend capability
    capability_governor_threshold: float = 0.80

    # -----------------------------------------------------------------------
    # v2.1 — Side-effect Interception
    # -----------------------------------------------------------------------
    # Monkey-patches socket/subprocess/file open; detection only by default
    side_effect_interception: bool = False

    # -----------------------------------------------------------------------
    # v2.1 — Policy DSL
    # -----------------------------------------------------------------------
    # Path to a YAML/JSON policy file loaded by PolicyEngineV2 (None = inline rules)
    dsl_policy_file: Optional[str] = None
    # Re-load the policy file every N seconds (0 = load once at startup)
    policy_reload_interval_seconds: float = 0.0

    # -----------------------------------------------------------------------
    # v2.1 — Security Trace / Event Bus
    # -----------------------------------------------------------------------
    security_trace_enabled: bool = False
    # Maximum events queued in the in-process event bus before back-pressure
    event_bus_max_queue: int = 10_000

    # -----------------------------------------------------------------------
    # v2.1 — Deterministic Replay
    # -----------------------------------------------------------------------
    replay_enabled: bool = False
    replay_mode: ReplayMode = ReplayMode.SHADOW

    # -----------------------------------------------------------------------
    # v2.1 — Backpressure / Degradation State Machine
    # -----------------------------------------------------------------------
    backpressure_enabled: bool = False
    initial_degradation_state: DegradationState = DegradationState.NORMAL

    # Thresholds that trigger advancement to a worse state
    # (expressed as queue/backlog sizes; 0 = tier disabled)
    bp_observation_drop_event_lag: int = 5_000
    bp_audit_only_event_lag: int = 8_000
    bp_fail_safe_event_lag: int = 10_000

    bp_observation_drop_wal_backlog: int = 1_000
    bp_audit_only_wal_backlog: int = 5_000
    bp_fail_safe_wal_backlog: int = 9_000

    # Hysteresis: state improves only after pressure has been below threshold
    # for this many seconds
    bp_recovery_hysteresis_seconds: float = 10.0

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def is_enforcing(self) -> bool:
        """True when violations should block execution (not just log)."""
        return self.strict_mode and not self.audit_only

    def is_v2_active(self) -> bool:
        """True when at least one v2.1 subsystem is turned on."""
        return any([
            self.adaptive_fingerprint,
            self.active_defense_enabled,
            self.circuit_breaker_enabled,
            self.capability_governor_enabled,
            self.kill_switch_enabled,
            self.trust_anchoring_enabled,
            self.causality_tracking_enabled,
            self.continuous_wal_monitor,
            self.side_effect_interception,
            self.replay_enabled,
            self.backpressure_enabled,
            self.security_trace_enabled,
        ])
