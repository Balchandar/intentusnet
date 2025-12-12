from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import datetime as dt


@dataclass
class RouterDecision:
    agent: str
    intent: str
    reason: str
    timestamp: str = field(default_factory=lambda: dt.datetime.utcnow().isoformat() + "Z")


@dataclass
class TraceSpan:
    agent: str
    intent: str
    status: str
    latencyMs: float
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: dt.datetime.utcnow().isoformat() + "Z")
