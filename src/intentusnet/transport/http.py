import requests
from intentusnet.protocol.models import (
    IntentEnvelope,
    IntentMetadata,
    IntentRef,
    AgentResponse,
    ErrorInfo,
    ErrorCode,
)
from intentusnet.utils import json_dumps, json_loads


class HttpTransport:
    """
    Sends IntentEnvelope via HTTP POST.
    """

    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        env.metadata.identityChain.append("http-transport")

        resp = requests.post(
            self.endpoint,
            data=json_dumps(env.__dict__),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if resp.status_code != 200:
            return AgentResponse.failure(
                ErrorInfo(
                    code=ErrorCode.TRANSPORT_ERROR,
                    message=f"HTTP {resp.status_code}: {resp.text}",
                )
            )

        data = json_loads(resp.text)

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
