# tests/test_transports.py

import datetime as dt
import uuid
from unittest.mock import patch, MagicMock

import pytest

from intentusnet import BaseAgent, IntentusRuntime
from intentusnet.transport.inprocess import InProcessTransport
from intentusnet.transport.http import HTTPTransport
from intentusnet.protocol.models import (
    IntentEnvelope,
    IntentRef,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
    AgentResponse,
    AgentDefinition,
    AgentIdentity,
    AgentEndpoint,
    AgentHealth,
    AgentRuntimeInfo,
    Capability,
)
from intentusnet.protocol.enums import Priority


def _now_iso() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


def _make_agent_def(name: str, intents: list[str]) -> AgentDefinition:
    caps = [
        Capability(intent=IntentRef(name=i, version="1.0"), inputSchema={}, outputSchema={},fallbackAgents=[])
        for i in intents
    ]
    return AgentDefinition(
        name=name,
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["executor"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address=name),
        health=AgentHealth(status="healthy", lastHeartbeat=_now_iso()),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class EchoAgent(BaseAgent):
    def __init__(self, router, emcl):
        super().__init__(_make_agent_def("echo-agent", ["echoIntent"]), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        return AgentResponse(
            version=env.version,
            status="success",
            payload={"echo": env.payload},
            metadata={"agent": self.definition.name, "timestamp": _now_iso()},
        )


def test_inprocess_transport_flow():
    runtime = IntentusRuntime()
    runtime.register_agent(lambda r, e: EchoAgent(r, e))
    client = runtime.client()

    resp = client.send("echoIntent", {"foo": "bar"})
    assert resp.status == "success"
    assert resp.payload["echo"]["foo"] == "bar"


@pytest.mark.parametrize("status_code", [200])
def test_http_transport_send_intent(status_code):
    # Minimal env + agent response for HTTPTransport mock
    env = IntentEnvelope(
        version="1.0",
        intent=IntentRef(name="dummy", version="1.0"),
        payload={"x": 1},
        context=IntentContext(sessionId=str(uuid.uuid4()), workflowId=str(uuid.uuid4())),
        metadata=IntentMetadata(
            sourceAgent=None,
            timestamp=_now_iso(),
            priority=Priority.NORMAL,
        ),
        routing=RoutingOptions(),
        routingMetadata=RoutingMetadata(),
    )

    transport = HTTPTransport("https://example.com/intentus/http")

    fake_resp = {
        "protocol": "INTENTUSNET/1.0",
        "protocolNegotiation": {"minVersion": "1.0", "maxVersion": "1.0"},
        "messageType": "response",
        "headers": {},
        "body": {
            "version": "1.0",
            "status": "success",
            "payload": {"ok": True},
            "metadata": {"agent": "mock-agent", "timestamp": _now_iso()},
            "error": None,
        },
    }

    with patch("intentusnet.transport.http.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = __import__("json").dumps(fake_resp)
        mock_post.return_value = mock_response

        resp = transport.send_intent(env)
        assert resp.status == "success"
        assert resp.payload["ok"] is True
