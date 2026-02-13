"""
Execution Interceptor for MCP Gateway v1.5.1.

Intercepts MCP tool calls transparently and records:
- Full request/response pairs
- Deterministic seeds
- WAL entries (execution_start, execution_end)
- Request/response hashes
- Timing metadata

Non-blocking WAL writes with crash-safe commit.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from intentusnet.utils.timestamps import now_iso

from .models import (
    DeterministicSeed,
    ExecutionIndex,
    ExecutionStatus,
    GatewayConfig,
    GatewayExecution,
    stable_json_hash,
)

logger = logging.getLogger(__name__)


class GatewayWALWriter:
    """
    Gateway-specific WAL writer.

    Separate from the core IntentusNet WAL to avoid coupling.
    Uses the same append-only, hash-chained, fsync-safe pattern.
    """

    def __init__(self, wal_dir: str, *, sync: bool = True) -> None:
        self._wal_dir = Path(wal_dir)
        self._wal_dir.mkdir(parents=True, exist_ok=True)
        self._wal_path = self._wal_dir / "gateway.wal"
        self._lock = threading.Lock()
        self._seq = 0
        self._last_hash: Optional[str] = None
        self._sync = sync

        # Resume sequence from existing WAL
        self._resume_from_existing()

    def _resume_from_existing(self) -> None:
        """Resume seq counter and hash chain from existing WAL file."""
        if not self._wal_path.exists():
            return
        try:
            with open(self._wal_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._seq = entry.get("seq", self._seq)
                        self._last_hash = entry.get("entry_hash")
                    except json.JSONDecodeError:
                        break  # Stop at corruption
        except IOError:
            pass

    def append(self, entry_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Append WAL entry atomically.

        Returns the written entry dict.
        """
        import hashlib

        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "entry_type": entry_type,
                "timestamp_iso": now_iso(),
                "payload": payload,
                "prev_hash": self._last_hash,
                "version": "1.5.1",
            }

            # Compute hash
            hash_data = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
            entry["entry_hash"] = hashlib.sha256(hash_data).hexdigest()

            # Write atomically
            line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            with open(self._wal_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                if self._sync:
                    os.fsync(f.fileno())

            self._last_hash = entry["entry_hash"]
            return entry

    def read_all(self) -> list[Dict[str, Any]]:
        """Read all WAL entries."""
        entries = []
        if not self._wal_path.exists():
            return entries
        with open(self._wal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping corrupted WAL entry")
                    break
        return entries

    def read_for_execution(self, execution_id: str) -> list[Dict[str, Any]]:
        """Read WAL entries for a specific execution."""
        return [
            e
            for e in self.read_all()
            if e.get("payload", {}).get("execution_id") == execution_id
        ]

    def verify_integrity(self) -> tuple[bool, Optional[str]]:
        """
        Verify WAL hash chain integrity.

        Returns (True, None) if valid, (False, reason) if corrupt.
        """
        import hashlib

        entries = self.read_all()
        if not entries:
            return True, None

        prev_hash = None
        for i, entry in enumerate(entries):
            # Verify chain link
            if entry.get("prev_hash") != prev_hash:
                return False, f"Hash chain broken at seq={entry.get('seq')}"

            # Verify entry hash
            stored_hash = entry.pop("entry_hash", None)
            computed = hashlib.sha256(
                json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            entry["entry_hash"] = stored_hash

            if stored_hash != computed:
                return False, f"Entry hash mismatch at seq={entry.get('seq')}"

            prev_hash = stored_hash

        return True, None

    @property
    def entry_count(self) -> int:
        """Return current sequence number."""
        return self._seq


class ExecutionInterceptor:
    """
    Intercepts MCP requests/responses and records executions.

    Usage:
        interceptor = ExecutionInterceptor(config)
        execution = interceptor.begin(request)
        try:
            response = forward_to_server(request)
            interceptor.complete(execution.execution_id, response)
        except Exception as e:
            interceptor.fail(execution.execution_id, str(e))
    """

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        config.ensure_dirs()

        self._wal = GatewayWALWriter(config.wal_dir, sync=config.wal_sync)
        self._index = ExecutionIndex(config.index_dir)
        self._data_dir = Path(config.data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Monotonic execution counter (gateway-global)
        self._seq_lock = threading.Lock()
        self._global_seq = self._wal.entry_count

        # In-flight executions
        self._in_flight: Dict[str, GatewayExecution] = {}
        self._in_flight_lock = threading.Lock()

    @property
    def wal(self) -> GatewayWALWriter:
        """Access to the WAL writer (for testing/inspection)."""
        return self._wal

    @property
    def index(self) -> ExecutionIndex:
        """Access to the execution index."""
        return self._index

    def _next_seq(self) -> int:
        """Get next global sequence number (thread-safe)."""
        with self._seq_lock:
            self._global_seq += 1
            return self._global_seq

    def begin(self, request: Dict[str, Any], method: str = "") -> GatewayExecution:
        """
        Begin recording an execution.

        Writes execution_start WAL entry.
        Returns GatewayExecution with assigned execution_id and seed.
        """
        execution_id = str(uuid.uuid4())
        seq = self._next_seq()
        seed = DeterministicSeed.capture(seq)
        request_hash = stable_json_hash(request)

        # Extract tool name from MCP request
        tool_name = None
        if method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")

        started_at = now_iso()

        execution = GatewayExecution(
            execution_id=execution_id,
            deterministic_seed=seed,
            request=request,
            request_hash=request_hash,
            method=method,
            tool_name=tool_name,
            started_at=started_at,
            status=ExecutionStatus.IN_PROGRESS,
        )

        # WAL: execution_start (DURABILITY BOUNDARY)
        self._wal.append(
            "gateway.execution_start",
            {
                "execution_id": execution_id,
                "request_hash": request_hash,
                "method": method,
                "tool_name": tool_name,
                "deterministic_seed": seed.to_dict(),
                "started_at": started_at,
            },
        )

        # Track in-flight
        with self._in_flight_lock:
            self._in_flight[execution_id] = execution

        # Index (status: in_progress)
        self._index.add(execution)

        logger.debug(
            "Execution started: %s method=%s tool=%s", execution_id, method, tool_name
        )
        return execution

    def complete(
        self, execution_id: str, response: Dict[str, Any]
    ) -> GatewayExecution:
        """
        Complete an execution with response.

        Writes execution_end WAL entry and persists full execution data.
        """
        with self._in_flight_lock:
            execution = self._in_flight.pop(execution_id, None)

        if execution is None:
            raise ValueError(f"Unknown execution: {execution_id}")

        completed_at = now_iso()
        response_hash = stable_json_hash(response)

        # Calculate duration
        duration_ms = None
        if execution.started_at:
            try:
                from dateutil.parser import isoparse

                start = isoparse(execution.started_at)
                end = isoparse(completed_at)
                duration_ms = (end - start).total_seconds() * 1000
            except Exception:
                pass

        execution.response = response
        execution.response_hash = response_hash
        execution.completed_at = completed_at
        execution.duration_ms = duration_ms
        execution.status = ExecutionStatus.COMPLETED

        # WAL: execution_end
        self._wal.append(
            "gateway.execution_end",
            {
                "execution_id": execution_id,
                "response_hash": response_hash,
                "status": "completed",
                "completed_at": completed_at,
                "duration_ms": duration_ms,
            },
        )

        # Persist full execution data
        self._persist_execution(execution)

        # Update index
        self._index.add(execution)

        logger.debug("Execution completed: %s (%.1fms)", execution_id, duration_ms or 0)
        return execution

    def fail(self, execution_id: str, error: str) -> GatewayExecution:
        """
        Mark an execution as failed.

        Writes execution_end WAL entry with failure.
        """
        with self._in_flight_lock:
            execution = self._in_flight.pop(execution_id, None)

        if execution is None:
            raise ValueError(f"Unknown execution: {execution_id}")

        completed_at = now_iso()
        execution.completed_at = completed_at
        execution.status = ExecutionStatus.FAILED
        execution.error = error

        # WAL: execution_end (failed)
        self._wal.append(
            "gateway.execution_end",
            {
                "execution_id": execution_id,
                "status": "failed",
                "error": error,
                "completed_at": completed_at,
            },
        )

        # Persist (even failures)
        self._persist_execution(execution)

        # Update index
        self._index.add(execution)

        logger.warning("Execution failed: %s error=%s", execution_id, error)
        return execution

    def _persist_execution(self, execution: GatewayExecution) -> None:
        """Persist full execution data to disk."""
        path = self._data_dir / f"{execution.execution_id}.json"
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(execution.to_dict(), f, ensure_ascii=False, indent=2)
            f.flush()
            if self._config.wal_sync:
                os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))

    def load_execution(self, execution_id: str) -> Optional[GatewayExecution]:
        """Load a persisted execution by ID."""
        path = self._data_dir / f"{execution_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return GatewayExecution.from_dict(data)
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning("Failed to load execution %s: %s", execution_id, e)
            return None

    def list_executions(self) -> list[Dict[str, Any]]:
        """List all indexed executions."""
        return self._index.list_all()

    def get_in_flight(self) -> list[str]:
        """Get IDs of currently in-flight executions."""
        with self._in_flight_lock:
            return list(self._in_flight.keys())

    def recover_partial_executions(self) -> int:
        """
        Recover partial executions after crash.

        Scans WAL for started-but-not-completed executions and marks them.
        Returns number of partial executions found.
        """
        entries = self._wal.read_all()
        started = {}  # execution_id -> start entry
        completed = set()  # execution_ids that completed

        for entry in entries:
            payload = entry.get("payload", {})
            eid = payload.get("execution_id")
            if not eid:
                continue

            etype = entry.get("entry_type", "")
            if etype == "gateway.execution_start":
                started[eid] = payload
            elif etype == "gateway.execution_end":
                completed.add(eid)

        partial_count = 0
        for eid, start_payload in started.items():
            if eid in completed:
                continue

            # This execution started but never completed — mark as partial
            partial_count += 1
            logger.warning("Partial execution detected: %s", eid)

            # Write failure WAL entry
            self._wal.append(
                "gateway.execution_end",
                {
                    "execution_id": eid,
                    "status": "partial",
                    "error": "Gateway crash: execution did not complete",
                    "completed_at": now_iso(),
                },
            )

            # Update index entry if it exists
            seed_data = start_payload.get("deterministic_seed", {})
            seed = DeterministicSeed.from_dict(seed_data) if seed_data else DeterministicSeed.capture(0)

            execution = GatewayExecution(
                execution_id=eid,
                deterministic_seed=seed,
                request={},  # Original request may not be recoverable
                request_hash=start_payload.get("request_hash", ""),
                method=start_payload.get("method", ""),
                tool_name=start_payload.get("tool_name"),
                started_at=start_payload.get("started_at", ""),
                completed_at=now_iso(),
                status=ExecutionStatus.PARTIAL,
                error="Gateway crash: execution did not complete",
            )
            self._index.add(execution)

        return partial_count

    def rebuild_index(self) -> int:
        """
        Rebuild execution index from persisted data files.

        Returns number of executions indexed.
        """
        executions = []
        for path in sorted(self._data_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                executions.append(GatewayExecution.from_dict(data))
            except (json.JSONDecodeError, IOError, KeyError):
                logger.warning("Skipping corrupted execution file: %s", path.name)
        return self._index.rebuild_from_executions(executions)
