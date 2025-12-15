from __future__ import annotations
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from intentusnet.protocol.intent import (
    IntentEnvelope, IntentRef, IntentContext, IntentMetadata,
    RoutingOptions, RoutingMetadata,
)
from intentusnet.protocol.emcl import EMCLEnvelope
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.enums import ErrorCode

def to_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    return obj

def intent_envelope_from_dict(d: Dict[str, Any]) -> IntentEnvelope:
    return IntentEnvelope(
        version=d["version"],
        intent=IntentRef(**d["intent"]),
        payload=d.get("payload") or {},
        context=IntentContext(**d["context"]),
        metadata=IntentMetadata(**d["metadata"]),
        routing=RoutingOptions(**(d.get("routing") or {})),
        routingMetadata=RoutingMetadata(**(d.get("routingMetadata") or {})),
    )

def agent_response_from_dict(d: Dict[str, Any]) -> AgentResponse:
    err = d.get("error")
    error_obj = None
    if err:
        code = err.get("code")
        try:
            code = ErrorCode(code)
        except Exception:
            pass
        error_obj = ErrorInfo(
            code=code,
            message=err.get("message", ""),
            retryable=bool(err.get("retryable", False)),
            details=err.get("details") or {},
        )
    return AgentResponse(
        version=d.get("version", "1.0"),
        status=d["status"],
        payload=d.get("payload"),
        metadata=d.get("metadata") or {},
        error=error_obj,
    )

def emcl_envelope_from_dict(d: Dict[str, Any]) -> EMCLEnvelope:
    return EMCLEnvelope(**d)
