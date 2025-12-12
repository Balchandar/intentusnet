# intentusnet/adapters/mcp_adapter.py

from __future__ import annotations
from typing import Any, Dict, Optional
from ..protocol import (
    IntentEnvelope,
    IntentMetadata,
    IntentContext,
    RoutingOptions,
    RoutingMetadata,
    IntentRef,
    AgentResponse,
    ErrorInfo
)

from intentusnet.utils import new_id
from intentusnet.core.router import IntentRouter
from intentusnet.security.emcl.base import EMCLProvider


class MCPAdapter:

    def __init__(self, router: IntentRouter, *, emcl: Optional[EMCLProvider] = None):
        self._router = router
        self._emcl = emcl

    # ----------------------------------------------------------------------
    def _to_intent_envelope(self, req: Dict[str, Any]) -> IntentEnvelope:
        name = req["name"]
        args = req.get("arguments", {})

        if self._emcl:
            args = {"__emcl__": self._emcl.wrap(args)}

        metadata = IntentMetadata(
            traceId=new_id(),
            requestId=new_id(),
            identityChain=["mcp-adapter"],
        )

        context = IntentContext(
            sessionId=new_id(),
            workflowId=new_id(),
        )

        routing = RoutingOptions()  # default

        return IntentEnvelope(
            intent=IntentRef(name=name),
            payload=args,
            metadata=metadata,
            context=context,
            routing=routing,
            routingMetadata=RoutingMetadata(),
        )

    # ----------------------------------------------------------------------
    def _to_mcp_response(self, resp: AgentResponse) -> Dict[str, Any]:

        payload = resp.payload
        if payload and "__emcl__" in payload and self._emcl:
            payload = self._emcl.unwrap(payload["__emcl__"])

        if resp.error is None:
            return {"result": payload, "error": None}

        err: ErrorInfo = resp.error

        return {
            "result": None,
            "error": {
                "code": err.code.value,
                "message": err.message,
                "details": err.details,
            },
        }

    # ----------------------------------------------------------------------
    def handle_mcp_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        env = self._to_intent_envelope(req)
        resp = self._router.route(env)
        return self._to_mcp_response(resp)
