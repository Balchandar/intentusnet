from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from typing import Any, Dict, List, Optional
from enum import Enum
import hashlib
import json
import uuid


# ---------------------------------------------------------------------------
# Deterministic Clock
# ---------------------------------------------------------------------------

class DeterministicClock:
    """
    Monotonic deterministic clock used for execution ordering.
    """

    def __init__(self) -> None:
        self._seq = 0

    def next(self) -> int:
        self._seq += 1
        return self._seq

    def tick(self) -> int:
        return self.next()

    def current(self) -> int:
        return self._seq


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_plain(obj: Any) -> Any:
    """
    Convert objects into JSON-serializable, deterministic structures.
    """

    # Enums (Priority, RoutingStrategy, etc.)
    if isinstance(obj, Enum):
        return obj.value if isinstance(obj.value, (str, int)) else obj.name

    # Dataclasses
    if is_dataclass(obj):
        return {k: _to_plain(v) for k, v in asdict(obj).items()}

    # Dicts
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}

    # Lists
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]

    return obj


def stable_hash(obj: Any) -> str:
    plain = _to_plain(obj)
    encoded = json.dumps(
        plain,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_hex(obj: Any) -> str:
    """
    Backward-compatible alias for stable_hash.
    """
    return stable_hash(obj)



# ---------------------------------------------------------------------------
# Execution Record Models
# ---------------------------------------------------------------------------

@dataclass
class ExecutionEvent:
    """
    One atomic step in an execution timeline.
    """
    seq: int
    type: str
    payload: Dict[str, Any]


@dataclass
class ExecutionHeader:
    """
    Metadata describing the execution record.
    """
    executionId: str
    createdUtcIso: str
    envelopeHash: str
    replayable: bool = True
    replayableReason: Optional[str] = None


@dataclass
class ExecutionRecord:
    """
    Canonical execution record stored by IntentusNet.
    """

    header: ExecutionHeader
    envelope: Dict[str, Any]
    routerDecision: Optional[Dict[str, Any]]
    events: List[ExecutionEvent] = field(default_factory=list)
    finalResponse: Optional[Dict[str, Any]] = None

    # -------------------------------------------------
    # Factory (used by router / recorder)
    # -------------------------------------------------
    @classmethod
    def new(
        cls,
        *,
        execution_id: Optional[str] = None,
        created_utc_iso: str,
        env: Any,
        router_decision: Optional[Any] = None,
        replayable: bool = True,
    ) -> "ExecutionRecord":
        """
        Create a new execution record deterministically.
        """
        plain_env = _to_plain(env)
        envelope_hash = stable_hash(plain_env)

        header = ExecutionHeader(
            executionId=execution_id or str(uuid.uuid4()),
            createdUtcIso=created_utc_iso,
            envelopeHash=envelope_hash,
            replayable=replayable,
        )

        return cls(
            header=header,
            envelope=plain_env,
            routerDecision=_to_plain(router_decision)
            if router_decision is not None
            else None,
            events=[],
            finalResponse=None,
        )

    # -------------------------------------------------
    # Serialization
    # -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the execution record into a JSON-serializable dict.
        """
        return {
            "header": {
                "executionId": self.header.executionId,
                "createdUtcIso": self.header.createdUtcIso,
                "envelopeHash": self.header.envelopeHash,
                "replayable": self.header.replayable,
                "replayableReason": self.header.replayableReason,
            },
            "envelope": self.envelope,
            "routerDecision": self.routerDecision,
            "events": [
                {
                    "seq": e.seq,
                    "type": e.type,
                    "payload": e.payload,
                }
                for e in self.events
            ],
            "finalResponse": self.finalResponse,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionRecord":
        """
        Rehydrate an ExecutionRecord from stored JSON.
        """
        header_data = data["header"]

        header = ExecutionHeader(
            executionId=header_data["executionId"],
            createdUtcIso=header_data["createdUtcIso"],
            envelopeHash=header_data["envelopeHash"],
            replayable=header_data.get("replayable", True),
            replayableReason=header_data.get("replayableReason", None),
        )

        events = [
            ExecutionEvent(
                seq=e["seq"],
                type=e["type"],
                payload=e["payload"],
            )
            for e in data.get("events", [])
        ]

        return cls(
            header=header,
            envelope=data["envelope"],
            routerDecision=data.get("routerDecision"),
            events=events,
            finalResponse=data.get("finalResponse"),
        )

    def is_replayable(self) -> bool:
        return bool(self.header.replayable)