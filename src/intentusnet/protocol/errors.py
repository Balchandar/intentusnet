from typing import Optional
from .enums import ErrorCode


class IntentusError(Exception):
    def __init__(self, message: str, code: Optional[ErrorCode] = None):
        super().__init__(message)
        self.code = code or ErrorCode.INTERNAL_ERROR


class RoutingError(IntentusError):
     """Raised when routing fails."""


class ValidationError(IntentusError):
    """Raised when Validation fails."""

class EMCLValidationError(IntentusError):
    """Raised when EMCL envelope validation or decryption fails."""
