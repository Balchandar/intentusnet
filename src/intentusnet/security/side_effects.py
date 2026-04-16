"""
Side-Effect Quarantine System

Enforces that all external calls from agent execution go through registered,
declared adapters — never ad-hoc HTTP calls, DB connections, or system calls.

Architecture:
  ISideEffectAdapter (ABC)
    Implementors register with SideEffectQuarantine at startup.
    Each adapter_id must map to a side_effect_signature entry in CapabilityMetadata.

  SideEffectQuarantine
    Central enforcement registry.
    Blocks any call whose adapter_id is not declared in the capability's
    side_effect_signature when strict_mode is enabled.
    In permissive mode (strict_mode=False): logs warnings, does not block.

Usage:
    quarantine = SideEffectQuarantine(strict_mode=True)
    quarantine.register(EmailAdapter(), allowed_intents=["SendNotification"])

    # Inside agent — instead of directly calling SMTP:
    quarantine.execute(
        adapter_id="email",
        intent_name="SendNotification",
        declared_signatures=capability.metadata.side_effect_signature,
        payload={"to": "...", "subject": "..."},
    )
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set

logger = logging.getLogger("intentusnet.security.side_effects")


class SideEffectNotAuthorizedError(RuntimeError):
    """
    Raised when a side-effect call is not authorized.

    Conditions:
    - adapter_id not in capability's side_effect_signature (strict mode)
    - adapter not registered in quarantine (strict mode)
    - intent not in adapter's allowed_intents (strict mode)
    """


class ISideEffectAdapter(ABC):
    """
    Base class for all external side-effect adapters.

    Rules:
    - adapter_id MUST be unique and stable across restarts.
    - adapter_id MUST appear in CapabilityMetadata.side_effect_signature
      for any intent that invokes it (in strict mode).
    - No dynamic endpoints — all destinations must be fixed at registration.
    - execute() MUST be idempotent where the intent's retry_pattern allows it.
    """

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier matching side_effect_signature entries."""
        ...

    @abstractmethod
    def execute(self, payload: Dict[str, Any]) -> Any:
        """Execute the side-effect. Called only after quarantine authorization."""
        ...


@dataclass
class _AdapterRegistration:
    adapter: ISideEffectAdapter
    allowed_intents: FrozenSet[str]   # empty = all intents allowed


class SideEffectQuarantine:
    """
    Registry and enforcement gateway for side-effect adapters.

    strict_mode=True:  Blocks any undeclared or unregistered side-effect.
    strict_mode=False: Logs warnings only (default for backward compatibility).
    """

    def __init__(self, strict_mode: bool = False) -> None:
        self._strict = strict_mode
        self._registry: Dict[str, _AdapterRegistration] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration (startup time)
    # ------------------------------------------------------------------

    def register(
        self,
        adapter: ISideEffectAdapter,
        allowed_intents: Optional[List[str]] = None,
    ) -> None:
        """
        Register a side-effect adapter.

        Args:
            adapter:          ISideEffectAdapter implementation.
            allowed_intents:  If provided, only these intent names may call
                              this adapter. Empty / None = any intent allowed.
        """
        with self._lock:
            aid = adapter.adapter_id
            if aid in self._registry:
                raise ValueError(f"Side-effect adapter '{aid}' is already registered.")
            self._registry[aid] = _AdapterRegistration(
                adapter=adapter,
                allowed_intents=frozenset(allowed_intents or []),
            )
        logger.debug("SideEffectQuarantine: registered adapter '%s'", adapter.adapter_id)

    def unregister(self, adapter_id: str) -> None:
        with self._lock:
            self._registry.pop(adapter_id, None)

    # ------------------------------------------------------------------
    # Execution (runtime — called by agents)
    # ------------------------------------------------------------------

    def execute(
        self,
        adapter_id: str,
        intent_name: str,
        declared_signatures: List[str],
        payload: Dict[str, Any],
    ) -> Any:
        """
        Execute a side-effect after authorization check.

        Authorization chain (all must pass in strict mode):
        1. adapter_id ∈ declared_signatures (capability contract).
        2. adapter_id ∈ registered adapters.
        3. intent_name ∈ adapter.allowed_intents (if restricted).

        Args:
            adapter_id:           Must match a registered adapter ID.
            intent_name:          Currently executing intent.
            declared_signatures:  CapabilityMetadata.side_effect_signature.
            payload:              Forwarded to adapter.execute().

        Returns:
            Whatever the adapter returns.

        Raises:
            SideEffectNotAuthorizedError: In strict mode when any check fails.
        """
        # --- Check 1: declared in capability metadata ---
        if adapter_id not in declared_signatures:
            msg = (
                f"Side-effect '{adapter_id}' is not declared in the capability's "
                f"side_effect_signature for intent '{intent_name}'. "
                f"Declared: {declared_signatures}"
            )
            if self._strict:
                raise SideEffectNotAuthorizedError(msg)
            logger.warning("SideEffectQuarantine [permissive]: %s", msg)

        with self._lock:
            registration = self._registry.get(adapter_id)

        # --- Check 2: adapter registered ---
        if registration is None:
            msg = (
                f"Side-effect adapter '{adapter_id}' is not registered. "
                "All external calls must go through registered adapters."
            )
            if self._strict:
                raise SideEffectNotAuthorizedError(msg)
            logger.warning("SideEffectQuarantine [permissive]: %s", msg)
            return None

        # --- Check 3: intent authorization ---
        if registration.allowed_intents and intent_name not in registration.allowed_intents:
            msg = (
                f"Intent '{intent_name}' is not authorized to use adapter '{adapter_id}'. "
                f"Allowed intents: {sorted(registration.allowed_intents)}"
            )
            if self._strict:
                raise SideEffectNotAuthorizedError(msg)
            logger.warning("SideEffectQuarantine [permissive]: %s", msg)

        logger.debug(
            "SideEffectQuarantine: AUTHORIZED adapter='%s' intent='%s'",
            adapter_id, intent_name,
        )
        return registration.adapter.execute(payload)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def registered_ids(self) -> List[str]:
        with self._lock:
            return sorted(self._registry.keys())

    def is_registered(self, adapter_id: str) -> bool:
        with self._lock:
            return adapter_id in self._registry

    def __len__(self) -> int:
        with self._lock:
            return len(self._registry)
