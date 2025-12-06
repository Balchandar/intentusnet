# tests/test_protocol_models.py

import datetime as dt
import uuid

from intentusnet.protocol.models import (
    IntentRef,
    IntentContext,
    IntentMetadata,
    RoutingOptions,
    RoutingMetadata,
    IntentEnvelope,
    ErrorInfo,
    AgentResponse,
    AgentIdentity,
    Capability,
    AgentEndpoint,
    AgentHealth,
    AgentRuntimeInfo,
    AgentDefinition,
)
from intentusnet.protocol.enums import Priority, ErrorCode


def test_intent_envelope_structure():
    intent = IntentRef(name="testIntent", version="1.0")
    context = IntentContext(
        sessionId=str(uuid.uuid4()),
        workflowId=str(uuid.uuid4()),
        memory={"foo": "bar"},
        history=[{"step": 1}],
    )
    metadata = IntentMetadata(
        sourceAgent="unit-test-agent",
        timestamp=dt.datetime.utcnow().isoformat() + "Z",
        priority=Priority.HIGH,
        tags=["test"],
    )
    routing = RoutingOptions(targetAgent="some-agent", fallbackAgents=["fallback-agent"])
    routing_meta = RoutingMetadata()

    env = IntentEnvelope(
        version="1.0",
        intent=intent,
        payload={"x": 1},
        context=context,
        metadata=metadata,
        routing=routing,
        routingMetadata=routing_meta,
    )

    assert env.version == "1.0"
    assert env.intent.name == "testIntent"
    assert env.context.memory["foo"] == "bar"
    assert env.metadata.priority == Priority.HIGH
    assert env.routing.targetAgent == "some-agent"


def test_agent_definition_and_capabilities():
    now = dt.datetime.utcnow().isoformat() + "Z"
    cap = Capability(
        intent=IntentRef(name="doSomething", version="1.0"),
        inputSchema={},
        outputSchema={},
        fallbackAgents=[]
    )
    definition = AgentDefinition(
        name="test-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["executor"]),
        capabilities=[cap],
        endpoint=AgentEndpoint(type="local", address="test-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )

    assert definition.name == "test-agent"
    assert len(definition.capabilities) == 1
    assert definition.capabilities[0].intent.name == "doSomething"


def test_agent_response_error_info():
    error = ErrorInfo(
        code=ErrorCode.ROUTING_ERROR,
        message="Something went wrong",
        retryable=False,
        details={"hint": "check registry"},
    )
    resp = AgentResponse(
        version="1.0",
        status="error",
        payload=None,
        metadata={"agent": "router"},
        error=error,
    )

    assert resp.status == "error"
    assert resp.error is not None
    assert resp.error.code == ErrorCode.ROUTING_ERROR
    assert resp.error.details["hint"] == "check registry"
