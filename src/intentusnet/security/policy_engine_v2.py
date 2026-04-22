"""
Security Kernel v2.1 — Policy Engine v2

Thin wrapper over v1's ``PolicyEngine`` that attaches a ``PolicyVersion`` to
every decision and supports safe hot-reload from a file on disk.

Design notes
------------
* v2 decisions are a superset of v1 decisions.  ``PolicyDecisionV2`` embeds the
  original ``PolicyDecision`` verbatim plus the ``policy_version`` in effect at
  evaluation time.  Existing v1 consumers can ignore the wrapper and read the
  inner decision directly.
* Hot reload is opt-in.  ``reload()`` re-reads the source file only when its
  mtime has advanced; failures are swallowed and the previous policy is kept
  (no policy is STRICTLY better than a half-parsed one, but falling back to
  the last-known-good policy is safer still).
* ``event_bus`` is optional.  When set, ``POLICY_VIOLATION`` events are emitted
  on each DENY decision.  The payload contains the rule id and the intent name
  so downstream consumers can count violations per rule.

Thread safety
-------------
All public methods are thread-safe.  The engine instance is swapped atomically
under a single lock during ``reload()``; readers always see a consistent view.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .event_bus import SecurityEventBus, SecurityEventType
from .policy_engine import (
    EvaluationContext,
    PolicyAction,
    PolicyDecision,
    PolicyEngine,
)
from .types import PolicyVersion


# ---------------------------------------------------------------------------
# PolicyDecisionV2
# ---------------------------------------------------------------------------

@dataclass
class PolicyDecisionV2:
    """
    Envelope around a v1 ``PolicyDecision`` adding the policy version under
    which the decision was made.

    The ``decision_id`` is opaque but unique per evaluation; consumers may use
    it to correlate WAL entries with audit entries.
    """
    decision:       PolicyDecision
    policy_version: PolicyVersion
    decided_at:     float = field(default_factory=time.time)

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    @property
    def reason(self) -> str:
        return self.decision.reason

    def to_dict(self) -> Dict[str, Any]:
        matched = self.decision.matched_rule
        return {
            "allowed":     self.decision.allowed,
            "reason":      self.decision.reason,
            "rule_id":     matched.id if matched else None,
            "policy_id":   self.policy_version.policy_id,
            "policy_hash": self.policy_version.policy_hash,
            "policy_version": self.policy_version.version,
            "decided_at":  self.decided_at,
        }


# ---------------------------------------------------------------------------
# PolicyEngineV2
# ---------------------------------------------------------------------------

class PolicyEngineV2:
    """
    Versioned, hot-reloadable policy engine.

    Usage — in-memory rules::

        engine = PolicyEngineV2.from_dict(
            {"default": "allow", "rules": [...]},
            policy_id="prod",
        )
        decision = engine.evaluate(ctx)

    Usage — file-backed::

        engine = PolicyEngineV2.from_file("/etc/intentusnet/policy.json",
                                          policy_id="prod")
        # later, in a ticker:
        engine.reload()     # re-reads file only if mtime advanced
    """

    def __init__(
        self,
        engine:         PolicyEngine,
        policy_version: PolicyVersion,
        *,
        source_path:    Optional[str] = None,
        source_mtime:   Optional[float] = None,
        event_bus:      Optional[SecurityEventBus] = None,
    ) -> None:
        self._engine         = engine
        self._policy_version = policy_version
        self._source_path    = source_path
        self._source_mtime   = source_mtime
        self._event_bus      = event_bus
        self._lock           = threading.Lock()

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(
        cls,
        data:      Dict[str, Any],
        *,
        policy_id: str = "default",
        version:   int = 1,
        event_bus: Optional[SecurityEventBus] = None,
    ) -> "PolicyEngineV2":
        """Build an engine from an in-memory policy dictionary."""
        engine = PolicyEngine.from_dict(data)
        pv = PolicyVersion(
            policy_id=policy_id,
            version=version,
            policy_hash=_hash_policy(data),
        )
        return cls(engine, pv, event_bus=event_bus)

    @classmethod
    def from_file(
        cls,
        path:      str,
        *,
        policy_id: Optional[str] = None,
        event_bus: Optional[SecurityEventBus] = None,
    ) -> "PolicyEngineV2":
        """
        Load a JSON policy file and build an engine.

        The ``policy_id`` defaults to the file's basename without extension so
        multiple policies loaded from different files are distinguishable in
        audit output.
        """
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(raw)
        mtime = os.path.getmtime(path)
        if policy_id is None:
            policy_id = os.path.splitext(os.path.basename(path))[0]

        engine = PolicyEngine.from_dict(data)
        pv = PolicyVersion(
            policy_id=policy_id,
            version=1,
            policy_hash=_hash_policy(data),
        )
        return cls(
            engine, pv,
            source_path=path,
            source_mtime=mtime,
            event_bus=event_bus,
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, ctx: EvaluationContext) -> PolicyDecisionV2:
        """Evaluate ``ctx`` against the current policy."""
        with self._lock:
            engine = self._engine
            pv     = self._policy_version

        raw = engine.evaluate(ctx)
        decision = PolicyDecisionV2(decision=raw, policy_version=pv)

        if not raw.allowed and self._event_bus is not None:
            rule_id = raw.matched_rule.id if raw.matched_rule else None
            self._event_bus.emit(
                SecurityEventType.POLICY_VIOLATION,
                ctx.intent,
                payload={
                    "rule_id":    rule_id,
                    "reason":     raw.reason,
                    "subject":    ctx.subject,
                    "tenant":     ctx.tenant,
                    "agent":      ctx.agent,
                    "policy_id":  pv.policy_id,
                    "policy_hash": pv.policy_hash,
                },
            )

        return decision

    # ------------------------------------------------------------------
    # Observability / introspection
    # ------------------------------------------------------------------

    @property
    def policy_version(self) -> PolicyVersion:
        with self._lock:
            return self._policy_version

    @property
    def source_path(self) -> Optional[str]:
        return self._source_path

    # ------------------------------------------------------------------
    # Hot reload
    # ------------------------------------------------------------------

    def reload(self) -> bool:
        """
        Reload the policy from ``source_path`` if its mtime has advanced.

        Returns True if the policy was reloaded (with a new version number),
        False if unchanged or if no source file was configured.  Parse errors
        are swallowed and the current policy is preserved.
        """
        if self._source_path is None:
            return False
        try:
            mtime = os.path.getmtime(self._source_path)
        except OSError:
            return False

        with self._lock:
            if self._source_mtime is not None and mtime <= self._source_mtime:
                return False

        try:
            with open(self._source_path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = json.loads(raw)
            new_engine = PolicyEngine.from_dict(data)
            new_hash = _hash_policy(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return False

        with self._lock:
            # If content is semantically identical, bump mtime only (no reload).
            if new_hash == self._policy_version.policy_hash:
                self._source_mtime = mtime
                return False

            next_version = self._policy_version.version + 1
            self._engine = new_engine
            self._policy_version = PolicyVersion(
                policy_id=self._policy_version.policy_id,
                version=next_version,
                policy_hash=new_hash,
            )
            self._source_mtime = mtime
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_policy(data: Dict[str, Any]) -> str:
    """Stable SHA-256 of the canonical JSON serialisation of a policy dict."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "PolicyAction",
    "PolicyDecision",
    "PolicyDecisionV2",
    "PolicyEngineV2",
]
