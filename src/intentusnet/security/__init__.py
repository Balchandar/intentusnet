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
- event_bus: Unified security event model + in-process dispatcher
- causality_index: Derivation-based execution graph with segmented storage
- backpressure: Degradation state machine (NORMAL → FAIL_SAFE)
- fingerprint_v2: Adaptive dual-baseline EWMA fingerprint engine
- circuit_breaker_v2: Per-intent circuit breaker on latency+error signals
- capability_governor_v2: Capability suspension on behaviour signal
- policy_engine_v2: Versioned policy engine with hot-reload
- resource_governor: Advisory resource measurement and limit checking
- isolation_manager: INPROCESS/SUBPROCESS execution isolation wrapper
- side_effect_stubs: Test-double adapters (Null/Recording/Fixed/Error/Interceptor)
- replay_engine: Deterministic re-execution comparison (SHADOW/AUDIT/ENFORCE)
- trust_anchor_v2: External confirmation quorum for WAL entry hashes
- wal_sampler: Periodic background WAL integrity sampling
"""

from .types import (
    ExecutionIsolationMode,
    ReplayMode,
    DegradationState,
    ResourceLimits,
    PolicyVersion,
)

from .fingerprint_v2 import (
    EWMAProfile,
    AdaptiveFingerprintEngineV2,
)

from .event_bus import (
    SecurityEventType,
    SecurityEvent,
    SecurityEventBus,
)

from .causality_index import (
    ExecutionNode,
    CausalityIndex,
)

from .backpressure import (
    BackpressureMetrics,
    BackpressureTransition,
    BackpressureManager,
    from_config as backpressure_from_config,
)

from .signals import (
    DualBaselineResult,
    DecomposedSignalSet,
    compute as compute_signals,
    reset_intent_baselines,
)

from .circuit_breaker_v2 import (
    CircuitState,
    CircuitTransition,
    CircuitBreaker,
)

from .capability_governor_v2 import (
    SuspensionEvent,
    CapabilityGovernor,
)

from .policy_engine_v2 import (
    PolicyDecisionV2,
    PolicyEngineV2,
)

from .resource_governor import (
    ResourceMeasurement,
    ResourceBreach,
    ResourceGovernor,
)

from .isolation_manager import (
    IsolationResult,
    IsolationManager,
)

from .side_effect_stubs import (
    SideEffectCall,
    NullSideEffectAdapter,
    RecordingStubAdapter,
    FixedResponseStubAdapter,
    ErrorStubAdapter,
    SideEffectInterceptor,
)

from .replay_engine import (
    ReplayDivergenceError,
    ReplayComparisonResult,
    SecurityReplayEngine,
)

from .trust_anchor_v2 import (
    ITrustAnchorAdapter,
    TrustAnchorConfirmation,
    AnchorStatus,
    TrustAnchorManager,
)

from .wal_sampler import (
    SamplerPassResult,
    WALSampler,
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

    # v2.1 Adaptive Fingerprint Engine
    "EWMAProfile",
    "AdaptiveFingerprintEngineV2",

    # v2.1 Event Bus
    "SecurityEventType",
    "SecurityEvent",
    "SecurityEventBus",

    # v2.1 Causality
    "ExecutionNode",
    "CausalityIndex",

    # v2.1 Backpressure
    "BackpressureMetrics",
    "BackpressureTransition",
    "BackpressureManager",
    "backpressure_from_config",

    # v2.1 Signals
    "DualBaselineResult",
    "DecomposedSignalSet",
    "compute_signals",
    "reset_intent_baselines",

    # v2.1 Circuit Breaker
    "CircuitState",
    "CircuitTransition",
    "CircuitBreaker",

    # v2.1 Capability Governor
    "SuspensionEvent",
    "CapabilityGovernor",

    # v2.1 Policy Engine v2
    "PolicyDecisionV2",
    "PolicyEngineV2",

    # v2.1 Resource Governor
    "ResourceMeasurement",
    "ResourceBreach",
    "ResourceGovernor",

    # v2.1 Isolation Manager
    "IsolationResult",
    "IsolationManager",

    # v2.1 Side-Effect Stubs
    "SideEffectCall",
    "NullSideEffectAdapter",
    "RecordingStubAdapter",
    "FixedResponseStubAdapter",
    "ErrorStubAdapter",
    "SideEffectInterceptor",

    # v2.1 Security Replay Engine
    "ReplayDivergenceError",
    "ReplayComparisonResult",
    "SecurityReplayEngine",

    # v2.1 Trust Anchor
    "ITrustAnchorAdapter",
    "TrustAnchorConfirmation",
    "AnchorStatus",
    "TrustAnchorManager",

    # v2.1 WAL Sampler
    "SamplerPassResult",
    "WALSampler",

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
