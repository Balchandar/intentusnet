"""
Forensic Audit System

Produces tamper-evident structured audit records linked to WAL hashes.

Compliance targets:
  - HIPAA § 164.312(b): audit controls — hardware, software, procedural
  - GDPR Art. 30: records of processing activities
  - NIST AI RMF GOVERN-1.4 / MANAGE-2.4: AI system audit trails

Each ForensicAuditEntry:
  - Is self-hashing (SHA-256 over its own fields)
  - Links to the WAL via wal_entry_hash (cross-system tamper evidence)
  - Is chained to the previous entry (append-only integrity)

ForensicAuditLog:
  - Thread-safe in-memory log
  - Exportable as list[dict] for compliance reporting
  - Supports per-intent and per-execution queries
  - chain_ok() verifies the full log is intact
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_dict(data: Dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class ForensicAuditEntry:
    """
    Tamper-evident forensic audit record.

    Fields follow the schema specified in IntentusNet Security Kernel design:
      intent_id, actor_id, input_hash, state_before, state_after,
      validation_result, anomaly_score, decision, wal_entry_hash, timestamp

    Additional fields for operational enrichment:
      intent_name, capability_violations, anomaly_reasons, execution_id

    entry_hash:
      SHA-256 of all core fields. Computed on construction; re-verifiable
      via verify_integrity().

    prev_entry_hash:
      Set by ForensicAuditLog when chaining entries together. None on the
      first entry.
    """

    # Core schema fields
    intent_id: str
    actor_id: str
    input_hash: str
    state_before: str
    state_after: str
    validation_result: str          # "allowed" | "blocked" | "audit_only" | "error"
    anomaly_score: float            # 0.0 – 1.0
    decision: str                   # "execute" | "block" | "quarantine" | "replay" | "error"
    wal_entry_hash: Optional[str]   # Links this audit entry to a WAL entry hash
    timestamp: str

    # Enrichment
    intent_name: str = ""
    capability_violations: List[str] = field(default_factory=list)
    anomaly_reasons: List[str] = field(default_factory=list)
    execution_id: str = ""

    # Self-integrity (set post-init; overwritten by chain on record())
    entry_hash: str = field(init=False, default="")
    prev_entry_hash: Optional[str] = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.entry_hash = self._compute_hash()

    def _core_fields(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "actor_id": self.actor_id,
            "input_hash": self.input_hash,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "validation_result": self.validation_result,
            "anomaly_score": self.anomaly_score,
            "decision": self.decision,
            "wal_entry_hash": self.wal_entry_hash,
            "timestamp": self.timestamp,
        }

    def _compute_hash(self) -> str:
        return _sha256_dict(self._core_fields())

    def verify_integrity(self) -> bool:
        """True if the entry's core fields match its stored entry_hash."""
        return self.entry_hash == self._compute_hash()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "actor_id": self.actor_id,
            "input_hash": self.input_hash,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "validation_result": self.validation_result,
            "anomaly_score": self.anomaly_score,
            "decision": self.decision,
            "wal_entry_hash": self.wal_entry_hash,
            "timestamp": self.timestamp,
            "intent_name": self.intent_name,
            "capability_violations": self.capability_violations,
            "anomaly_reasons": self.anomaly_reasons,
            "execution_id": self.execution_id,
            "entry_hash": self.entry_hash,
            "prev_entry_hash": self.prev_entry_hash,
        }


class ForensicAuditLog:
    """
    Thread-safe, append-only, hash-chained forensic audit log.

    Each entry is linked to the previous via prev_entry_hash, forming a
    chain that detects post-hoc insertion, deletion, or reordering.

    The log is in-memory. Persistence can be added by wrapping record()
    to also write to a JSONL file (same pattern as WALWriter).
    """

    def __init__(self) -> None:
        self._entries: List[ForensicAuditEntry] = []
        self._last_hash: Optional[str] = None
        self._lock = threading.Lock()

    def record(self, entry: ForensicAuditEntry) -> None:
        """
        Append an entry to the log.

        Chains the entry to the previous entry's hash.
        The entry's entry_hash is recomputed to incorporate the chain link.
        """
        with self._lock:
            entry.prev_entry_hash = self._last_hash

            # Incorporate chain link into the entry's own hash
            chain_data = entry._core_fields()
            chain_data["prev_entry_hash"] = self._last_hash
            entry.entry_hash = _sha256_dict(chain_data)

            self._entries.append(entry)
            self._last_hash = entry.entry_hash

    def chain_ok(self) -> bool:
        """
        Verify the complete audit chain is intact.

        Returns False if any entry has been tampered with or reordered.
        """
        with self._lock:
            prev_hash: Optional[str] = None
            for entry in self._entries:
                chain_data = entry._core_fields()
                chain_data["prev_entry_hash"] = prev_hash
                expected = _sha256_dict(chain_data)
                if entry.entry_hash != expected:
                    return False
                prev_hash = entry.entry_hash
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_by_intent(self, intent_id: str) -> List[ForensicAuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.intent_id == intent_id]

    def get_by_execution(self, execution_id: str) -> List[ForensicAuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.execution_id == execution_id]

    def get_anomalies(self, min_score: float = 0.75) -> List[ForensicAuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.anomaly_score >= min_score]

    def get_blocked(self) -> List[ForensicAuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.decision == "block"]

    # ------------------------------------------------------------------
    # Export (compliance)
    # ------------------------------------------------------------------

    def export(self) -> List[Dict[str, Any]]:
        """Export full log as JSON-serializable list for compliance reporting."""
        with self._lock:
            return [e.to_dict() for e in self._entries]

    def export_jsonl(self) -> str:
        """Export as JSONL string (one JSON object per line)."""
        rows = self.export()
        return "\n".join(json.dumps(r, separators=(",", ":")) for r in rows)

    def last_hash(self) -> Optional[str]:
        with self._lock:
            return self._last_hash

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
