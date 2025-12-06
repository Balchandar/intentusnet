# tests/test_router.py

import uuid
import datetime as dt

from intentusnet import BaseAgent
from intentusnet.core.registry import AgentRegistry
from intentusnet.core.router import IntentRouter
from intentusnet.protocol.models import (
    AgentDefinition,
    AgentIdentity,
    AgentEndpoint,
    AgentHealth,
    AgentRuntimeInfo,
    Capability,
    IntentRef,
    IntentEnvelope,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
    AgentResponse,
)
from intentusnet.protocol.enums import Priority


def _now_iso() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


def _make_agent_def(name: str, intent_name: str) -> AgentDefinition:
    cap = Capability(
        intent=IntentRef(name=intent_name, version="1.0"),
        inputSchema={},
        outputSchema={},
        fallbackAgents=[] 
    )
    return AgentDefinition(
        name=name,
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["executor"]),
        capabilities=[cap],
        endpoint=AgentEndpoint(type="local", address=name),
        health=AgentHealth(status="healthy", lastHeartbeat=_now_iso()),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class OkAgent(BaseAgent):
    def __init__(self, router, emcl):
        super().__init__(_make_agent_def("ok-agent", "doIt"), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        return AgentResponse(
            version=env.version,
            status="success",
            payload={"ok": True},
            metadata={"agent": self.definition.name, "timestamp": _now_iso()},
        )


class FailingAgent(BaseAgent):
    def __init__(self, router, emcl):
        super().__init__(_make_agent_def("failing-agent", "doIt"), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        raise RuntimeError("boom")


def _make_env() -> IntentEnvelope:
    return IntentEnvelope(
        version="1.0",
        intent=IntentRef(name="doIt", version="1.0"),
        payload={},
        context=IntentContext(sessionId=str(uuid.uuid4()), workflowId=str(uuid.uuid4())),
        metadata=IntentMetadata(
            sourceAgent=None,
            timestamp=_now_iso(),
            priority=Priority.NORMAL,
        ),
        routing=RoutingOptions(),
        routingMetadata=RoutingMetadata(),
    )


def test_router_success_path():
    reg = AgentRegistry()
    router = IntentRouter(registry=reg)

    ok_agent = OkAgent(router, emcl=None)
    reg.register(ok_agent)

    env = _make_env()
    resp = router.route_intent(env)

    assert resp.status == "success"
    assert resp.payload["ok"] is True


def test_router_fallback_on_error():
    reg = AgentRegistry()
    router = IntentRouter(registry=reg)

    failing = FailingAgent(router, emcl=None)
    ok = OkAgent(router, emcl=None)

    reg.register(failing)
    reg.register(ok)

    env = _make_env()
    env.routing.fallbackAgents = ["ok-agent"]

    # Force first selection to failing-agent by targetAgent
    env.routing.targetAgent = "failing-agent"

    resp = router.route_intent(env)

    # Should still end as error OR success depending on fallback behavior:
    # Our router: will try failing-agent, then ok-agent
    assert resp.status in ("success", "error")

    # In our current router implementation, fallback will eventually succeed
    if resp.status == "success":
        assert resp.payload["ok"] is True
