"""
MCP Adapter Transport for IntentusNet
-------------------------------------

Allows IntentusNet to act as a backend for MCP tool calls.

The adapter:
- Accepts MCP-compliant request dictionaries
- Converts them into IntentEnvelope
- Routes through IntentusNet runtime
- Converts AgentResponse back to MCP format
"""

from __future__ import annotations
from typing import Any, Dict, Optional

from ..protocol.models import (
    IntentEnvelope,
    IntentContext,
    IntentMetadata,
    IntentRef,
    RoutingOptions,
    RoutingMetadata,
)
from ..protocol.enums import Priority
from ..utils.timestamps import now_iso
from ..emcl.base import EMCLProvider
from ..utils.id_gen import generate_uuid


class MCPAdapter:
    """
    Converts MCP Tool Calls → IntentusNet → MCP responses.
    """

    def __init__(self, router, *, emcl: Optional[EMCLProvider] = None) -> None:
        self._router = router
        self._emcl = emcl

    # MCP → IntentusNet

    def _to_intent_envelope(self, mcp_request: Dict[str, Any]) -> IntentEnvelope:
        """
        Convert an MCP "tool" request into IntentEnvelope.
        """

        intent_name = mcp_request["name"]
        payload = mcp_request.get("arguments", {})

        ctx = IntentContext(
            sessionId=generate_uuid(),
            workflowId=generate_uuid(),
            memory={},
            history=[],
        )

        meta = IntentMetadata(
            sourceAgent="mcp-adapter",
            timestamp=now_iso(),
            priority=Priority.NORMAL,
        )

        routing = RoutingOptions(
            targetAgent=None,
            fallbackAgents=[],
            broadcast=False,
        )

        return IntentEnvelope(
            version="1.0",
            intent=IntentRef(name=intent_name, version="1.0"),
            payload=payload,
            context=ctx,
            metadata=meta,
            routing=routing,
            routingMetadata=RoutingMetadata(),
        )

    # IntentusNet → MCP

    def _to_mcp_response(self, response) -> Dict[str, Any]:
        """
        Convert AgentResponse → MCP tool result.
        """

        if response.status == "success":
            return {
                "result": response.payload,
                "error": None,
            }

        return {
            "result": None,
            "error": {
                "code": response.error.code if response.error else "UNKNOWN",
                "message": response.error.message if response.error else "Unknown error",
            },
        }

    # Public API

    def handle_mcp_request(self, mcp_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Entrypoint: Accepts an MCP tool request and returns an MCP tool response.
        """
        env = self._to_intent_envelope(mcp_request)

        # Route inside IntentusNet
        resp = self._router.route_intent(env)

        return self._to_mcp_response(resp)
