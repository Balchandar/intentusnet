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
# Capability Metadata (Security Kernel extensions — all fields optional)
# ---------------------------------------------------------------------------

@dataclass
class LatencyProfile:
    """
    Expected execution timing for a capability.
    Used by ExecutionFingerprintEngine to detect anomalies.
    """
    min_ms: float = 0.0
    max_ms: float = 30_000.0
    timeout_threshold_ms: float = 30_000.0


@dataclass
class CapabilityMetadata:
    """
    Optional security-kernel metadata for a Capability.

    Rules:
    - If absent on a Capability → permissive mode (no enforcement).
    - If present + SecurityConfig.strict_mode=True → fully enforced.

    capability_scope:
        List of caller scope strings allowed to invoke this intent.
        Empty list = any scope allowed.

    allowed_state_transitions:
        Map of from_state → [to_state, ...] for state machine enforcement.
        None = no state transition restrictions.

    side_effect_signature:
        List of adapter IDs this capability is permitted to invoke.
        Empty list = no side-effects allowed (in strict mode).

    latency_profile:
        Expected latency range; used for fingerprint anomaly baselines.

    retry_pattern:
        "none" | "idempotent" | "at-most-once" | "at-least-once"

    max_retries:
        Maximum retry attempts before treating as anomaly.
    """
    capability_scope: List[str] = field(default_factory=list)
    allowed_state_transitions: Optional[Dict[str, List[str]]] = None
    side_effect_signature: List[str] = field(default_factory=list)
    latency_profile: Optional[LatencyProfile] = None
    retry_pattern: str = "none"
    max_retries: int = 0


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

    metadata:
        Optional security-kernel metadata (CapabilityMetadata).
        Absent = permissive mode. Present + strict_mode = enforced.
    """
    intent: IntentRef
    inputSchema: Dict[str, Any] = field(default_factory=dict)
    outputSchema: Dict[str, Any] = field(default_factory=dict)
    metadata: Optional[CapabilityMetadata] = None


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
