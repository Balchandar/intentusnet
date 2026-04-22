"""
Security Kernel v2.1 — Side-Effect Stubs

Provides test-double ``ISideEffectAdapter`` implementations that can replace
real adapters during:
  * unit tests — assert what calls were made without actual I/O
  * deterministic replay — swallow or record side effects so the agent can
    be re-executed safely against recorded inputs

All stubs are thread-safe.

Adapters
--------
``NullSideEffectAdapter``
    Silently swallows every call; returns ``None``.  Use when you want replay
    to succeed without any I/O.

``RecordingStubAdapter``
    Records every call in an ordered list; returns a configurable response
    (default ``None``).  Use in tests to assert call count/payloads.

``FixedResponseStubAdapter``
    Returns a pre-configured value for every call; does not record payloads.
    Useful when the agent code inspects the adapter return value.

``ErrorStubAdapter``
    Raises a configurable exception on every call.  Use to test error paths.

``SideEffectInterceptor``
    Context manager wrapping a ``SideEffectQuarantine`` that temporarily
    replaces every registered adapter with a ``RecordingStubAdapter``.  On
    exit the original adapters are restored.  Keeps a unified call log across
    all intercepted adapters.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from .side_effects import ISideEffectAdapter, SideEffectQuarantine


# ---------------------------------------------------------------------------
# NullSideEffectAdapter
# ---------------------------------------------------------------------------

class NullSideEffectAdapter(ISideEffectAdapter):
    """
    No-op adapter.  Swallows every call and returns ``None``.

    Safe to install globally during deterministic replay when you want all
    side effects to be silent and non-destructive.
    """

    def __init__(self, adapter_id: str) -> None:
        self._id = adapter_id

    @property
    def adapter_id(self) -> str:
        return self._id

    def execute(self, payload: Dict[str, Any]) -> None:
        return None


# ---------------------------------------------------------------------------
# RecordingStubAdapter
# ---------------------------------------------------------------------------

@dataclass
class SideEffectCall:
    """One recorded invocation of a stub adapter."""
    adapter_id: str
    payload:    Dict[str, Any]
    seq:        int    # monotonically increasing call sequence number


class RecordingStubAdapter(ISideEffectAdapter):
    """
    Records every call in an ordered list and returns a configurable response.

    Parameters
    ----------
    adapter_id
        Must match the ``adapter_id`` used when registering with a quarantine.
    return_value
        Value returned by every ``execute()`` call.  Default: ``None``.
    seq_counter
        Optional shared counter so multiple adapters share a call-sequence
        namespace (e.g. inside ``SideEffectInterceptor``).
    """

    def __init__(
        self,
        adapter_id:   str,
        return_value: Any = None,
        *,
        seq_counter:  Optional["_SharedCounter"] = None,
    ) -> None:
        self._id           = adapter_id
        self._return_value = return_value
        self._calls:  List[SideEffectCall] = []
        self._lock    = threading.Lock()
        self._counter = seq_counter or _SharedCounter()

    @property
    def adapter_id(self) -> str:
        return self._id

    def execute(self, payload: Dict[str, Any]) -> Any:
        seq = self._counter.next()
        with self._lock:
            self._calls.append(
                SideEffectCall(
                    adapter_id=self._id,
                    payload=dict(payload),
                    seq=seq,
                )
            )
        return self._return_value

    @property
    def calls(self) -> List[SideEffectCall]:
        """Snapshot of recorded calls (copy; thread-safe)."""
        with self._lock:
            return list(self._calls)

    @property
    def call_count(self) -> int:
        with self._lock:
            return len(self._calls)

    def reset(self) -> None:
        """Clear recorded calls (e.g. between test cases)."""
        with self._lock:
            self._calls.clear()


# ---------------------------------------------------------------------------
# FixedResponseStubAdapter
# ---------------------------------------------------------------------------

class FixedResponseStubAdapter(ISideEffectAdapter):
    """
    Returns a fixed value for every call; does not record payloads.

    Useful when the agent inspects the adapter's return value but you do not
    need to assert on call arguments.
    """

    def __init__(self, adapter_id: str, return_value: Any) -> None:
        self._id    = adapter_id
        self._value = return_value

    @property
    def adapter_id(self) -> str:
        return self._id

    def execute(self, payload: Dict[str, Any]) -> Any:
        return self._value


# ---------------------------------------------------------------------------
# ErrorStubAdapter
# ---------------------------------------------------------------------------

class ErrorStubAdapter(ISideEffectAdapter):
    """
    Raises a configurable exception on every ``execute()`` call.

    Useful for testing error-handling paths in agent code.
    """

    def __init__(
        self,
        adapter_id:     str,
        exception:      Optional[BaseException] = None,
        exception_type: Optional[Type[BaseException]] = None,
        message:        str = "stub error",
    ) -> None:
        self._id        = adapter_id
        self._exception = exception or (exception_type or RuntimeError)(message)

    @property
    def adapter_id(self) -> str:
        return self._id

    def execute(self, payload: Dict[str, Any]) -> Any:
        raise self._exception


# ---------------------------------------------------------------------------
# SideEffectInterceptor (context manager)
# ---------------------------------------------------------------------------

class SideEffectInterceptor:
    """
    Context manager that wraps a live ``SideEffectQuarantine`` with recording
    stubs during a block of code.

    Usage::

        with SideEffectInterceptor(quarantine) as interceptor:
            quarantine.execute("email", "SendNotification", ["email"], {…})

        calls = interceptor.all_calls()
        assert calls[0].adapter_id == "email"

    On ``__exit__`` the original adapters are restored.

    Parameters
    ----------
    quarantine
        A ``SideEffectQuarantine`` instance whose adapters will be replaced.
    return_value
        Value all stubs return; defaults to ``None``.
    """

    def __init__(
        self,
        quarantine:   SideEffectQuarantine,
        return_value: Any = None,
    ) -> None:
        self._quarantine  = quarantine
        self._return_value = return_value
        self._originals:  Dict[str, ISideEffectAdapter] = {}
        self._stubs:      Dict[str, RecordingStubAdapter] = {}
        self._counter     = _SharedCounter()

    def __enter__(self) -> "SideEffectInterceptor":
        self._install()
        return self

    def __exit__(self, *_: object) -> None:
        self._restore()

    # ------------------------------------------------------------------
    # Call log
    # ------------------------------------------------------------------

    def all_calls(self) -> List[SideEffectCall]:
        """Return all recorded calls across all stubs, ordered by seq."""
        calls: List[SideEffectCall] = []
        for stub in self._stubs.values():
            calls.extend(stub.calls)
        return sorted(calls, key=lambda c: c.seq)

    def calls_for(self, adapter_id: str) -> List[SideEffectCall]:
        stub = self._stubs.get(adapter_id)
        return stub.calls if stub else []

    def call_count(self, adapter_id: Optional[str] = None) -> int:
        if adapter_id is not None:
            return len(self.calls_for(adapter_id))
        return len(self.all_calls())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _install(self) -> None:
        for aid in self._quarantine.registered_ids():
            reg = self._quarantine._registry.get(aid)
            if reg is None:
                continue
            original = reg.adapter
            self._originals[aid] = original
            stub = RecordingStubAdapter(
                adapter_id=aid,
                return_value=self._return_value,
                seq_counter=self._counter,
            )
            self._stubs[aid] = stub
            # Swap adapter in-place; preserve allowed_intents
            reg.adapter = stub    # type: ignore[assignment]

    def _restore(self) -> None:
        for aid, original in self._originals.items():
            reg = self._quarantine._registry.get(aid)
            if reg is not None:
                reg.adapter = original  # type: ignore[assignment]
        # Preserve _stubs so all_calls() / call_count() remain queryable after
        # the context exits.  Only drop the reference to the originals.
        self._originals.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _SharedCounter:
    """Monotonically increasing integer counter; thread-safe."""

    def __init__(self) -> None:
        self._n    = 0
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            self._n += 1
            return self._n
