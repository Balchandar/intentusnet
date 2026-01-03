"""
Execution-level concurrency locking.

Prevents concurrent execution of the same execution_id.
"""

from __future__ import annotations

import os
import time
import fcntl
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import json


@dataclass
class LockInfo:
    """Lock ownership information."""
    execution_id: str
    pid: int
    hostname: str
    acquired_at: float


class ExecutionLock:
    """
    File-based execution lock.

    Prevents concurrent execution, detects stale locks.
    """

    def __init__(self, lock_dir: str, execution_id: str, stale_timeout_sec: int = 3600) -> None:
        self.lock_dir = Path(lock_dir)
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.execution_id = execution_id
        self.stale_timeout_sec = stale_timeout_sec

        self.lock_file = self.lock_dir / f"{execution_id}.lock"
        self._fd: Optional[int] = None
        self._lock_info: Optional[LockInfo] = None

    def __enter__(self) -> "ExecutionLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def acquire(self, timeout_sec: int = 0) -> None:
        """
        Acquire lock.

        Raises TimeoutError if lock cannot be acquired within timeout.
        Raises ValueError if lock is held by another process.
        """
        import socket

        # Check for stale lock
        if self.lock_file.exists():
            existing_lock = self._read_lock_info()
            if existing_lock:
                # Check if process is still alive
                if not self._is_process_alive(existing_lock.pid):
                    # Stale lock - clean it
                    self._clean_stale_lock(existing_lock)
                elif time.time() - existing_lock.acquired_at > self.stale_timeout_sec:
                    # Timeout - clean it
                    self._clean_stale_lock(existing_lock)
                else:
                    raise ValueError(
                        f"Lock held by PID {existing_lock.pid} on {existing_lock.hostname}"
                    )

        # Acquire lock
        self._fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR, 0o644)

        start = time.time()
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if timeout_sec > 0 and time.time() - start > timeout_sec:
                    os.close(self._fd)
                    self._fd = None
                    raise TimeoutError(
                        f"Could not acquire lock for {self.execution_id} within {timeout_sec}s"
                    )
                time.sleep(0.1)

        # Write lock info
        self._lock_info = LockInfo(
            execution_id=self.execution_id,
            pid=os.getpid(),
            hostname=socket.gethostname(),
            acquired_at=time.time(),
        )

        lock_data = json.dumps({
            "execution_id": self._lock_info.execution_id,
            "pid": self._lock_info.pid,
            "hostname": self._lock_info.hostname,
            "acquired_at": self._lock_info.acquired_at,
        })

        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, lock_data.encode("utf-8"))

    def release(self) -> None:
        """Release lock."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            finally:
                self._fd = None

            # Remove lock file
            try:
                self.lock_file.unlink()
            except FileNotFoundError:
                pass

    def _read_lock_info(self) -> Optional[LockInfo]:
        """Read lock info from file."""
        try:
            with open(self.lock_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return LockInfo(
                    execution_id=data["execution_id"],
                    pid=data["pid"],
                    hostname=data["hostname"],
                    acquired_at=data["acquired_at"],
                )
        except Exception:
            return None

    def _is_process_alive(self, pid: int) -> bool:
        """Check if process is alive."""
        try:
            # Send signal 0 (no-op) to check if process exists
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _clean_stale_lock(self, lock_info: LockInfo) -> None:
        """Clean stale lock."""
        try:
            self.lock_file.unlink()
        except FileNotFoundError:
            pass
