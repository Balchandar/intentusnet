"""
Gateway Fast Replay Engine v1.5.1.

WAL playback only — no re-execution.

Reads stored execution data and returns the recorded response
along with full execution metadata and deterministic seed.

This is a LOOKUP operation, not re-execution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from intentusnet.utils.timestamps import now_iso

from .interceptor import ExecutionInterceptor, GatewayWALWriter
from .models import ExecutionIndex, GatewayExecution, ExecutionStatus

logger = logging.getLogger(__name__)


@dataclass
class ReplayResult:
    """
    Result of a fast replay (WAL playback).

    Contains the stored response and full execution metadata.
    This is a historical lookup — no code was re-executed.
    """

    execution_id: str
    response: Optional[Dict[str, Any]]
    request: Dict[str, Any]
    request_hash: str
    response_hash: Optional[str]
    deterministic_seed: Dict[str, Any]
    method: str
    tool_name: Optional[str]
    status: str
    started_at: str
    completed_at: Optional[str]
    duration_ms: Optional[float]
    wal_entries: List[Dict[str, Any]]
    replayed_at: str
    warning: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "response": self.response,
            "request": self.request,
            "request_hash": self.request_hash,
            "response_hash": self.response_hash,
            "deterministic_seed": self.deterministic_seed,
            "method": self.method,
            "tool_name": self.tool_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "wal_entries": self.wal_entries,
            "replayed_at": self.replayed_at,
            "warning": self.warning,
        }


class ReplayError(RuntimeError):
    """Raised when replay fails."""

    pass


class GatewayReplayEngine:
    """
    Fast Replay Engine for MCP Gateway.

    Replays executions by reading WAL entries and stored data.
    No re-execution of MCP tools occurs.

    Usage:
        engine = GatewayReplayEngine(interceptor)
        result = engine.replay("execution-id-here")
    """

    REPLAY_WARNING = (
        "This is the RECORDED response from execution time. "
        "No MCP tool was re-executed. No server was contacted. "
        "This is a WAL playback, NOT re-execution."
    )

    def __init__(self, interceptor: ExecutionInterceptor) -> None:
        self._interceptor = interceptor

    def replay(self, execution_id: str) -> ReplayResult:
        """
        Replay an execution by ID.

        Reads from persisted execution data and WAL entries.
        Returns the stored response with full metadata.

        Raises:
            ReplayError: If execution not found or not replayable.
        """
        # Load execution data
        execution = self._interceptor.load_execution(execution_id)
        if execution is None:
            raise ReplayError(f"Execution not found: {execution_id}")

        # Read WAL entries for this execution
        wal_entries = self._interceptor.wal.read_for_execution(execution_id)

        # Verify execution is in a terminal state
        if execution.status not in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.PARTIAL,
        ):
            raise ReplayError(
                f"Execution {execution_id} is in state '{execution.status.value}' "
                "and cannot be replayed. Only completed, failed, or partial executions "
                "can be replayed."
            )

        return ReplayResult(
            execution_id=execution.execution_id,
            response=execution.response,
            request=execution.request,
            request_hash=execution.request_hash,
            response_hash=execution.response_hash,
            deterministic_seed=execution.deterministic_seed.to_dict(),
            method=execution.method,
            tool_name=execution.tool_name,
            status=execution.status.value,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            duration_ms=execution.duration_ms,
            wal_entries=wal_entries,
            replayed_at=now_iso(),
            warning=self.REPLAY_WARNING,
        )

    def replay_summary(self, execution_id: str) -> Dict[str, Any]:
        """
        Get a concise replay summary (for CLI display).

        Returns key fields without full request/response bodies.
        """
        execution = self._interceptor.load_execution(execution_id)
        if execution is None:
            raise ReplayError(f"Execution not found: {execution_id}")

        wal_entries = self._interceptor.wal.read_for_execution(execution_id)

        return {
            "execution_id": execution.execution_id,
            "status": execution.status.value,
            "method": execution.method,
            "tool_name": execution.tool_name,
            "request_hash": execution.request_hash,
            "response_hash": execution.response_hash,
            "deterministic_seed": execution.deterministic_seed.to_dict(),
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "duration_ms": execution.duration_ms,
            "wal_entry_count": len(wal_entries),
            "has_response": execution.response is not None,
            "error": execution.error,
        }

    def is_replayable(self, execution_id: str) -> tuple[bool, str]:
        """
        Check if an execution can be replayed.

        Returns (True, "OK") or (False, reason).
        """
        execution = self._interceptor.load_execution(execution_id)
        if execution is None:
            return False, f"Execution not found: {execution_id}"

        if execution.status not in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.PARTIAL,
        ):
            return False, f"Execution in non-terminal state: {execution.status.value}"

        return True, "OK"
