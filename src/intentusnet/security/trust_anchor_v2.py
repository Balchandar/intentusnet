"""
Security Kernel v2.1 — Trust Anchor Manager

Attaches external verification proofs (confirmations) to WAL entry hashes.
Multiple ``ITrustAnchorAdapter`` implementations submit confirmations
independently; the manager collects them and determines the quorum status.

Design goals
------------
* Quorum-based assurance: a segment is FULLY_ANCHORED only when
  ``confirmations >= anchor_quorum_size``.
* Fault tolerance: individual adapter failures do not block execution.
  A segment with partial confirmations is PARTIALLY_ANCHORED, not FAILED.
* Non-blocking: ``submit_async()`` dispatches all adapters concurrently via
  threads; the caller is never blocked waiting for slow external systems.
* Auditability: every confirmation is stored in-memory (and optionally
  emitted as a SecurityEvent) so the quorum state can be re-evaluated at
  any time.

Anchor lifecycle
----------------
1. Caller calls ``anchor(execution_id, entry_hash)`` (or the batch form
   ``anchor_entries(execution_id, entries)`` for a list of WAL entries).
2. Manager dispatches all registered adapters concurrently.
3. Confirmations (or failures) are stored under
   ``(execution_id, entry_hash)``.
4. ``status(execution_id, entry_hash)`` queries current quorum state.

Thread safety
-------------
All public methods are thread-safe.  Adapter callbacks run on short-lived
worker threads; the confirmation store is protected by a lock.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .event_bus import SecurityEventBus, SecurityEventType


# ---------------------------------------------------------------------------
# Adapter protocol
# ---------------------------------------------------------------------------

class ITrustAnchorAdapter(ABC):
    """
    Abstract base for external trust anchor systems.

    Implementations should be IO-bound (remote attestation service, blockchain
    witness, HSM timestamp authority, etc.).  ``confirm()`` is called from a
    worker thread so blocking is acceptable — but should be bounded by a
    reasonable timeout.
    """

    @property
    @abstractmethod
    def anchor_id(self) -> str:
        """Stable unique identifier for this anchor."""
        ...

    @abstractmethod
    def confirm(
        self,
        execution_id: str,
        entry_hash:   str,
    ) -> "TrustAnchorConfirmation":
        """
        Submit ``entry_hash`` to the external anchor and return a
        ``TrustAnchorConfirmation``.

        May raise any exception; the manager catches all errors and records
        an ANCHOR_FAILED status instead.
        """
        ...


# ---------------------------------------------------------------------------
# Confirmation record
# ---------------------------------------------------------------------------

@dataclass
class TrustAnchorConfirmation:
    """
    One successful confirmation from a single anchor adapter.

    ``external_id`` is an opaque reference returned by the anchor service
    (e.g. a transaction hash or ticket ID).  May be empty when not applicable.
    """
    anchor_id:    str
    execution_id: str
    entry_hash:   str
    external_id:  str  = ""
    timestamp:    float = field(default_factory=time.time)
    metadata:     Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Anchor status
# ---------------------------------------------------------------------------

class AnchorStatus(str, Enum):
    PENDING            = "pending"             # no confirmations yet
    PARTIALLY_ANCHORED = "partially_anchored"  # some but below quorum
    FULLY_ANCHORED     = "fully_anchored"      # quorum reached
    FAILED             = "failed"              # all adapters failed


# ---------------------------------------------------------------------------
# Per-entry state
# ---------------------------------------------------------------------------

@dataclass
class _EntryAnchorState:
    confirmations: List[TrustAnchorConfirmation] = field(default_factory=list)
    failures:      List[Tuple[str, str]] = field(default_factory=list)  # (anchor_id, error)
    in_flight:     int = 0


# ---------------------------------------------------------------------------
# TrustAnchorManager
# ---------------------------------------------------------------------------

class TrustAnchorManager:
    """
    Collects external trust confirmations for WAL entry hashes.

    Parameters
    ----------
    quorum_size
        Minimum number of successful confirmations required for
        FULLY_ANCHORED status.  0 disables quorum enforcement (every entry
        is considered FULLY_ANCHORED once at least one confirmation arrives).
    event_bus
        Optional.  ``TRUST_ANCHOR_CONFIRMED`` events are emitted when quorum
        is reached; ``TRUST_ANCHOR_FAILED`` when all adapters fail.
    """

    def __init__(
        self,
        quorum_size: int = 1,
        *,
        event_bus:   Optional[SecurityEventBus] = None,
    ) -> None:
        self._quorum    = quorum_size
        self._event_bus = event_bus

        self._adapters: Dict[str, ITrustAnchorAdapter] = {}
        # key: (execution_id, entry_hash)
        self._store:  Dict[Tuple[str, str], _EntryAnchorState] = {}
        self._lock    = threading.Lock()

    # ------------------------------------------------------------------
    # Adapter management
    # ------------------------------------------------------------------

    def register(self, adapter: ITrustAnchorAdapter) -> None:
        """Register an anchor adapter.  Duplicate ``anchor_id`` raises ValueError."""
        with self._lock:
            if adapter.anchor_id in self._adapters:
                raise ValueError(
                    f"Anchor adapter '{adapter.anchor_id}' is already registered."
                )
            self._adapters[adapter.anchor_id] = adapter

    def unregister(self, anchor_id: str) -> None:
        with self._lock:
            self._adapters.pop(anchor_id, None)

    def registered_ids(self) -> List[str]:
        with self._lock:
            return sorted(self._adapters.keys())

    # ------------------------------------------------------------------
    # Anchoring
    # ------------------------------------------------------------------

    def anchor(
        self,
        execution_id: str,
        entry_hash:   str,
        *,
        timeout_seconds: float = 10.0,
    ) -> AnchorStatus:
        """
        Dispatch all registered adapters concurrently and wait up to
        ``timeout_seconds`` for results.

        Returns the ``AnchorStatus`` after all adapters complete or time out.
        """
        with self._lock:
            adapters = list(self._adapters.values())

        if not adapters:
            return AnchorStatus.PENDING

        key = (execution_id, entry_hash)
        with self._lock:
            state = self._store.setdefault(key, _EntryAnchorState())
            state.in_flight += len(adapters)

        threads = []
        for adapter in adapters:
            t = threading.Thread(
                target=self._run_adapter,
                args=(adapter, execution_id, entry_hash),
                daemon=True,
            )
            threads.append(t)
            t.start()

        deadline = time.time() + timeout_seconds
        for t in threads:
            remaining = deadline - time.time()
            t.join(timeout=max(0.0, remaining))

        return self.status(execution_id, entry_hash)

    def anchor_entries(
        self,
        execution_id: str,
        entry_hashes: List[str],
        *,
        timeout_seconds: float = 10.0,
    ) -> Dict[str, AnchorStatus]:
        """
        Anchor a batch of WAL entry hashes.  Returns a mapping of
        ``entry_hash → AnchorStatus``.
        """
        return {
            h: self.anchor(execution_id, h, timeout_seconds=timeout_seconds)
            for h in entry_hashes
        }

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def status(self, execution_id: str, entry_hash: str) -> AnchorStatus:
        """Current quorum status for a (execution_id, entry_hash) pair."""
        key = (execution_id, entry_hash)
        with self._lock:
            state = self._store.get(key)

        if state is None:
            return AnchorStatus.PENDING

        n_confirmed = len(state.confirmations)
        n_failed    = len(state.failures)
        n_adapters  = len(self._adapters)

        if n_confirmed == 0 and n_failed == 0:
            return AnchorStatus.PENDING

        effective_quorum = self._quorum if self._quorum > 0 else 1
        if n_confirmed >= effective_quorum:
            return AnchorStatus.FULLY_ANCHORED

        # All dispatched adapters have responded (confirmed + failed = total)
        # and quorum not reached → FAILED only if none confirmed
        if n_confirmed == 0 and (n_confirmed + n_failed) >= n_adapters > 0:
            return AnchorStatus.FAILED

        if n_confirmed > 0:
            return AnchorStatus.PARTIALLY_ANCHORED

        return AnchorStatus.PENDING

    def confirmations(
        self,
        execution_id: str,
        entry_hash:   str,
    ) -> List[TrustAnchorConfirmation]:
        """Return recorded confirmations for one entry hash."""
        key = (execution_id, entry_hash)
        with self._lock:
            state = self._store.get(key)
            return list(state.confirmations) if state else []

    def failures(
        self,
        execution_id: str,
        entry_hash:   str,
    ) -> List[Tuple[str, str]]:
        """Return (anchor_id, error_message) pairs for failed adapters."""
        key = (execution_id, entry_hash)
        with self._lock:
            state = self._store.get(key)
            return list(state.failures) if state else []

    def is_fully_anchored(self, execution_id: str, entry_hash: str) -> bool:
        return self.status(execution_id, entry_hash) == AnchorStatus.FULLY_ANCHORED

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        config:    Any,   # SecurityConfig; typed as Any to avoid circular import
        *,
        event_bus: Optional[SecurityEventBus] = None,
    ) -> "TrustAnchorManager":
        """Build from a ``SecurityConfig`` instance."""
        return cls(
            quorum_size=config.anchor_quorum_size,
            event_bus=event_bus,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_adapter(
        self,
        adapter:      ITrustAnchorAdapter,
        execution_id: str,
        entry_hash:   str,
    ) -> None:
        key = (execution_id, entry_hash)
        try:
            confirmation = adapter.confirm(execution_id, entry_hash)
            with self._lock:
                state = self._store.setdefault(key, _EntryAnchorState())
                state.confirmations.append(confirmation)
                state.in_flight = max(0, state.in_flight - 1)
                n_confirmed = len(state.confirmations)
                effective_quorum = self._quorum if self._quorum > 0 else 1
                quorum_reached = n_confirmed >= effective_quorum

            if quorum_reached and self._event_bus is not None:
                self._event_bus.emit(
                    SecurityEventType.TRUST_ANCHOR_CONFIRMED,
                    execution_id,
                    payload={
                        "entry_hash":   entry_hash,
                        "anchor_id":    adapter.anchor_id,
                        "n_confirmed":  n_confirmed,
                        "quorum":       self._quorum,
                    },
                )

        except Exception as exc:
            with self._lock:
                state = self._store.setdefault(key, _EntryAnchorState())
                state.failures.append((adapter.anchor_id, str(exc)))
                state.in_flight = max(0, state.in_flight - 1)
                n_confirmed = len(state.confirmations)
                n_failed    = len(state.failures)
                n_adapters  = len(self._adapters)
                all_failed  = (n_confirmed == 0
                               and (n_confirmed + n_failed) >= n_adapters > 0)

            if all_failed and self._event_bus is not None:
                self._event_bus.emit(
                    SecurityEventType.TRUST_ANCHOR_FAILED,
                    execution_id,
                    payload={
                        "entry_hash": entry_hash,
                        "anchor_id":  adapter.anchor_id,
                        "error":      str(exc),
                    },
                )
