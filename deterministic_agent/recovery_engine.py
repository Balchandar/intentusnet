"""
IntentusNet v1.4.1 Deterministic Agent - Recovery Engine

Deterministic recovery engine for resuming failed executions.

This engine provides:
- Safe recovery from crashes and failures
- Strict resume from last committed step
- Never re-run committed state-changing tools
- Abort if safe threshold exceeded
- Full deterministic recovery path

CRITICAL RULES:
1. Resume strictly using WAL state
2. Never re-run completed steps
3. Never regenerate intent for committed steps
4. Retry must preserve deterministic execution
5. Retry reason MUST be recorded
6. Abort if retry exceeds safe threshold
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable

from .models import (
    WALEntry,
    SideEffectClass,
    RetryReason,
    ExecutionFingerprint,
)
from .wal_engine import WALReader, WALState, WALIntegrityError

logger = logging.getLogger("intentusnet.recovery")


class RecoveryDecision(str, Enum):
    """
    Recovery decision after analyzing WAL state.

    RESUME: Safe to resume from last committed step
    ABORT: Must abort (irreversible step in ambiguous state)
    COMPLETE: Execution already completed
    NOT_FOUND: No WAL found for execution
    """
    RESUME = "resume"
    ABORT = "abort"
    COMPLETE = "complete"
    NOT_FOUND = "not_found"


@dataclass
class RecoveryAnalysis:
    """
    Result of WAL analysis for recovery.

    Contains all information needed to make deterministic
    recovery decisions.
    """
    execution_id: str
    decision: RecoveryDecision
    reason: str

    # WAL state
    wal_state: Optional[WALState] = None
    execution_state: str = ""
    last_committed_step_id: Optional[str] = None
    pending_step_id: Optional[str] = None

    # Recovery details
    committed_step_count: int = 0
    can_resume_from: int = 0  # Execution order to resume from
    idempotency_keys: set[str] = field(default_factory=set)

    # Risk assessment
    has_pending_irreversible: bool = False
    pending_side_effect_class: Optional[SideEffectClass] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "decision": self.decision.value,
            "reason": self.reason,
            "execution_state": self.execution_state,
            "last_committed_step_id": self.last_committed_step_id,
            "pending_step_id": self.pending_step_id,
            "committed_step_count": self.committed_step_count,
            "can_resume_from": self.can_resume_from,
            "has_pending_irreversible": self.has_pending_irreversible,
            "pending_side_effect_class": (
                self.pending_side_effect_class.value
                if self.pending_side_effect_class else None
            ),
        }


class RecoveryEngine:
    """
    Deterministic recovery engine for failed executions.

    RECOVERY ALGORITHM:
    1. Scan WAL for incomplete executions
    2. For each incomplete execution:
       - Read WAL with integrity verification
       - Reconstruct execution state
       - Check for pending irreversible steps
       - Decide: RESUME or ABORT

    RECOVERY RULES:
    - RESUME if:
      - All pending steps are READ_ONLY or have not started
      - No ambiguous irreversible step state
    - ABORT if:
      - Irreversible step started but not completed
      - WAL integrity check failed
      - State is ambiguous

    USAGE:
        recovery = RecoveryEngine("./logs")

        # Analyze WAL for recovery
        analysis = recovery.analyze("execution-123")

        if analysis.decision == RecoveryDecision.RESUME:
            # Safe to resume
            state = recovery.prepare_resume(analysis)
            # Continue execution from state.can_resume_from
        elif analysis.decision == RecoveryDecision.ABORT:
            # Must abort
            recovery.abort(analysis, "Manual abort")
    """

    def __init__(
        self,
        wal_dir: str,
        max_retry_threshold: int = 5,
    ):
        """
        Initialize recovery engine.

        Args:
            wal_dir: Directory containing WAL files
            max_retry_threshold: Maximum retries before forced abort
        """
        self.wal_dir = Path(wal_dir)
        self.max_retry_threshold = max_retry_threshold

    def analyze(self, execution_id: str) -> RecoveryAnalysis:
        """
        Analyze WAL state for recovery decision.

        Args:
            execution_id: Execution ID to analyze

        Returns:
            RecoveryAnalysis with decision and details
        """
        wal_path = self.wal_dir / f"{execution_id}.jsonl"

        # Check if WAL exists
        if not wal_path.exists():
            return RecoveryAnalysis(
                execution_id=execution_id,
                decision=RecoveryDecision.NOT_FOUND,
                reason=f"WAL file not found: {wal_path}",
            )

        # Load and verify WAL
        try:
            reader = WALReader(str(wal_path))
            reader.load()
        except WALIntegrityError as e:
            logger.error(f"WAL integrity error for {execution_id}: {e}")
            return RecoveryAnalysis(
                execution_id=execution_id,
                decision=RecoveryDecision.ABORT,
                reason=f"WAL integrity check failed: {e}",
            )

        # Get execution state
        execution_state = reader.get_execution_state()

        # Already completed
        if execution_state == "completed":
            return RecoveryAnalysis(
                execution_id=execution_id,
                decision=RecoveryDecision.COMPLETE,
                reason="Execution already completed",
                execution_state=execution_state,
                last_committed_step_id=reader.get_last_committed_step(),
            )

        # Already aborted
        if execution_state == "aborted":
            return RecoveryAnalysis(
                execution_id=execution_id,
                decision=RecoveryDecision.ABORT,
                reason="Execution was previously aborted",
                execution_state=execution_state,
            )

        # Reconstruct state
        try:
            wal_state = reader.reconstruct_state()
        except WALIntegrityError as e:
            return RecoveryAnalysis(
                execution_id=execution_id,
                decision=RecoveryDecision.ABORT,
                reason=f"Failed to reconstruct state: {e}",
            )

        # Check for pending step
        pending_step = reader.get_pending_step()

        if pending_step is None:
            # No pending step - safe to resume
            return RecoveryAnalysis(
                execution_id=execution_id,
                decision=RecoveryDecision.RESUME,
                reason="No pending step, safe to resume",
                wal_state=wal_state,
                execution_state=execution_state,
                last_committed_step_id=wal_state.last_committed_step_id,
                committed_step_count=len(wal_state.committed_steps),
                can_resume_from=len(wal_state.committed_steps) + 1,
                idempotency_keys=wal_state.idempotency_keys,
            )

        # Analyze pending step
        pending_side_effect = SideEffectClass(
            pending_step.get("side_effect_class", "read_only")
        )

        # CRITICAL: Cannot resume if irreversible step is pending
        if pending_side_effect == SideEffectClass.STATE_CHANGING:
            return RecoveryAnalysis(
                execution_id=execution_id,
                decision=RecoveryDecision.ABORT,
                reason=(
                    f"Pending STATE_CHANGING step '{pending_step.get('step_id')}' "
                    "cannot be safely resumed. Manual intervention required."
                ),
                wal_state=wal_state,
                execution_state=execution_state,
                last_committed_step_id=wal_state.last_committed_step_id,
                pending_step_id=pending_step.get("step_id"),
                has_pending_irreversible=True,
                pending_side_effect_class=pending_side_effect,
                idempotency_keys=wal_state.idempotency_keys,
            )

        # READ_ONLY or EXTERNAL steps can be retried
        return RecoveryAnalysis(
            execution_id=execution_id,
            decision=RecoveryDecision.RESUME,
            reason=f"Pending {pending_side_effect.value} step can be safely retried",
            wal_state=wal_state,
            execution_state=execution_state,
            last_committed_step_id=wal_state.last_committed_step_id,
            pending_step_id=pending_step.get("step_id"),
            committed_step_count=len(wal_state.committed_steps),
            can_resume_from=len(wal_state.committed_steps) + 1,
            pending_side_effect_class=pending_side_effect,
            idempotency_keys=wal_state.idempotency_keys,
        )

    def scan_incomplete(self) -> list[RecoveryAnalysis]:
        """
        Scan WAL directory for incomplete executions.

        Returns:
            List of RecoveryAnalysis for each incomplete execution
        """
        incomplete = []

        if not self.wal_dir.exists():
            return incomplete

        for wal_file in self.wal_dir.glob("*.jsonl"):
            execution_id = wal_file.stem
            analysis = self.analyze(execution_id)

            # Only include incomplete executions
            if analysis.decision not in (
                RecoveryDecision.COMPLETE,
                RecoveryDecision.NOT_FOUND,
            ):
                incomplete.append(analysis)

        return incomplete

    def prepare_resume(
        self,
        analysis: RecoveryAnalysis,
    ) -> dict[str, Any]:
        """
        Prepare state for resuming execution.

        Args:
            analysis: RecoveryAnalysis from analyze()

        Returns:
            Dict with resume state including:
            - execution_id
            - resume_from_order: Execution order to resume from
            - committed_steps: List of committed step IDs
            - idempotency_keys: Set of used idempotency keys
            - skip_step_id: Step ID to skip (if retrying pending)

        Raises:
            ValueError: If execution cannot be resumed
        """
        if analysis.decision != RecoveryDecision.RESUME:
            raise ValueError(
                f"Cannot resume execution: {analysis.reason}"
            )

        return {
            "execution_id": analysis.execution_id,
            "resume_from_order": analysis.can_resume_from,
            "committed_steps": list(analysis.wal_state.committed_steps),
            "idempotency_keys": analysis.idempotency_keys,
            "skip_step_id": analysis.pending_step_id,
            "last_committed_step_id": analysis.last_committed_step_id,
        }

    def should_abort_retry(
        self,
        execution_id: str,
        current_retry_count: int,
        retry_reason: RetryReason,
    ) -> tuple[bool, str]:
        """
        Determine if retry should be aborted.

        Args:
            execution_id: Execution ID
            current_retry_count: Current retry count
            retry_reason: Reason for retry

        Returns:
            Tuple of (should_abort, reason)
        """
        # Check retry threshold
        if current_retry_count >= self.max_retry_threshold:
            return True, (
                f"Retry count ({current_retry_count}) exceeds "
                f"threshold ({self.max_retry_threshold})"
            )

        # Certain retry reasons should not be retried
        non_retryable = {
            RetryReason.MALFORMED_OUTPUT,
            RetryReason.RUNTIME_ERROR,
        }

        if retry_reason in non_retryable:
            return True, f"Non-retryable error: {retry_reason.value}"

        return False, ""


class RecoveryManager:
    """
    High-level recovery manager for deterministic agent.

    Provides simplified interface for recovery operations.

    USAGE:
        manager = RecoveryManager("./logs")

        # Check if execution needs recovery
        if manager.needs_recovery("exec-123"):
            # Attempt recovery
            result = manager.recover("exec-123", executor_callback)

            if result.success:
                print(f"Recovered successfully: {result.fingerprint}")
            else:
                print(f"Recovery failed: {result.reason}")
    """

    def __init__(self, wal_dir: str):
        """
        Initialize recovery manager.

        Args:
            wal_dir: Directory containing WAL files
        """
        self.engine = RecoveryEngine(wal_dir)
        self.wal_dir = Path(wal_dir)

    def needs_recovery(self, execution_id: str) -> bool:
        """
        Check if execution needs recovery.

        Args:
            execution_id: Execution ID to check

        Returns:
            True if recovery is needed and possible
        """
        analysis = self.engine.analyze(execution_id)
        return analysis.decision == RecoveryDecision.RESUME

    def get_recovery_info(self, execution_id: str) -> dict[str, Any]:
        """
        Get recovery information for execution.

        Args:
            execution_id: Execution ID

        Returns:
            Dict with recovery analysis
        """
        analysis = self.engine.analyze(execution_id)
        return analysis.to_dict()

    def list_incomplete(self) -> list[dict[str, Any]]:
        """
        List all incomplete executions.

        Returns:
            List of recovery analyses
        """
        analyses = self.engine.scan_incomplete()
        return [a.to_dict() for a in analyses]

    def mark_aborted(self, execution_id: str, reason: str) -> bool:
        """
        Mark execution as aborted.

        Args:
            execution_id: Execution ID
            reason: Reason for abort

        Returns:
            True if successfully marked
        """
        wal_path = self.wal_dir / f"{execution_id}.jsonl"

        if not wal_path.exists():
            return False

        # Append abort entry to WAL
        from .wal_engine import WALWriter
        import json
        from datetime import datetime, timezone
        import hashlib
        import os

        # Read last hash
        with open(wal_path, "r") as f:
            lines = f.readlines()
            if lines:
                last_entry = json.loads(lines[-1].strip())
                prev_hash = last_entry.get("entry_hash")
                seq = last_entry.get("seq", 0) + 1
            else:
                prev_hash = None
                seq = 1

        # Create abort entry
        entry = {
            "seq": seq,
            "prev_hash": prev_hash,
            "entry_type": "execution.aborted",
            "execution_id": execution_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Compute hash
        encoded = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        entry["entry_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

        # Append to WAL
        with open(wal_path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

        return True


@dataclass
class RecoveryResult:
    """Result of recovery attempt."""
    success: bool
    execution_id: str
    fingerprint: Optional[str] = None
    reason: str = ""
    steps_recovered: int = 0


def create_recovery_manager(wal_dir: str = "./logs") -> RecoveryManager:
    """
    Factory function to create recovery manager.

    Args:
        wal_dir: WAL directory path

    Returns:
        Configured RecoveryManager
    """
    return RecoveryManager(wal_dir)
