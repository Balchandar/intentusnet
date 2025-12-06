class IntentusError(Exception):
    """Base SDK error."""


class RoutingError(IntentusError):
    """Routing or registry failure."""


class AgentError(IntentusError):
    """Agent execution failure."""


class EMCLValidationError(IntentusError):
    """EMCL envelope validation failed."""
