"""
IntentusNet v1.4.1 Deterministic Agent - WAL Entry Models (HARDENED)

This module defines the Write-Ahead Log (WAL) entry schema for deterministic
execution tracking. All execution steps are recorded with full metadata to
enable:
- Exact replay verification
- Deterministic recovery from failures
- Execution fingerprint computation
- Timeout/latency determinism tracking

CRITICAL: These models are the source of truth for execution state.

HARDENING v1.4.1.1:
- Removed UUID randomness from step_id (now deterministic)
- Separated volatile fields from fingerprint computation
- Added stable hash computation that excludes timestamps
- Added cross-environment determinism guarantees
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class SideEffectClass(str, Enum):
    """
    Classification of tool side effects for deterministic safety.

    - READ_ONLY: No state changes, safe to retry/replay
    - STATE_CHANGING: Modifies state, requires idempotency key
    - EXTERNAL: External service call, requires MCP adapter
    """
    READ_ONLY = "read_only"
    STATE_CHANGING = "state_changing"
    EXTERNAL = "external"


class RetryReason(str, Enum):
    """
    Reason for execution retry - recorded for deterministic replay.

    Each retry reason affects the execution fingerprint differently.
    """
    NONE = "none"
    TIMEOUT = "timeout"
    MALFORMED_OUTPUT = "malformed_output"
    RUNTIME_ERROR = "runtime_error"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"


def _generate_deterministic_id(
    execution_id: str,
    execution_order: int,
    intent: str = "",
    tool_name: str = "",
) -> str:
    """
    Generate deterministic step ID based on execution context.

    CRITICAL: This replaces UUID4 to ensure cross-execution reproducibility.
    The step_id is now derived from:
    - execution_id (provided by caller)
    - execution_order (sequential number)
    - intent name
    - tool name

    This ensures the same logical step produces the same step_id
    across different runs.
    """
    data = {
        "execution_id": execution_id,
        "execution_order": execution_order,
        "intent": intent,
        "tool_name": tool_name,
    }
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
    hash_value = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"step_{hash_value[:24]}"


@dataclass
class LatencyMetadata:
    """
    Latency metadata for v1.4.1 deterministic execution.

    CRITICAL: Timeouts are hashed into the execution fingerprint in v1.4.1.
    This ensures that timeout behavior is deterministically tracked and
    replay-verifiable.

    HARDENING: Only deterministic fields (timeout_ms, did_timeout, retry_triggered)
    are included in fingerprint computation. Volatile fields (start_time, end_time,
    duration_ms) are stored for debugging but excluded from hashes.

    Attributes:
        start_time: Unix timestamp when execution started (ms) [VOLATILE - not hashed]
        end_time: Unix timestamp when execution ended (ms) [VOLATILE - not hashed]
        duration_ms: Actual execution duration in milliseconds [VOLATILE - not hashed]
        timeout_ms: Configured timeout threshold [DETERMINISTIC - hashed]
        did_timeout: Whether the execution timed out [DETERMINISTIC - hashed]
        retry_triggered: Whether a retry was triggered [DETERMINISTIC - hashed]
    """
    start_time: int = 0
    end_time: int = 0
    duration_ms: int = 0
    timeout_ms: int = 0
    did_timeout: bool = False
    retry_triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_deterministic_dict(self) -> dict[str, Any]:
        """
        Return only deterministic fields for fingerprint computation.

        CRITICAL: Excludes start_time, end_time, duration_ms which are
        time-dependent and break cross-execution determinism.
        """
        return {
            "timeout_ms": self.timeout_ms,
            "did_timeout": self.did_timeout,
            "retry_triggered": self.retry_triggered,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LatencyMetadata:
        return cls(**data)

    def compute_hash(self) -> str:
        """
        Compute deterministic hash of latency metadata.

        HARDENED: Only includes deterministic fields.
        """
        data = self.to_deterministic_dict()
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass
class WALEntry:
    """
    Complete WAL entry schema for IntentusNet v1.4.1.

    This schema captures all information needed for:
    - Deterministic replay verification
    - Exact-once side-effect safety
    - Execution fingerprint computation
    - Recovery from failures

    CRITICAL FIELDS:
    - step_id: Unique identifier for this execution step
    - idempotency_key: Prevents duplicate side-effects on replay
    - commit: Only True after successful execution
    - latency_metadata: Required for v1.4.1 timeout determinism

    HARDENING v1.4.1.1:
    - step_id is now deterministic (not UUID)
    - compute_hash() excludes volatile fields
    - compute_deterministic_hash() for fingerprint computation
    """
    # Core identification
    step_id: str = ""  # CHANGED: No longer UUID, set explicitly
    execution_id: str = ""
    intent: str = ""

    # Tool execution details
    tool_name: str = ""
    execution_order: int = 0

    # Parameter tracking for deterministic replay
    params_hash: str = ""
    params_snapshot: dict[str, Any] = field(default_factory=dict)

    # Output tracking for verification
    output_hash: str = ""
    output_snapshot: Any = None

    # Side-effect classification for safety
    side_effect_class: SideEffectClass = SideEffectClass.READ_ONLY

    # Retry tracking for deterministic recovery
    retry_count: int = 0
    retry_reason: RetryReason = RetryReason.NONE

    # Idempotency for exact-once guarantee
    idempotency_key: str = ""

    # Commit flag - CRITICAL for exact-once safety
    # Only True AFTER successful execution
    commit: bool = False

    # Timestamp for ordering [VOLATILE - excluded from deterministic hash]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # v1.4.1 REQUIRED: Latency metadata for timeout determinism
    latency_metadata: LatencyMetadata = field(default_factory=LatencyMetadata)

    # Hash chain for integrity
    prev_hash: Optional[str] = None
    entry_hash: str = ""

    def __post_init__(self):
        """Generate deterministic step_id if not provided."""
        if not self.step_id and self.execution_id:
            self.step_id = _generate_deterministic_id(
                self.execution_id,
                self.execution_order,
                self.intent,
                self.tool_name,
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["side_effect_class"] = self.side_effect_class.value
        data["retry_reason"] = self.retry_reason.value
        data["latency_metadata"] = self.latency_metadata.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WALEntry:
        """Create from dictionary."""
        data = data.copy()
        data["side_effect_class"] = SideEffectClass(data.get("side_effect_class", "read_only"))
        data["retry_reason"] = RetryReason(data.get("retry_reason", "none"))
        if isinstance(data.get("latency_metadata"), dict):
            data["latency_metadata"] = LatencyMetadata.from_dict(data["latency_metadata"])
        return cls(**data)

    def compute_deterministic_hash(self) -> str:
        """
        Compute deterministic hash for fingerprint computation.

        CRITICAL: This hash is STABLE across:
        - Different execution times
        - Different machines
        - Process restarts

        EXCLUDES volatile fields:
        - timestamp (wall-clock time)
        - latency_metadata.start_time/end_time/duration_ms
        - prev_hash (chain position)
        """
        data = {
            "step_id": self.step_id,
            "execution_id": self.execution_id,
            "intent": self.intent,
            "tool_name": self.tool_name,
            "execution_order": self.execution_order,
            "params_hash": self.params_hash,
            "output_hash": self.output_hash,
            "side_effect_class": self.side_effect_class.value,
            "retry_count": self.retry_count,
            "retry_reason": self.retry_reason.value,
            "idempotency_key": self.idempotency_key,
            "commit": self.commit,
            # DETERMINISTIC latency fields only
            "timeout_ms": self.latency_metadata.timeout_ms,
            "did_timeout": self.latency_metadata.did_timeout,
            "retry_triggered": self.latency_metadata.retry_triggered,
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def compute_hash(self) -> str:
        """
        Compute SHA-256 hash of this entry for WAL integrity verification.

        NOTE: This hash includes ALL fields for integrity checking.
        For fingerprint computation, use compute_deterministic_hash().
        """
        data = {
            "step_id": self.step_id,
            "execution_id": self.execution_id,
            "intent": self.intent,
            "tool_name": self.tool_name,
            "execution_order": self.execution_order,
            "params_hash": self.params_hash,
            "output_hash": self.output_hash,
            "side_effect_class": self.side_effect_class.value,
            "retry_count": self.retry_count,
            "retry_reason": self.retry_reason.value,
            "idempotency_key": self.idempotency_key,
            "commit": self.commit,
            "timestamp": self.timestamp,
            "latency_metadata": self.latency_metadata.to_dict(),
            "prev_hash": self.prev_hash,
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def generate_idempotency_key(self) -> str:
        """
        Generate deterministic idempotency key for this step.

        The key is based on:
        - Execution ID (scope)
        - Intent name
        - Tool name
        - Parameter hash
        - Execution order

        This ensures that re-executing the same logical operation
        will be detected and prevented.
        """
        data = {
            "execution_id": self.execution_id,
            "intent": self.intent,
            "tool_name": self.tool_name,
            "params_hash": self.params_hash,
            "execution_order": self.execution_order,
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return f"idem_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]}"


@dataclass
class ExecutionFingerprint:
    """
    Deterministic execution fingerprint for IntentusNet v1.4.1.

    The fingerprint uniquely identifies an execution path and is used
    to verify replay equivalence. Any change in the execution path
    will result in a different fingerprint.

    CRITICAL: The fingerprint includes timeout values and trigger flags
    because timeouts are hashed into the execution fingerprint in v1.4.1.

    HARDENING v1.4.1.1:
    - Fingerprint is now STABLE across process restarts
    - Only deterministic fields included
    - Excludes actual latency durations (time-dependent)
    """
    execution_id: str = ""

    # Sequences for fingerprint computation
    intent_sequence: list[str] = field(default_factory=list)
    tool_sequence: list[str] = field(default_factory=list)
    param_hashes: list[str] = field(default_factory=list)
    output_hashes: list[str] = field(default_factory=list)
    retry_pattern: list[tuple[int, str]] = field(default_factory=list)  # (retry_count, reason)
    execution_order: list[int] = field(default_factory=list)

    # v1.4.1 REQUIRED: Timeout determinism
    timeout_values: list[int] = field(default_factory=list)
    timeout_trigger_flags: list[bool] = field(default_factory=list)

    # Final fingerprint
    fingerprint: str = ""

    def compute(self) -> str:
        """
        Compute the execution fingerprint.

        SHA256(
            intent_sequence +
            tool_sequence +
            param_hashes +
            output_hashes +
            retry_pattern +
            execution_order +
            timeout_values +
            timeout_trigger_flags
        )

        HARDENING: This computation is fully deterministic and
        will produce identical results for identical execution paths.
        """
        data = {
            "intent_sequence": self.intent_sequence,
            "tool_sequence": self.tool_sequence,
            "param_hashes": self.param_hashes,
            "output_hashes": self.output_hashes,
            "retry_pattern": self.retry_pattern,
            "execution_order": self.execution_order,
            "timeout_values": self.timeout_values,
            "timeout_trigger_flags": self.timeout_trigger_flags,
        }
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
        self.fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return self.fingerprint

    def add_step(self, entry: WALEntry) -> None:
        """Add a WAL entry to the fingerprint computation."""
        self.intent_sequence.append(entry.intent)
        self.tool_sequence.append(entry.tool_name)
        self.param_hashes.append(entry.params_hash)
        self.output_hashes.append(entry.output_hash)
        self.retry_pattern.append((entry.retry_count, entry.retry_reason.value))
        self.execution_order.append(entry.execution_order)
        self.timeout_values.append(entry.latency_metadata.timeout_ms)
        self.timeout_trigger_flags.append(entry.latency_metadata.did_timeout)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionFingerprint:
        return cls(**data)


@dataclass
class DriftClassification:
    """
    Classification of logic drift between executions.

    Used by the evaluation rig to categorize mismatches
    and determine failure severity.
    """
    class DriftType(str, Enum):
        INTENT_DRIFT = "intent_drift"
        TOOL_DRIFT = "tool_drift"
        PARAM_DRIFT = "param_drift"
        EXECUTION_DRIFT = "execution_drift"
        OUTPUT_DRIFT = "output_drift"
        RETRY_DRIFT = "retry_drift"
        TIMEOUT_DRIFT = "timeout_drift"
        SIDE_EFFECT_DRIFT = "side_effect_drift"  # CRITICAL - fails CI immediately

    drift_type: DriftType
    expected_value: Any
    actual_value: Any
    step_id: str
    is_critical: bool = False

    def __post_init__(self):
        # Side-effect drift is always critical
        if self.drift_type == self.DriftType.SIDE_EFFECT_DRIFT:
            self.is_critical = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_type": self.drift_type.value,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "step_id": self.step_id,
            "is_critical": self.is_critical,
        }


def compute_params_hash(params: dict[str, Any]) -> str:
    """
    Compute deterministic hash of tool parameters.

    Parameters are sorted by key to ensure deterministic hashing
    regardless of insertion order.

    HARDENING: Uses stable JSON serialization with sort_keys=True
    and minimal separators for cross-platform consistency.
    """
    encoded = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_output_hash(output: Any) -> str:
    """
    Compute deterministic hash of tool output.

    Output must be serializable to JSON for hashing.

    HARDENING: Uses stable JSON serialization with sort_keys=True
    and minimal separators for cross-platform consistency.
    """
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def current_time_ms() -> int:
    """
    Get current time in milliseconds.

    NOTE: This is a volatile value and should NOT be used in
    fingerprint computation. Use only for latency measurement
    and debugging.
    """
    return int(time.time() * 1000)
