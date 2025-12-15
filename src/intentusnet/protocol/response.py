from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid

from .enums import ErrorCode


# ---- Error & Response ----

@dataclass
class ErrorInfo:
    code: ErrorCode
    message: str
    retryable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """
    Standard agent response contract.

    - status: "success" | "error"
    - payload: response data (for success)
    - error: ErrorInfo (for error)
    - metadata: free-form but must at least hold agent + traceId
    """
    version: str
    status: str        # "success" | "error"
    payload: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]
    error: Optional[ErrorInfo] = None

    # ----------------------------------------------------------
    # Helper constructors
    # ----------------------------------------------------------
    @classmethod
    def success(
        cls,
        payload: Dict[str, Any],
        *,
        agent: str,
        trace_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> "AgentResponse":

        meta = {
            "agent": agent,
            "traceId": trace_id or str(uuid.uuid4()),
        }

        if extra_metadata:
            meta.update(extra_metadata)

        return cls(
            version="1.0",
            status="success",
            payload=payload,
            metadata=meta,
            error=None,
        )

    @classmethod
    def failure(
        cls,
        error: ErrorInfo,
        *,
        agent: str,
        trace_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> "AgentResponse":

        meta = {
            "agent": agent,
            "traceId": trace_id or str(uuid.uuid4()),
        }

        if extra_metadata:
            meta.update(extra_metadata)

        return cls(
            version="1.0",
            status="error",
            payload=None,
            metadata=meta,
            error=error,
        )
