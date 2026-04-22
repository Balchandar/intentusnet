from .core.runtime import IntentusRuntime
from .core.router import IntentRouter
from .core.registry import AgentRegistry
from .core.client import IntentusClient
from .core.agent import BaseAgent
from .core.tracing import TraceSink
from .security.emcl.base import EMCLProvider

from .protocol import (
    AgentDefinition,
    Capability,
    IntentRef,
    IntentContext,
    IntentMetadata,
    IntentEnvelope,
    RoutingOptions,
    AgentResponse,
    ErrorInfo,
    RouterDecision,
    TraceSpan,
    Priority,
    RoutingStrategy,
    ErrorCode,
)

from .recording.models import ExecutionRecord
from .recording.replay import ReplayEngine
from .recording.store import FileExecutionStore

from .security.fingerprint_v2 import (
    EWMAProfile,
    AdaptiveFingerprintEngineV2,
)
from .security.event_bus import (
    SecurityEventType,
    SecurityEvent,
    SecurityEventBus,
)
from .security.causality_index import (
    ExecutionNode,
    CausalityIndex,
)
from .security.backpressure import (
    BackpressureMetrics,
    BackpressureTransition,
    BackpressureManager,
    from_config as backpressure_from_config,
)
from .security.types import (
    ExecutionIsolationMode,
    ReplayMode,
    DegradationState,
    ResourceLimits,
    PolicyVersion,
)
from .security.signals import (
    DualBaselineResult,
    DecomposedSignalSet,
    compute as compute_signals,
    reset_intent_baselines,
)
from .security.circuit_breaker_v2 import (
    CircuitState,
    CircuitTransition,
    CircuitBreaker,
)
from .security.capability_governor_v2 import (
    SuspensionEvent,
    CapabilityGovernor,
)
from .security.policy_engine_v2 import (
    PolicyDecisionV2,
    PolicyEngineV2,
)
from .security.resource_governor import (
    ResourceMeasurement,
    ResourceBreach,
    ResourceGovernor,
)
from .security.isolation_manager import (
    IsolationResult,
    IsolationManager,
)
from .security.config import SecurityConfig
from .security.kernel import SecurityKernelMiddleware
from .security.mcp_validation import MCPValidationMiddleware
from .security.fingerprint import ExecutionFingerprintEngine, AnomalyClass, AnomalyResult
from .security.side_effects import ISideEffectAdapter, SideEffectQuarantine, SideEffectNotAuthorizedError
from .security.audit import ForensicAuditEntry, ForensicAuditLog
from .wal.integrity import verify_wal_integrity, WALIntegrityResult
from .protocol.agent import CapabilityMetadata, LatencyProfile

__version__ = "1.5.2"

__all__ = [
    # Core runtime
    "IntentusRuntime",
    "IntentRouter",
    "AgentRegistry",
    "IntentusClient",
    "BaseAgent",

    # Protocol - Core types
    "IntentEnvelope",
    "IntentRef",
    "IntentContext",
    "IntentMetadata",
    "RoutingOptions",

    # Protocol - Agent types
    "AgentDefinition",
    "Capability",

    # Protocol - Response types
    "AgentResponse",
    "ErrorInfo",

    # Protocol - Enums
    "Priority",
    "RoutingStrategy",
    "ErrorCode",

    # Tracing
    "TraceSink",
    "RouterDecision",
    "TraceSpan",

    # Recording & Replay
    "ExecutionRecord",
    "ReplayEngine",
    "FileExecutionStore",

    # Security (Phase I)
    "EMCLProvider",

    # Security Kernel (v2.1 — Adaptive Fingerprint)
    "EWMAProfile",
    "AdaptiveFingerprintEngineV2",

    # Security Kernel (v2.1 — Event Bus)
    "SecurityEventType",
    "SecurityEvent",
    "SecurityEventBus",

    # Security Kernel (v2.1 — Causality)
    "ExecutionNode",
    "CausalityIndex",

    # Security Kernel (v2.1 — Backpressure)
    "BackpressureMetrics",
    "BackpressureTransition",
    "BackpressureManager",
    "backpressure_from_config",

    # Security Kernel (v2.1 — Types & Signals)
    "ExecutionIsolationMode",
    "ReplayMode",
    "DegradationState",
    "ResourceLimits",
    "PolicyVersion",
    "DualBaselineResult",
    "DecomposedSignalSet",
    "compute_signals",
    "reset_intent_baselines",

    # Security Kernel (v2.1 — Circuit Breaker)
    "CircuitState",
    "CircuitTransition",
    "CircuitBreaker",

    # Security Kernel (v2.1 — Capability Governor)
    "SuspensionEvent",
    "CapabilityGovernor",

    # Security Kernel (v2.1 — Policy Engine v2)
    "PolicyDecisionV2",
    "PolicyEngineV2",

    # Security Kernel (v2.1 — Resource Governor)
    "ResourceMeasurement",
    "ResourceBreach",
    "ResourceGovernor",

    # Security Kernel (v2.1 — Isolation Manager)
    "IsolationResult",
    "IsolationManager",

    # Security Kernel (v1.5.2)
    "SecurityConfig",
    "SecurityKernelMiddleware",
    "MCPValidationMiddleware",
    "ExecutionFingerprintEngine",
    "AnomalyClass",
    "AnomalyResult",
    "ISideEffectAdapter",
    "SideEffectQuarantine",
    "SideEffectNotAuthorizedError",
    "ForensicAuditEntry",
    "ForensicAuditLog",

    # WAL Integrity API
    "verify_wal_integrity",
    "WALIntegrityResult",

    # Capability Metadata
    "CapabilityMetadata",
    "LatencyProfile",

    # Version
    "__version__",
]
