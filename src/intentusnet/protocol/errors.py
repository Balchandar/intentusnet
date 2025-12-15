from __future__ import annotations


class IntentusError(Exception):
    """Base IntentusNet error."""


class RoutingError(IntentusError):
    """Routing or registry failure."""


class AgentError(IntentusError):
    """Agent execution failure."""


class EMCLValidationError(IntentusError):
    """EMCL envelope validation or crypto failure."""


class JWTAuthError(IntentusError):
    """JWT authentication or validation failure."""
