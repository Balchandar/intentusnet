"""
Write-Ahead Log (WAL) for crash-safe execution.

The WAL is:
- Append-only (JSONL format)
- Written BEFORE any side effects
- Integrity-verified (hash chaining)
- The source of truth for execution state

Phase I REGULATED mode:
- WAL entries can be signed with Ed25519
- Signatures are stored per-entry
- Verification is offline-capable
"""

from .models import (
    WALEntry,
    WALEntryType,
    ExecutionState,
    WALSigner,
    WALVerifier,
    WALSignatureError,
)
from .writer import WALWriter, WALSigningError
from .reader import WALReader
from .recovery import RecoveryManager
from .signing import Ed25519WALSigner, Ed25519WALVerifier

__all__ = [
    # Core models
    "WALEntry",
    "WALEntryType",
    "ExecutionState",
    # Signing protocols (Phase I REGULATED)
    "WALSigner",
    "WALVerifier",
    "WALSignatureError",
    "WALSigningError",
    # Signing implementations
    "Ed25519WALSigner",
    "Ed25519WALVerifier",
    # Core components
    "WALWriter",
    "WALReader",
    "RecoveryManager",
]
