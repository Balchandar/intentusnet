from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


# ------------------------------------------------------------
# ENUMS
# ------------------------------------------------------------

class ErrorCode(Enum):
    ROUTING_ERROR = "routing_error"
    AGENT_ERROR = "agent_error"
    VALIDATION_ERROR = "validation_error"
    TRANSPORT_ERROR = "transport_error"
    UNKNOWN = "unknown"


class RoutingStrategy(Enum):
    PRIORITY = "priority"


# ------------------------------------------------------------
# CORE ERROR MODEL
# ------------------------------------------------------------

@dataclass
class ErrorInfo:
    code: ErrorCode
    message: str
    retryable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------
# WORKFLOW + ROUTING CONTEXT MODELS (NEW)
# ------------------------------------------------------------

@dataclass
class IntentContext:
    """
    Workflow/session state carried across steps.
    """
    sessionId: str
    workflowId: str
    memory: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RoutingOptions:
    """
    Developer-level routing instructions.
    """
    targetAgent: Optional[str] = None
    fallbackAgents: List[str] = field(default_factory=list)
    broadcast: bool = False


@dataclass
class RoutingMetadata:
    """
    Router-generated metadata for debugging, tracing, UI visibility.
    """
    selectedAgent: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    strategy: Optional[str] = None
    error: Optional[str] = None


# ------------------------------------------------------------
# INTENT MODELS
# ------------------------------------------------------------

@dataclass
class IntentRef:
    name: str
    version: str = "1.0"


@dataclass
class IntentMetadata:
    traceId: str
    requestId: str
    identityChain: List[str] = field(default_factory=list)
    strategy: RoutingStrategy = RoutingStrategy.PRIORITY


# ------------------------------------------------------------
# INTENT ENVELOPE (UPDATED)
# ------------------------------------------------------------

@dataclass
class IntentEnvelope:
    """
    Full envelope passed into router and agents.
    """
    intent: IntentRef
    payload: Dict[str, Any]
    metadata: IntentMetadata

    context: Optional[IntentContext] = None
    routing: Optional[RoutingOptions] = None
    routingMetadata: Optional[RoutingMetadata] = None


# ------------------------------------------------------------
# AGENT DEFINITIONS (unchanged)
# ------------------------------------------------------------

@dataclass
class AgentIdentity:
    agentId: str
    version: str = "1.0"


@dataclass
class Capability:
    name: str
    intents: List[str]
    priority: int = 100


@dataclass
class AgentDefinition:
    name: str
    capabilities: List[Capability]


# ------------------------------------------------------------
# AGENT RESPONSE
# ------------------------------------------------------------

@dataclass
class AgentResponse:
    payload: Optional[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorInfo] = None

    @property
    def status(self) -> str:
        return "success" if self.error is None else "error"

    @staticmethod
    def success(payload: Dict[str, Any]):
        return AgentResponse(payload=payload, error=None)

    @staticmethod
    def failure(error: ErrorInfo):
        return AgentResponse(payload=None, error=error)

# ---------------------------
# EMCL Envelope (Protocol)
# ---------------------------

from dataclasses import dataclass, field
from typing import List


@dataclass
class EMCLEnvelope:
    """
    Encrypted Message Context Layer (EMCL) envelope.
    Produced by encryption providers (AES-GCM or HMAC).

    This is a *protocol model* used by transports, router-entry,
    and security layer for decrypt/verify.
    """
    emclVersion: str
    ciphertext: str
    nonce: str
    hmac: str
    identityChain: List[str] = field(default_factory=list)
