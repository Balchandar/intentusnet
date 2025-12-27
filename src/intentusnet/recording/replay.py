from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from .models import ExecutionRecord, sha256_hex
from .models import _to_plain


class ReplayError(RuntimeError):
    pass


@dataclass
class ReplayResult:
    response: Any
    execution_id: str
    envelope_hash_ok: bool


class ReplayEngine:
    def __init__(self, record: ExecutionRecord) -> None:
        self.record = record

    def is_replayable(self) -> tuple[bool, str]:
        if not self.record.header.replayable:
            return False, self.record.header.replayableReason or "Marked not replayable"
        if not self.record.finalResponse:
            return False, "Missing finalResponse"
        return True, "OK"

    def replay(self, *, env: Optional[Any] = None) -> ReplayResult:
        ok, reason = self.is_replayable()
        if not ok:
            raise ReplayError(f"Execution is not replayable: {reason}")

        envelope_hash_ok = True
        if env is not None:
            envelope_hash_ok = sha256_hex(_to_plain(env)) == self.record.header.envelopeHash

        # Return recorded output EXACTLY (no routing/model calls)
        return ReplayResult(
            response=self.record.finalResponse,
            execution_id=self.record.header.executionId,
            envelope_hash_ok=envelope_hash_ok,
        )
