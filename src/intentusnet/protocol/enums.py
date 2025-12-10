from enum import Enum, auto


class ErrorCode(str, Enum):
    ROUTING_ERROR = "routing_error"
    AGENT_ERROR = "agent_error"
    VALIDATION_ERROR = "validation_error"
    TRANSPORT_ERROR = "transport_error"
    INTERNAL_ERROR = "internal_error"


class RoutingStrategy(str, Enum):
    FIRST_MATCH = "first_match"
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
