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

__version__ = "0.3.0"

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

    # Security
    "EMCLProvider",

    # Version
    "__version__",
]
