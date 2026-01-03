"""
Structured Failure System - Typed, queryable failures.

All failures are:
- Typed (no generic exceptions)
- Structured (queryable fields)
- Persisted (in WAL and execution record)
- Classified (recoverable vs. non-recoverable)
"""

from .models import (
    FailureType,
    StructuredFailure,
    RecoveryStrategy,
)
from .registry import FailureRegistry

__all__ = [
    "FailureType",
    "StructuredFailure",
    "RecoveryStrategy",
    "FailureRegistry",
]
