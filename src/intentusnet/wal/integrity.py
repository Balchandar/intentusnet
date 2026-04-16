"""
WAL Integrity Public API

Provides verify_wal_integrity() — a standalone function for verifying
the cryptographic integrity of a WAL file outside of the writer lifecycle.

Returns a structured result usable for compliance reporting and forensic audits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .reader import WALReader, WALIntegrityError
from .models import WALEntry, WALVerifier


@dataclass
class WALIntegrityResult:
    """
    Result of a WAL integrity verification run.

    ok:
        True if the chain is intact and all hashes verify.

    entry_count:
        Total entries read.

    first_hash / last_hash:
        Boundary hashes for cross-referencing with audit systems.

    signed_count:
        Number of entries with Ed25519 signatures present.

    signature_failures:
        List of seq numbers where signature verification failed.

    errors:
        Human-readable error descriptions (empty when ok=True).
    """
    ok: bool
    entry_count: int
    first_hash: Optional[str]
    last_hash: Optional[str]
    signed_count: int = 0
    signature_failures: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "entry_count": self.entry_count,
            "first_hash": self.first_hash,
            "last_hash": self.last_hash,
            "signed_count": self.signed_count,
            "signature_failures": self.signature_failures,
            "errors": self.errors,
        }


def verify_wal_integrity(
    wal_dir: str,
    execution_id: str,
    *,
    verifier: Optional[WALVerifier] = None,
) -> WALIntegrityResult:
    """
    Verify the cryptographic integrity of a WAL file.

    Checks:
    1. File exists and is readable.
    2. All entries deserialize without corruption.
    3. Sequence numbers are monotonically increasing (1, 2, 3, ...).
    4. prev_hash chain is unbroken end-to-end.
    5. entry_hash matches recomputed SHA-256 for each entry.
    6. If verifier provided: Ed25519 signature verified on all signed entries.

    Args:
        wal_dir:      Directory containing the .wal file.
        execution_id: The execution whose WAL file to verify.
        verifier:     Optional WALVerifier for Ed25519 signature checks.
                      If None, signature fields are not verified (only noted).

    Returns:
        WALIntegrityResult with full details.
    """
    reader = WALReader(wal_dir, execution_id)

    if not reader.exists():
        return WALIntegrityResult(
            ok=False,
            entry_count=0,
            first_hash=None,
            last_hash=None,
            errors=[f"WAL file not found: {reader.wal_path}"],
        )

    try:
        entries: List[WALEntry] = reader.read_all(verify_integrity=True)
    except WALIntegrityError as exc:
        return WALIntegrityResult(
            ok=False,
            entry_count=0,
            first_hash=None,
            last_hash=None,
            errors=[f"Hash chain violation: {exc}"],
        )
    except Exception as exc:
        return WALIntegrityResult(
            ok=False,
            entry_count=0,
            first_hash=None,
            last_hash=None,
            errors=[f"Unexpected read error: {exc}"],
        )

    if not entries:
        return WALIntegrityResult(
            ok=True,
            entry_count=0,
            first_hash=None,
            last_hash=None,
        )

    signed_count = 0
    signature_failures: List[int] = []
    sig_errors: List[str] = []

    if verifier is not None:
        for entry in entries:
            if entry.is_signed:
                signed_count += 1
                try:
                    valid = entry.verify_signature(verifier)
                    if not valid:
                        signature_failures.append(entry.seq)
                        sig_errors.append(
                            f"Signature invalid at seq={entry.seq} (key_id={entry.signer_key_id})"
                        )
                except Exception as exc:
                    signature_failures.append(entry.seq)
                    sig_errors.append(f"Signature error at seq={entry.seq}: {exc}")
    else:
        signed_count = sum(1 for e in entries if e.is_signed)

    ok = len(signature_failures) == 0

    return WALIntegrityResult(
        ok=ok,
        entry_count=len(entries),
        first_hash=entries[0].entry_hash,
        last_hash=entries[-1].entry_hash,
        signed_count=signed_count,
        signature_failures=signature_failures,
        errors=sig_errors,
    )
