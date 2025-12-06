# tests/test_registry.py

import uuid
import datetime as dt

from intentusnet import BaseAgent
from intentusnet.core.registry import AgentRegistry
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


def _make_agent_def(name: str, intents: list[str]) -> AgentDefinition:
    now = dt.datetime.utcnow().isoformat() + "Z"
    caps = [
        Capability(intent=IntentRef(name=i, version="1.0"), inputSchema={}, outputSchema={}, fallbackAgents=[])
        for i in intents
    ]
    return AgentDefinition(
        name=name,
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["executor"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address=name),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class DummyAgent(BaseAgent):
    def __init__(self, router, emcl, name: str, intents: list[str]):
        super().__init__(_make_agent_def(name, intents), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        return AgentResponse(
            version=env.version,
            status="success",
            payload={"receivedIntent": env.intent.name},
            metadata={"agent": self.definition.name, "timestamp": dt.datetime.utcnow().isoformat() + "Z"},
        )


def test_registry_register_and_find():
    reg = AgentRegistry()

    # router/emcl can be None for pure registry tests
    agent_a = DummyAgent(router=None, emcl=None, name="agent-a", intents=["intentA", "sharedIntent"])
    agent_b = DummyAgent(router=None, emcl=None, name="agent-b", intents=["intentB", "sharedIntent"])

    reg.register(agent_a)
    reg.register(agent_b)

    assert reg.get_agent("agent-a") is agent_a
    assert reg.get_agent("agent-b") is agent_b

    matches = reg.find_agents_for_intent(IntentRef(name="sharedIntent", version="1.0"))
    names = {a.definition.name for a in matches}
    assert names == {"agent-a", "agent-b"}
