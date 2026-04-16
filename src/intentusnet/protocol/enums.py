# FILE: src/intentusnet/protocol/enums.py
from enum import Enum


class Priority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    @property
    def weight(self) -> int:
        """
        Numeric weight used for routing decisions.
        Higher number = higher priority.
        """
        if self == Priority.HIGH:
            return 3
        if self == Priority.NORMAL:
            return 2
        return 1


class RoutingStrategy(Enum):
    DIRECT = "direct"
    FALLBACK = "fallback"
    BROADCAST = "broadcast"
    PARALLEL = "parallel"


class ErrorCode(Enum):
    VALIDATION_ERROR="VALIDATION_ERROR"
    AGENT_ERROR = "AGENT_ERROR"
    ROUTING_ERROR = "ROUTING_ERROR"
    CAPABILITY_NOT_FOUND = "CAPABILITY_NOT_FOUND"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    RATE_LIMIT = "RATE_LIMIT"
    INTERNAL_AGENT_ERROR = "INTERNAL_AGENT_ERROR"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    WORKFLOW_ABORTED = "WORKFLOW_ABORTED"
    EMCL_FAILURE = "EMCL_FAILURE"

    # Security Kernel error codes (v1.5.2+)
    SIDE_EFFECT_BLOCKED = "SIDE_EFFECT_BLOCKED"     # undeclared side-effect attempted
    ANOMALY_DETECTED = "ANOMALY_DETECTED"           # execution fingerprint anomaly
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"         # exact-once duplicate detected
    CAPABILITY_VIOLATION = "CAPABILITY_VIOLATION"   # capability contract breach
    MCP_VIOLATION = "MCP_VIOLATION"                 # tool not mapped to registry
