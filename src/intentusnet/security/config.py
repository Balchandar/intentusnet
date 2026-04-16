"""
Security Kernel Configuration — Feature Flags

Default posture: audit_only=True, strict_mode=False.
Zero breaking changes on upgrade — all enforcement is opt-in.

To harden:
    cfg = SecurityConfig(strict_mode=True, audit_only=False)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SecurityConfig:
    """
    Feature flags for the IntentusNet Security Kernel.

    Enforcement levels:
      - audit_only=True  (default): log violations, never block
      - strict_mode=True + audit_only=False: enforce and block
    """

    # --- Core enforcement mode ---
    strict_mode: bool = False
    audit_only: bool = True

    # --- Module toggles ---
    capability_contracts: bool = True
    state_transition_enforcement: bool = True
    wal_precommit: bool = True
    idempotency_enabled: bool = True
    fingerprint_enabled: bool = True
    side_effect_quarantine: bool = False   # off by default; enable per-deployment
    mcp_validation: bool = True
    forensic_audit: bool = True

    # --- Fingerprint thresholds (anomaly_score range: 0.0 – 1.0) ---
    anomaly_threshold: float = 0.75     # score >= this → suspicious
    malicious_threshold: float = 0.95   # score >= this → malicious

    # --- Fingerprint sliding window (number of historical samples) ---
    fingerprint_window: int = 100

    # --- Idempotency TTL in seconds (0 = never expire) ---
    idempotency_ttl_seconds: int = 3600

    def is_enforcing(self) -> bool:
        """True when violations should block execution (not just log)."""
        return self.strict_mode and not self.audit_only
