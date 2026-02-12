"""
Time Machine UI Module (Phase II)

Read-only, verification-first system for execution inspection.

CRITICAL CONSTRAINTS:
- Read-only by default
- No silent failures
- No protocol shortcuts
- UI consumes backend contracts exactly
- UI must not invent data
- Signature MUST verify before rendering content
- Decryption must be explicit and user-triggered
- Never auto-decrypt
"""

from intentusnet.phase2.timemachine.api import (
    TimeMachineAPI,
    ExecutionQuery,
    ExecutionDetailResponse,
    ProofExportBundle,
    TimelineEntry,
    VerificationStatus,
)

__all__ = [
    "TimeMachineAPI",
    "ExecutionQuery",
    "ExecutionDetailResponse",
    "ProofExportBundle",
    "TimelineEntry",
    "VerificationStatus",
]
