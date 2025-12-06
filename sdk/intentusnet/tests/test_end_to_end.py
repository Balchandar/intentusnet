# tests/test_end_to_end.py

import uuid
import datetime as dt

from intentusnet import IntentusRuntime, BaseAgent
from intentusnet.protocol.models import (
    AgentDefinition,
    AgentIdentity,
    AgentEndpoint,
    AgentHealth,
    AgentRuntimeInfo,
    Capability,
    IntentRef,
    AgentResponse,
    IntentEnvelope,
)


def _now_iso() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


def _make_math_def() -> AgentDefinition:
    cap = Capability(
        intent=IntentRef(name="addNumbers", version="1.0"),
        inputSchema={},
        outputSchema={},
        fallbackAgents=[]
    )
    return AgentDefinition(
        name="math-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["math"]),
        capabilities=[cap],
        endpoint=AgentEndpoint(type="local", address="math-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=_now_iso()),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class MathAgent(BaseAgent):
    def __init__(self, router, emcl):
        super().__init__(_make_math_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        a = env.payload.get("a", 0)
        b = env.payload.get("b", 0)
        return AgentResponse(
            version=env.version,
            status="success",
            payload={"result": a + b},
            metadata={"agent": self.definition.name, "timestamp": _now_iso()},
        )


def math_factory(router, emcl):
    return MathAgent(router, emcl)


def test_end_to_end_math_flow():
    runtime = IntentusRuntime()
    runtime.register_agent(math_factory)
    client = runtime.client()

    resp = client.send("addNumbers", {"a": 10, "b": 32})
    assert resp.status == "success"
    assert resp.payload["result"] == 42
