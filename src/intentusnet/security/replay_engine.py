"""
Security Kernel v2.1 — Deterministic Replay Engine

Re-executes a previously recorded intent invocation and compares the new
response against the original using stable SHA-256 hashing.  Behavioural
divergence can indicate:

  * Uncontrolled non-determinism (time, randomness, global state)
  * Logic regression after a deployment
  * Adversarial input that produces a different response under controlled
    conditions

Three enforcement modes (``ReplayMode`` from ``types.py``)
----------------------------------------------------------
SHADOW
    Re-execute silently.  On divergence emit a ``REPLAY_DIVERGENCE`` event via
    the SecurityEventBus but let execution continue normally.  Safest mode for
    warming up comparison coverage on production traffic.

AUDIT
    Same as SHADOW, plus write a ``ForensicAuditEntry`` with
    ``decision="replay"`` to the ForensicAuditLog on divergence.  Useful when
    you need tamper-evident records of every divergent replay.

ENFORCE
    Raise ``ReplayDivergenceError`` on divergence.  The original response is
    NOT returned to the caller.  Use this as a deployment gate or for
    high-assurance intents where determinism is contractually required.

Comparison
----------
Both the recorded and replayed responses are serialised to canonical JSON via
``stable_hash()`` (the same function used by the WAL recorder) before hashing.
This means structurally identical responses with different key ordering or
float precision within epsilon are still considered equal.

The engine accepts ``new_response`` from any callable via ``execute()``; it can
also be invoked directly with ``compare()`` when the caller already has the new
response value (e.g. from a shadow execution path).

Thread safety
-------------
``SecurityReplayEngine`` is stateless beyond its configuration; all methods may
be called concurrently.  Any mutable state (``IsolationManager`` counters,
``ForensicAuditLog``) is thread-safe in the respective components.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .audit import ForensicAuditEntry, ForensicAuditLog
from .event_bus import SecurityEventBus, SecurityEventType
from .isolation_manager import IsolationManager
from .types import ReplayMode
from ..recording.models import ExecutionRecord, stable_hash


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ReplayDivergenceError(RuntimeError):
    """
    Raised in ENFORCE mode when the replayed response differs from the
    originally recorded response.

    Attributes
    ----------
    result
        The populated ``ReplayComparisonResult`` (``matched=False``).
    """

    def __init__(self, result: "ReplayComparisonResult") -> None:
        self.result = result
        super().__init__(
            f"Replay divergence for execution_id={result.execution_id!r}: "
            f"original_hash={result.original_hash[:12]}… "
            f"replay_hash={result.replay_hash[:12]}…"
        )


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ReplayComparisonResult:
    """
    Outcome of one replay comparison.

    ``matched``        — True when both responses hash identically.
    ``original_hash``  — Stable hash of the recorded finalResponse.
    ``replay_hash``    — Stable hash of the new response produced by replay.
    ``execution_id``   — From the ExecutionRecord header.
    ``intent_name``    — Extracted from the envelope if present.
    ``mode``           — ReplayMode active at comparison time.
    ``wall_seconds``   — Wall time of the re-execution (0 when compare() used directly).
    ``timestamp``      — When the comparison was performed.
    """
    matched:        bool
    original_hash:  str
    replay_hash:    str
    execution_id:   str
    intent_name:    str
    mode:           ReplayMode
    wall_seconds:   float = 0.0
    timestamp:      float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "matched":       self.matched,
            "original_hash": self.original_hash,
            "replay_hash":   self.replay_hash,
            "execution_id":  self.execution_id,
            "intent_name":   self.intent_name,
            "mode":          self.mode.value,
            "wall_seconds":  round(self.wall_seconds, 4),
            "timestamp":     self.timestamp,
        }


# ---------------------------------------------------------------------------
# SecurityReplayEngine
# ---------------------------------------------------------------------------

class SecurityReplayEngine:
    """
    Deterministic replay engine for intent executions.

    Parameters
    ----------
    mode
        SHADOW, AUDIT, or ENFORCE (see module docstring).
    isolation_manager
        Optional ``IsolationManager`` used by ``execute()`` to run the
        callable.  If None, INPROCESS execution with no resource limits is
        used.
    event_bus
        If set, ``REPLAY_DIVERGENCE`` events are emitted on divergence.
    audit_log
        Required in AUDIT mode; ignored in SHADOW/ENFORCE.
    """

    def __init__(
        self,
        mode:              ReplayMode = ReplayMode.SHADOW,
        *,
        isolation_manager: Optional[IsolationManager] = None,
        event_bus:         Optional[SecurityEventBus] = None,
        audit_log:         Optional[ForensicAuditLog] = None,
    ) -> None:
        self._mode      = mode
        self._isolation = isolation_manager or IsolationManager()
        self._event_bus = event_bus
        self._audit_log = audit_log

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        config:    Any,   # SecurityConfig; typed as Any to avoid circular import
        *,
        event_bus: Optional[SecurityEventBus] = None,
        audit_log: Optional[ForensicAuditLog] = None,
    ) -> "SecurityReplayEngine":
        """Build from a ``SecurityConfig`` instance."""
        from .isolation_manager import IsolationManager
        return cls(
            mode=config.replay_mode,
            isolation_manager=IsolationManager.from_config(config),
            event_bus=event_bus,
            audit_log=audit_log,
        )

    # ------------------------------------------------------------------
    # Core: compare pre-computed responses
    # ------------------------------------------------------------------

    def compare(
        self,
        record:       ExecutionRecord,
        new_response: Any,
        *,
        wall_seconds: float = 0.0,
    ) -> ReplayComparisonResult:
        """
        Compare ``new_response`` against the ``finalResponse`` in ``record``.

        Can be called directly when the replay execution was managed by the
        caller (e.g. a shadow A/B path in a production router).

        Raises ``ReplayDivergenceError`` in ENFORCE mode on divergence.
        """
        original_hash = stable_hash(record.finalResponse)
        replay_hash   = stable_hash(new_response)
        matched       = (original_hash == replay_hash)
        intent_name   = _extract_intent(record)

        result = ReplayComparisonResult(
            matched=matched,
            original_hash=original_hash,
            replay_hash=replay_hash,
            execution_id=record.header.executionId,
            intent_name=intent_name,
            mode=self._mode,
            wall_seconds=wall_seconds,
        )

        if not matched:
            self._handle_divergence(result, record)

        return result

    # ------------------------------------------------------------------
    # Core: execute and compare
    # ------------------------------------------------------------------

    def execute(
        self,
        record:     ExecutionRecord,
        fn:         Callable[..., Any],
        *args:      Any,
        **kwargs:   Any,
    ) -> ReplayComparisonResult:
        """
        Re-execute ``fn(*args, **kwargs)`` and compare the return value
        against the recorded ``finalResponse``.

        The callable receives the same positional/keyword arguments the caller
        supplies; the engine does not attempt to deserialise the envelope back
        into typed objects (that is the caller's responsibility).

        Re-execution runs via the configured ``IsolationManager``; in SUBPROCESS
        mode the function must be picklable.

        If the re-execution itself raises an exception, the result is
        ``matched=False`` with ``replay_hash="<exception>"`` and the exception
        is re-raised after the divergence handling (so audit/events are still
        recorded).
        """
        intent_name = _extract_intent(record)
        iso_result  = self._isolation.execute(
            fn, *args, intent_name=intent_name, **kwargs,
        )

        if not iso_result.success:
            exc_token = f"<exception:{type(iso_result.exception).__name__}>"
            result = ReplayComparisonResult(
                matched=False,
                original_hash=stable_hash(record.finalResponse),
                replay_hash=exc_token,
                execution_id=record.header.executionId,
                intent_name=intent_name,
                mode=self._mode,
                wall_seconds=iso_result.wall_seconds,
            )
            self._handle_divergence(result, record)
            if iso_result.exception is not None:
                raise iso_result.exception
            return result

        return self.compare(
            record,
            iso_result.return_value,
            wall_seconds=iso_result.wall_seconds,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> ReplayMode:
        return self._mode

    # ------------------------------------------------------------------
    # Internal divergence handling
    # ------------------------------------------------------------------

    def _handle_divergence(
        self,
        result: ReplayComparisonResult,
        record: ExecutionRecord,
    ) -> None:
        """Emit event, write audit entry, and/or raise depending on mode."""
        if self._event_bus is not None:
            self._event_bus.emit(
                SecurityEventType.REPLAY_DIVERGENCE,
                result.intent_name,
                execution_id=result.execution_id,
                payload={
                    "original_hash": result.original_hash,
                    "replay_hash":   result.replay_hash,
                    "mode":          result.mode.value,
                    "wall_seconds":  result.wall_seconds,
                },
            )

        if self._mode == ReplayMode.AUDIT and self._audit_log is not None:
            self._audit_log.record(
                ForensicAuditEntry(
                    intent_id=result.execution_id,
                    actor_id="replay_engine_v2",
                    input_hash=record.header.envelopeHash,
                    state_before=result.original_hash,
                    state_after=result.replay_hash,
                    validation_result="replay_divergence",
                    anomaly_score=1.0,
                    decision="replay",
                    wal_entry_hash=None,
                    timestamp=_utc_now(),
                    intent_name=result.intent_name,
                    execution_id=result.execution_id,
                )
            )

        if self._mode == ReplayMode.ENFORCE:
            raise ReplayDivergenceError(result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_intent(record: ExecutionRecord) -> str:
    """Best-effort extraction of intent name from envelope dict."""
    env = record.envelope
    if isinstance(env, dict):
        # Common envelope shapes
        for key in ("intent", "intent_name", "intentName"):
            val = env.get(key)
            if isinstance(val, str) and val:
                return val
        # Nested: {"intent": {"name": "…"}}
        intent_obj = env.get("intent")
        if isinstance(intent_obj, dict):
            name = intent_obj.get("name") or intent_obj.get("intentName")
            if isinstance(name, str) and name:
                return name
    return record.header.executionId


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
