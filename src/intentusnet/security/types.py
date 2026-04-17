"""
Security Kernel v2.1 — Shared Type Definitions

All types defined here are pure data; they import nothing from the rest of
the security package, making them safe to import from any phase.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Execution Isolation Mode
# ---------------------------------------------------------------------------

class ExecutionIsolationMode(str, Enum):
    """How strictly agent execution is isolated from the host process."""
    INPROCESS = "inprocess"       # no isolation; advisory resource limits only
    SUBPROCESS = "subprocess"     # pre-forked worker, SIGKILL after one use
    CONTAINER = "container"       # OCI container (future; not yet implemented)


# ---------------------------------------------------------------------------
# Replay Mode
# ---------------------------------------------------------------------------

class ReplayMode(str, Enum):
    """Behaviour of the deterministic replay engine."""
    SHADOW = "shadow"         # re-execute silently; compare result vs recorded
    AUDIT = "audit"           # re-execute; write comparison to ForensicAuditLog
    ENFORCE = "enforce"       # block if replay result diverges from recorded


# ---------------------------------------------------------------------------
# Degradation / Backpressure State Machine
# ---------------------------------------------------------------------------

class DegradationState(str, Enum):
    """
    Four-tier backpressure ladder.

    Transitions (forward): NORMAL → OBSERVATION_DROP → AUDIT_ONLY → FAIL_SAFE
    Transitions (recovery): each tier recovers to the tier immediately above
    when pressure metrics fall below the corresponding recovery threshold for
    at least ``hysteresis_seconds`` seconds.
    """
    NORMAL = "normal"
    OBSERVATION_DROP = "observation_drop"   # non-critical events dropped
    AUDIT_ONLY = "audit_only"               # enforcement suspended; audit preserved
    FAIL_SAFE = "fail_safe"                 # all new requests rejected


# ---------------------------------------------------------------------------
# Resource Limits
# ---------------------------------------------------------------------------

@dataclass
class ResourceLimits:
    """
    Hard resource ceilings applied to isolated execution workers.

    In INPROCESS mode these are advisory (logged on breach; not enforced by the
    OS).  In SUBPROCESS mode they are enforced via ``resource.setrlimit()``
    inside the worker process before execution begins.

    All memory values are in bytes.  0 means "no limit".
    """
    max_cpu_seconds: float = 0.0        # RLIMIT_CPU (0 = unlimited)
    max_memory_bytes: int = 0           # RLIMIT_AS  (0 = unlimited)
    max_open_files: int = 0             # RLIMIT_NOFILE (0 = unlimited)
    max_processes: int = 0              # RLIMIT_NPROC  (0 = unlimited)
    max_wall_seconds: float = 0.0       # watchdog SIGKILL deadline (0 = unlimited)

    def any_limit_set(self) -> bool:
        return any([
            self.max_cpu_seconds > 0,
            self.max_memory_bytes > 0,
            self.max_open_files > 0,
            self.max_processes > 0,
            self.max_wall_seconds > 0,
        ])


# ---------------------------------------------------------------------------
# Policy Version
# ---------------------------------------------------------------------------

@dataclass
class PolicyVersion:
    """
    Immutable identity + hash of a policy snapshot.

    Attached to every WAL entry, ForensicAuditEntry, and SecurityEvent so
    that the policy state at decision time is auditable post-hoc.

    ``policy_hash`` is SHA-256 of the canonical JSON serialization of the
    policy rules list.  It is computed by the policy loader, not here.
    """
    policy_id: str
    version: int
    policy_hash: str            # hex SHA-256 of canonical rule set
    loaded_at: float = field(default_factory=time.time)

    # Sentinel used before any real policy is loaded.
    @classmethod
    def unknown(cls) -> PolicyVersion:
        return cls(
            policy_id="__unknown__",
            version=0,
            policy_hash="0" * 64,
        )

    def short_hash(self) -> str:
        """First 12 hex chars — useful for log lines."""
        return self.policy_hash[:12]

    @staticmethod
    def hash_rules(rules_json: str) -> str:
        """Canonical SHA-256 of the serialised rules string."""
        return hashlib.sha256(rules_json.encode()).hexdigest()
