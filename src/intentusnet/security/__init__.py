"""
IntentusNet Security Module

Phase I Components:
- compliance: Compliance mode configuration and validation
- emcl: Encrypted Model Context Layer (transport encryption)
- policy_engine: Security policy enforcement
- node_identity: Node identity management

Security Kernel (v1.5.2):
- config: SecurityConfig feature flags
- fingerprint: ExecutionFingerprintEngine — behavioral anomaly detection
- side_effects: ISideEffectAdapter + SideEffectQuarantine
- audit: ForensicAuditLog — tamper-evident compliance audit trail
- kernel: SecurityKernelMiddleware — central enforcement middleware
- mcp_validation: MCPValidationMiddleware — MCP tool → Registry enforcement

Security Kernel (v2.1):
- types: Shared enums/dataclasses (PolicyVersion, DegradationState, …)
- signals: Dual-baseline EWMA + four-signal decomposition
"""

from .types import (
    ExecutionIsolationMode,
    ReplayMode,
    DegradationState,
    ResourceLimits,
    PolicyVersion,
)

from .signals import (
    DualBaselineResult,
    DecomposedSignalSet,
    compute as compute_signals,
    reset_intent_baselines,
)

from .compliance import (
    ComplianceLevel,
    ComplianceConfig,
    ComplianceError,
    ComplianceValidator,
    set_global_compliance,
    get_global_compliance,
    require_compliance,
    validate_hash_truncation,
    get_sha256_full,
)

from .config import SecurityConfig

from .fingerprint import (
    ExecutionFingerprintEngine,
    AnomalyClass,
    AnomalyResult,
    FingerprintSample,
)

from .side_effects import (
    ISideEffectAdapter,
    SideEffectQuarantine,
    SideEffectNotAuthorizedError,
)

from .audit import (
    ForensicAuditEntry,
    ForensicAuditLog,
)

from .kernel import SecurityKernelMiddleware

from .mcp_validation import MCPValidationMiddleware

__all__ = [
    # v2.1 Types
    "ExecutionIsolationMode",
    "ReplayMode",
    "DegradationState",
    "ResourceLimits",
    "PolicyVersion",

    # v2.1 Signals
    "DualBaselineResult",
    "DecomposedSignalSet",
    "compute_signals",
    "reset_intent_baselines",

    # Phase I
    "ComplianceLevel",
    "ComplianceConfig",
    "ComplianceError",
    "ComplianceValidator",
    "set_global_compliance",
    "get_global_compliance",
    "require_compliance",
    "validate_hash_truncation",
    "get_sha256_full",

    # Security Kernel (v1.5.2)
    "SecurityConfig",
    "ExecutionFingerprintEngine",
    "AnomalyClass",
    "AnomalyResult",
    "FingerprintSample",
    "ISideEffectAdapter",
    "SideEffectQuarantine",
    "SideEffectNotAuthorizedError",
    "ForensicAuditEntry",
    "ForensicAuditLog",
    "SecurityKernelMiddleware",
    "MCPValidationMiddleware",
]
