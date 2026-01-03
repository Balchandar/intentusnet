"""
Write-Ahead Log (WAL) for crash-safe execution.

The WAL is:
- Append-only (JSONL format)
- Written BEFORE any side effects
- Integrity-verified (hash chaining)
- The source of truth for execution state
"""

from .models import WALEntry, WALEntryType, ExecutionState
from .writer import WALWriter
from .reader import WALReader
from .recovery import RecoveryManager

__all__ = [
    "WALEntry",
    "WALEntryType",
    "ExecutionState",
    "WALWriter",
    "WALReader",
    "RecoveryManager",
]
