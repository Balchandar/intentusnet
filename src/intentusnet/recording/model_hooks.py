from __future__ import annotations

from typing import Any, Dict, Optional
from .recorder import ExecutionRecorder


def record_model_call(
    recorder: Optional[ExecutionRecorder],
    *,
    agent: str,
    provider: str,
    input: Dict[str, Any],
    output: Dict[str, Any],
) -> None:
    if recorder is None:
        return
    recorder.record_event(
        "MODEL_CALL",
        {"agent": agent, "provider": provider, "input": input, "output": output},
    )
