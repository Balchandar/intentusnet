import zmq
from intentusnet.protocol.models import (
    IntentEnvelope,
    AgentResponse,
    ErrorInfo,
    ErrorCode,
)
from intentusnet.utils import json_dumps, json_loads


class ZeroMQTransport:

    def __init__(self, endpoint: str):
        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(endpoint)

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        env.metadata.identityChain.append("zeromq-transport")

        self._socket.send_string(json_dumps(env.__dict__))
        raw = self._socket.recv_string()
        data = json_loads(raw)

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
