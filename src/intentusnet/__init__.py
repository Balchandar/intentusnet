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
