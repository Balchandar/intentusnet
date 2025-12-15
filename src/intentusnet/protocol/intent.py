from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .enums import Priority, RoutingStrategy


# ---- Intent & Context ----

@dataclass
class IntentRef:
    name: str
    version: str = "1.0"


@dataclass
class IntentContext:
    sourceAgent: str
    timestamp: str
    priority: Priority = Priority.NORMAL
    tags: List[str] = field(default_factory=list)


@dataclass
class IntentMetadata:
    requestId: str
    source: str
    createdAt: str
    traceId: str
    identityChain: List[str] = field(default_factory=list)

@dataclass
class RoutingOptions:
    strategy: RoutingStrategy = RoutingStrategy.DIRECT
    targetAgent: Optional[str] = None
    fallbackAgents: List[str] = field(default_factory=list)



@dataclass
class RoutingMetadata:
    decisionPath: List[str] = field(default_factory=list)
    retries: int = 0


@dataclass
class IntentEnvelope:
    """
    Canonical wire-level representation of an intent request.
    """
    version: str
    intent: IntentRef
    payload: Dict[str, Any]
    context: IntentContext
    metadata: IntentMetadata
    routing: RoutingOptions = field(default_factory=RoutingOptions)
    routingMetadata: RoutingMetadata = field(default_factory=RoutingMetadata)
