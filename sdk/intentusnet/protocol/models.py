from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
from .enums import Priority, RoutingStrategy, ErrorCode


# ---- Intent & Context ----

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
    sourceAgent: Optional[str]
    timestamp: str
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


# ---- Agent response & errors ----

@dataclass
class ErrorInfo:
    code: ErrorCode
    message: str
    retryable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    version: str
    status: str  # success | error
    payload: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]
    error: Optional[ErrorInfo] = None


# ---- Agent & Registry Models ----

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
    type: str  # local | zeromq | http | grpc | websocket | mcp
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


@dataclass
class AgentDefinition:
    name: str
    version: str
    identity: AgentIdentity
    capabilities: List[Capability]
    endpoint: AgentEndpoint
    health: AgentHealth
    runtime: AgentRuntimeInfo


@dataclass
class RouterDecision:
    selectedAgent: str
    routingStrategy: RoutingStrategy
    fallbackOrder: List[str]
    reason: str
    traceId: str


# ---- Tracing & lifecycle ----

@dataclass
class TraceSpan:
    traceId: str
    spanId: str
    parentSpanId: Optional[str]
    agent: str
    intent: str
    startTime: str
    endTime: str
    latencyMs: int
    status: str
    error: Optional[ErrorInfo]


@dataclass
class LifecycleEvent:
    eventType: str  # REGISTER | DEREGISTER | HEARTBEAT | READY | DRAINING
    timestamp: str
    agent: Dict[str, Any]
    eventPayload: Dict[str, Any]


# ---- Transport & EMCL ----

@dataclass
class TransportNegotiation:
    minVersion: str
    maxVersion: str


@dataclass
class TransportEnvelope:
    protocol: str
    protocolNegotiation: TransportNegotiation
    messageType: str  # intent | response | event
    headers: Dict[str, Any]
    body: Dict[str, Any]


@dataclass
class EMCLEnvelope:
    emclVersion: str
    ciphertext: str
    nonce: str
    hmac: str
    identityChain: List[str] = field(default_factory=list)
