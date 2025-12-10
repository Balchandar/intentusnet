import asyncio
import websockets

from intentusnet.protocol.models import (
    IntentEnvelope,
    AgentResponse,
    ErrorInfo,
    ErrorCode,
)
from intentusnet.utils import json_dumps, json_loads


class WebSocketTransport:
    """
    Async WebSocket transport for interactive/streaming scenarios.
    """

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    async def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        env.metadata.identityChain.append("ws-transport")

        async with websockets.connect(self.endpoint) as ws:
            await ws.send(json_dumps(env.__dict__))
            resp_raw = await ws.recv()

        data = json_loads(resp_raw)

        if data.get("error"):
            err = data["error"]
            return AgentResponse.failure(
                ErrorInfo(
                    code=ErrorCode(err.get("code", "UNKNOWN")),
                    message=err.get("message", ""),
                    details=err.get("details", {}),
                )
            )

        return AgentResponse.success(data.get("payload"))
