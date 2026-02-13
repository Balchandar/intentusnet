"""
Gateway data models for v1.5.1 MCP Gateway Foundation.

Models:
- GatewayConfig: Gateway configuration
- GatewayExecution: Single execution record with seed + hashes
- GatewayState: Runtime gateway state
- ExecutionIndex: Fast execution lookup index
- DeterministicSeed: Seed capture for future deterministic replay
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from intentusnet.utils.timestamps import now_iso


class GatewayMode(str, Enum):
    """Gateway operational mode."""

    STDIO = "stdio"
    HTTP = "http"


class ExecutionStatus(str, Enum):
    """Execution lifecycle status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Crash during execution


@dataclass
class GatewayConfig:
    """
    Gateway configuration.

    Minimal and focused on v1.5.1 scope.
    """

    # Directories
    wal_dir: str = ".intentusnet/gateway/wal"
    index_dir: str = ".intentusnet/gateway/index"
    data_dir: str = ".intentusnet/gateway/data"

    # Gateway mode
    mode: GatewayMode = GatewayMode.STDIO

    # Target MCP server (stdio command or HTTP URL)
    target_command: Optional[str] = None  # For stdio: "npx @modelcontextprotocol/server-foo"
    target_url: Optional[str] = None  # For HTTP: "http://localhost:3000"

    # Performance
    wal_sync: bool = True  # fsync WAL writes (disable only for testing)
    max_execution_size: int = 10 * 1024 * 1024  # 10MB max per execution payload

    def validate(self) -> None:
        """Validate configuration."""
        if self.mode == GatewayMode.STDIO and not self.target_command:
            raise ValueError("stdio mode requires target_command")
        if self.mode == GatewayMode.HTTP and not self.target_url:
            raise ValueError("HTTP mode requires target_url")

    def ensure_dirs(self) -> None:
        """Create required directories."""
        for d in [self.wal_dir, self.index_dir, self.data_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)


@dataclass
class DeterministicSeed:
    """
    Deterministic seed captured at execution time.

    Captures entropy sources to prepare for future deterministic replay.
    """

    # Seed components
    timestamp_iso: str  # Wall-clock at execution start
    sequence_number: int  # Gateway-global monotonic counter
    process_id: int  # OS PID (for correlation)
    random_seed: str  # Captured random seed (hex)

    # Optional environment snapshot
    env_hash: Optional[str] = None  # Hash of relevant env vars

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_iso": self.timestamp_iso,
            "sequence_number": self.sequence_number,
            "process_id": self.process_id,
            "random_seed": self.random_seed,
            "env_hash": self.env_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeterministicSeed:
        return cls(
            timestamp_iso=data["timestamp_iso"],
            sequence_number=data["sequence_number"],
            process_id=data["process_id"],
            random_seed=data["random_seed"],
            env_hash=data.get("env_hash"),
        )

    @classmethod
    def capture(cls, sequence_number: int) -> DeterministicSeed:
        """Capture current deterministic seed."""
        random_bytes = os.urandom(32)
        return cls(
            timestamp_iso=now_iso(),
            sequence_number=sequence_number,
            process_id=os.getpid(),
            random_seed=random_bytes.hex(),
        )


def stable_json_hash(obj: Any) -> str:
    """Compute deterministic SHA-256 hash of JSON-serializable object."""
    encoded = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class GatewayExecution:
    """
    Single gateway execution record.

    Persisted via WAL and indexed for fast lookup.
    """

    execution_id: str
    deterministic_seed: DeterministicSeed

    # Request/Response
    request: Dict[str, Any]
    request_hash: str
    response: Optional[Dict[str, Any]] = None
    response_hash: Optional[str] = None

    # Tool call intercept
    method: str = ""  # MCP method (e.g. "tools/call")
    tool_name: Optional[str] = None  # Tool name if applicable

    # Timing
    started_at: str = ""
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None

    # Status
    status: ExecutionStatus = ExecutionStatus.PENDING
    error: Optional[str] = None

    # Metadata
    gateway_version: str = "1.5.1"

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "execution_id": self.execution_id,
            "deterministic_seed": self.deterministic_seed.to_dict(),
            "request": self.request,
            "request_hash": self.request_hash,
            "response": self.response,
            "response_hash": self.response_hash,
            "method": self.method,
            "tool_name": self.tool_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "error": self.error,
            "gateway_version": self.gateway_version,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GatewayExecution:
        return cls(
            execution_id=data["execution_id"],
            deterministic_seed=DeterministicSeed.from_dict(data["deterministic_seed"]),
            request=data["request"],
            request_hash=data["request_hash"],
            response=data.get("response"),
            response_hash=data.get("response_hash"),
            method=data.get("method", ""),
            tool_name=data.get("tool_name"),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            duration_ms=data.get("duration_ms"),
            status=ExecutionStatus(data.get("status", "pending")),
            error=data.get("error"),
            gateway_version=data.get("gateway_version", "1.5.1"),
        )


@dataclass
class GatewayState:
    """Runtime gateway state (in-memory)."""

    started_at: str = ""
    mode: GatewayMode = GatewayMode.STDIO
    target: str = ""
    execution_count: int = 0
    is_running: bool = False
    last_error: Optional[str] = None
    pid: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "mode": self.mode.value,
            "target": self.target,
            "execution_count": self.execution_count,
            "is_running": self.is_running,
            "last_error": self.last_error,
            "pid": self.pid,
        }


class ExecutionIndex:
    """
    Fast execution index backed by a JSON file.

    Provides O(1) lookup by execution_id and supports rebuild from WAL.
    Thread-safe for concurrent access.
    """

    def __init__(self, index_dir: str) -> None:
        self._index_dir = Path(index_dir)
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._index_dir / "executions.json"
        self._lock = threading.Lock()
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load index from disk."""
        if self._index_path.exists():
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("executions", {})
            except (json.JSONDecodeError, IOError):
                # Corrupted index - will be rebuilt
                self._entries = {}

    def _save(self) -> None:
        """Persist index to disk atomically."""
        tmp_path = self._index_path.with_suffix(".tmp")
        data = {
            "version": "1.5.1",
            "updated_at": now_iso(),
            "count": len(self._entries),
            "executions": self._entries,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # Atomic rename
        os.replace(str(tmp_path), str(self._index_path))

    def add(self, execution: GatewayExecution) -> None:
        """Add or update execution in index."""
        with self._lock:
            self._entries[execution.execution_id] = {
                "execution_id": execution.execution_id,
                "method": execution.method,
                "tool_name": execution.tool_name,
                "status": execution.status.value,
                "started_at": execution.started_at,
                "completed_at": execution.completed_at,
                "request_hash": execution.request_hash,
                "response_hash": execution.response_hash,
                "duration_ms": execution.duration_ms,
            }
            self._save()

    def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get execution index entry."""
        with self._lock:
            return self._entries.get(execution_id)

    def list_all(self) -> List[Dict[str, Any]]:
        """List all executions, ordered by started_at."""
        with self._lock:
            entries = list(self._entries.values())
        entries.sort(key=lambda e: e.get("started_at", ""))
        return entries

    def count(self) -> int:
        """Return number of indexed executions."""
        with self._lock:
            return len(self._entries)

    def rebuild_from_executions(self, executions: List[GatewayExecution]) -> int:
        """Rebuild index from execution records. Returns count."""
        with self._lock:
            self._entries = {}
            for ex in executions:
                self._entries[ex.execution_id] = {
                    "execution_id": ex.execution_id,
                    "method": ex.method,
                    "tool_name": ex.tool_name,
                    "status": ex.status.value,
                    "started_at": ex.started_at,
                    "completed_at": ex.completed_at,
                    "request_hash": ex.request_hash,
                    "response_hash": ex.response_hash,
                    "duration_ms": ex.duration_ms,
                }
            self._save()
            return len(self._entries)
