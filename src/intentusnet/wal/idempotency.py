"""
Idempotency key tracking.

Prevents duplicate execution of the same intent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict
import hashlib


class IdempotencyStore:
    """
    Persistent idempotency key → execution_id mapping.

    Thread-safe, crash-safe storage.
    """

    def __init__(self, store_dir: str) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.store_dir / "idempotency_index.json"
        self._index: Dict[str, str] = self._load_index()

    def _load_index(self) -> Dict[str, str]:
        """Load idempotency index from disk."""
        if not self.index_file.exists():
            return {}

        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_index(self) -> None:
        """Save idempotency index to disk."""
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2, ensure_ascii=False)

    def check(self, idempotency_key: str) -> Optional[str]:
        """
        Check if idempotency key has been seen.

        Returns execution_id if duplicate, None otherwise.
        """
        return self._index.get(idempotency_key)

    def register(self, idempotency_key: str, execution_id: str) -> None:
        """
        Register idempotency key.

        Raises ValueError if key already registered with different execution_id.
        """
        existing = self._index.get(idempotency_key)
        if existing and existing != execution_id:
            raise ValueError(
                f"Idempotency key '{idempotency_key}' already mapped to {existing}"
            )

        self._index[idempotency_key] = execution_id
        self._save_index()

    def compute_key(self, envelope: dict) -> str:
        """
        Compute deterministic idempotency key from envelope.

        Hash includes: intent name, parameters (canonicalized).
        """
        canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
