from __future__ import annotations

"""
Agent protocol models used by IntentusNet runtimes.

These models are shared across:
  - local agents
  - remote agent proxies
  - node execution gateways
  - discovery registries
  - runtime/router metadata
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from .intent import IntentRef


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

@dataclass
class AgentIdentity:
    """
    Unique identity metadata for an agent.
    """
    agentId: str
    tenantId: Optional[str] = None


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

@dataclass
class Capability:
    """
    Describes what an agent can do.

    intent:
        IntentRef object referencing the intent this capability handles.

    inputSchema / outputSchema:
        JSON-schema-like structures to describe I/O.
        Not strictly validated at runtime but valuable for:
          - client SDKs
          - documentation
          - schema validation layers
          - MCP-like tool definitions
    """
    intent: IntentRef
    inputSchema: Dict[str, Any] = field(default_factory=dict)
    outputSchema: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@dataclass
class AgentEndpoint:
    """
    Physical location of an agent.

    type:
        'local' | 'http' | 'zmq' | 'websocket' | 'mcp' | ...

    address:
        If local: "local"
        If remote: URL or socket address
    """
    type: str = "local"
    address: str = "local"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@dataclass
class AgentHealth:
    """
    Observability + discovery metadata.
    """
    status: str = "unknown"      # healthy | degraded | unhealthy | unknown
    lastHeartbeat: str = ""


# ---------------------------------------------------------------------------
# Runtime Info
# ---------------------------------------------------------------------------

@dataclass
class AgentRuntimeInfo:
    """
    Metadata about the agent's runtime environment.
    Useful for debugging and observability.
    """
    language: str = "python"
    environment: str = "local"
    scaling: str = "manual"      # manual | autoscale | external


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

@dataclass
class AgentDefinition:
    """
    Canonical definition for an agent inside IntentusNet.

    Fields intentionally support:
      - single-node operation
      - distributed multi-node clusters
      - remote agent proxies
      - discovery registries
      - future autoscaling

    nodeId:
        None = local agent inside this runtime
        string = agent belongs to a remote node

    nodePriority:
        Lower → preferred by router when multiple nodes can handle same intent.

    isRemote:
        Convenience flag for UI / logging / dashboards.
    """

    name: str
    version: str = "1.0"

    nodeId: Optional[str] = None
    nodePriority: int = 100
    isRemote: bool = False

    identity: AgentIdentity = field(
        default_factory=lambda: AgentIdentity(agentId=str(uuid.uuid4()))
    )

    capabilities: List[Capability] = field(default_factory=list)

    endpoint: AgentEndpoint = field(default_factory=AgentEndpoint)
    health: AgentHealth = field(default_factory=AgentHealth)
    runtime: AgentRuntimeInfo = field(default_factory=AgentRuntimeInfo)
