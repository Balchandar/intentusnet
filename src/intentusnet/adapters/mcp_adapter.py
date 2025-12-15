from __future__ import annotations
from typing import Any, Dict, Optional

from intentusnet.core.client import IntentusClient
from intentusnet.protocol.response import AgentResponse, ErrorInfo
from intentusnet.protocol.enums import ErrorCode


class MCPAdapter:
    """
    Adapter between MCP-style tool calls and IntentusNet v1.

    This adapter:
    - does NOT touch router directly
    - does NOT invent metadata
    - uses IntentusClient as the official entry point
    """

    def __init__(self, client: IntentusClient):
        self._client = client

    # --------------------------------------------------
    # MCP → Intentus
    # --------------------------------------------------
    def handle_mcp_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        MCP request shape (assumed):
        {
          "name": "SearchIntent",
          "arguments": { ... }
        }
        """

        intent_name = req.get("name")
        arguments = req.get("arguments", {}) or {}

        if not intent_name:
            return self._mcp_error(
                ErrorInfo(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Missing MCP field: name",
                    retryable=False,
                    details={},
                )
            )

        # Call IntentusNet through the OFFICIAL client
        response: AgentResponse = self._client.send_intent(
            intent_name=intent_name,
            payload=arguments,
        )

        return self._to_mcp_response(response)

    # --------------------------------------------------
    # Intentus → MCP
    # --------------------------------------------------
    def _to_mcp_response(self, resp: AgentResponse) -> Dict[str, Any]:
        if resp.error is None:
            return {
                "result": resp.payload,
                "error": None,
            }

        err = resp.error
        return self._mcp_error(err)

    def _mcp_error(self, err: ErrorInfo) -> Dict[str, Any]:
        return {
            "result": None,
            "error": {
                "code": err.code.value,
                "message": err.message,
                "details": err.details or {},
            },
        }
