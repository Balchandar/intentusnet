# FILE: src/intentusnet/protocol/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
from .enums import Priority, RoutingStrategy, ErrorCode


# -------------------------
# INTENTS
# -------------------------

@dataclass
class IntentRef:
    name: str
    version: str = "1.0"


@dataclass
class IntentContext:
    sessionId: str
    workflowId: str
    memory: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class IntentMetadata:
    timestamp: str
    sourceAgent: Optional[str] = None
    priority: Priority = Priority.NORMAL
    traceId: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlationId: str = field(default_factory=lambda: str(uuid.uuid4()))
    tags: List[str] = field(default_factory=list)


@dataclass
class RoutingOptions:
    targetAgent: Optional[str] = None
    broadcast: bool = False
    fallbackAgents: List[str] = field(default_factory=list)


@dataclass
class RoutingMetadata:
    routeType: RoutingStrategy = RoutingStrategy.DIRECT
    previousAgents: List[str] = field(default_factory=list)
    retryCount: int = 0


@dataclass
class IntentEnvelope:
    version: str
    intent: IntentRef
    payload: Dict[str, Any]
    context: IntentContext
    metadata: IntentMetadata
    routing: RoutingOptions = field(default_factory=RoutingOptions)
    routingMetadata: RoutingMetadata = field(default_factory=RoutingMetadata)


# -------------------------
# RESPONSE & ERRORS
# -------------------------

@dataclass
class ErrorInfo:
    code: ErrorCode
    message: str
    retryable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    version: str
    status: str
    payload: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]
    error: Optional[ErrorInfo] = None

    @staticmethod
    def success(payload: Any, metadata: Optional[Dict[str, Any]] = None) -> "AgentResponse":
        return AgentResponse(
            version="1.0",
            status="success",
            payload=payload,
            metadata=metadata or {},
            error=None,
        )

    @staticmethod
    def failure(error: ErrorInfo, metadata: Optional[Dict[str, Any]] = None) -> "AgentResponse":
        return AgentResponse(
            version="1.0",
            status="error",
            payload=None,
            metadata=metadata or {},
            error=error,
        )


# -------------------------
# AGENT DEFINITION (UPDATED)
# -------------------------

@dataclass
class AgentIdentity:
    agentId: str
    roles: List[str] = field(default_factory=list)
    signingKeyId: Optional[str] = None


@dataclass
class Capability:
    intent: IntentRef
    inputSchema: Dict[str, Any]
    outputSchema: Dict[str, Any]
    examples: List[Dict[str, Any]] = field(default_factory=list)
    fallbackAgents: List[str] = field(default_factory=list)
    priority: int = 0


@dataclass
class AgentEndpoint:
    type: str  # local | http | zeromq | websocket | grpc
    address: str


@dataclass
class AgentHealth:
    status: str
    lastHeartbeat: str


@dataclass
class AgentRuntimeInfo:
    language: str
    environment: str
    scaling: str  # auto | manual


# RECOMMENDED NEW SHAPE

@dataclass
class AgentDefinition:
    name: str
    version: str = "1.0"
    capabilities: List[Capability] = field(default_factory=list)

    # Optional metadata for distributed mode / future features
    identity: Optional[AgentIdentity] = None
    endpoint: Optional[AgentEndpoint] = None
    health: Optional[AgentHealth] = None
    runtime: Optional[AgentRuntimeInfo] = None



# -------------------------
# ROUTER DECISION
# -------------------------

@dataclass
class RouterDecision:
    selectedAgent: str
    routingStrategy: RoutingStrategy
    fallbackOrder: List[str]
    reason: str
    traceId: str


# -------------------------
# EMCLEnvelope unchanged
# -------------------------

@dataclass
class EMCLEnvelope:
    emclVersion: str
    ciphertext: str
    nonce: str
    hmac: str
    identityChain: List[str] = field(default_factory=list)
