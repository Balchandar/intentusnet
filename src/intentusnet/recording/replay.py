"""
Historical Response Retrieval (Phase I)

IMPORTANT SEMANTIC CLARIFICATION:

This module provides RETRIEVAL of historically recorded responses,
NOT re-execution or replay of agent logic.

What retrieve() does:
- Returns the exact finalResponse stored at execution time
- Verifies envelope hash match (optional)
- Provides metadata about the retrieval

What retrieve() does NOT do:
- Re-execute any agent code
- Invoke routing logic
- Contact external systems
- Validate that current system would produce the same response

The term "replay" is DEPRECATED because it implies re-execution.
Use "retrieve" or "historical response retrieval" instead.

See: docs/phase-i-remediation-plan.md Section 4
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Optional, Any

from intentusnet.utils.timestamps import now_iso

from .models import ExecutionRecord, sha256_hex
from .models import _to_plain


class RetrievalError(RuntimeError):
    """Raised when historical response cannot be retrieved."""
    pass


# Backward compatibility alias (deprecated)
ReplayError = RetrievalError


@dataclass
class RetrievalResult:
    """
    Result of historical response retrieval.

    Attributes:
        response: The exact finalResponse recorded at execution time.
                  This is a LOOKUP, not a re-execution.
        execution_id: The execution identifier from the record.
        envelope_hash_ok: True if provided envelope matches recorded envelope.
        retrieval_timestamp: When this retrieval occurred.
        warning: Mandatory warning clarifying semantics.
    """
    response: Any
    execution_id: str
    envelope_hash_ok: bool
    retrieval_timestamp: str
    warning: str


# Backward compatibility alias (deprecated)
ReplayResult = RetrievalResult


class HistoricalResponseEngine:
    """
    Engine for retrieving historically recorded execution responses.

    IMPORTANT: This is a LOOKUP operation, not re-execution.

    retrieve() returns the stored finalResponse exactly as recorded.
    No agent code is executed. No routing occurs.

    Use cases:
    - Audit trail inspection
    - Incident investigation
    - Compliance evidence

    NOT a use case:
    - Validating current system behavior (use timemachine diff instead)
    - Testing agent logic (write actual tests)
    - Proving behavioral equivalence (requires re-execution, Phase II)
    """

    # Standard warning included in all retrieval results
    RETRIEVAL_WARNING = (
        "This is the RECORDED response from execution time. "
        "No agent code was executed. No routing occurred. "
        "This is a historical lookup, NOT re-execution. "
        "To compare with current system behavior, use 'intentusnet timemachine diff'."
    )

    def __init__(self, record: ExecutionRecord) -> None:
        self.record = record

    def is_retrievable(self) -> tuple[bool, str]:
        """
        Check if the historical response can be retrieved.

        Returns:
            (True, "OK") if retrievable
            (False, reason) if not retrievable
        """
        if not self.record.header.replayable:
            return False, self.record.header.replayableReason or "Marked not retrievable"
        if not self.record.finalResponse:
            return False, "Missing finalResponse in record"
        return True, "OK"

    def retrieve(self, *, envelope: Optional[Any] = None) -> RetrievalResult:
        """
        Retrieve the historically recorded response.

        This is a LOOKUP operation. No agents are executed.
        The stored finalResponse is returned exactly as recorded.

        Args:
            envelope: Optional envelope to verify hash match.
                      If provided, envelope_hash_ok indicates whether
                      it matches the recorded envelope.

        Returns:
            RetrievalResult with the stored response and metadata.

        Raises:
            RetrievalError: If the response cannot be retrieved.
        """
        ok, reason = self.is_retrievable()
        if not ok:
            raise RetrievalError(f"Historical response not retrievable: {reason}")

        envelope_hash_ok = True
        if envelope is not None:
            recorded_hash = self.record.header.envelopeHash
            provided_hash = sha256_hex(_to_plain(envelope))
            envelope_hash_ok = (recorded_hash == provided_hash)

        return RetrievalResult(
            response=self.record.finalResponse,
            execution_id=self.record.header.executionId,
            envelope_hash_ok=envelope_hash_ok,
            retrieval_timestamp=now_iso(),
            warning=self.RETRIEVAL_WARNING,
        )


# ===========================================================================
# Backward Compatibility (DEPRECATED)
# ===========================================================================

class ReplayEngine:
    """
    DEPRECATED: Use HistoricalResponseEngine instead.

    This class exists for backward compatibility only.
    The term "replay" incorrectly implies re-execution.

    Migration:
        # Old (deprecated)
        engine = ReplayEngine(record)
        result = engine.replay(env=envelope)

        # New (preferred)
        engine = HistoricalResponseEngine(record)
        result = engine.retrieve(envelope=envelope)
    """

    def __init__(self, record: ExecutionRecord) -> None:
        warnings.warn(
            "ReplayEngine is deprecated. Use HistoricalResponseEngine. "
            "'Replay' incorrectly implies re-execution; this is actually retrieval.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._engine = HistoricalResponseEngine(record)
        self.record = record

    def is_replayable(self) -> tuple[bool, str]:
        """DEPRECATED: Use HistoricalResponseEngine.is_retrievable()"""
        return self._engine.is_retrievable()

    def replay(self, *, env: Optional[Any] = None) -> RetrievalResult:
        """
        DEPRECATED: Use HistoricalResponseEngine.retrieve()

        This method returns the stored response. It does NOT re-execute
        any agent code or routing logic.
        """
        warnings.warn(
            "replay() is deprecated. Use HistoricalResponseEngine.retrieve(). "
            "This is a lookup operation, not re-execution.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._engine.retrieve(envelope=env)
