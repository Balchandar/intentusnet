# examples/orchestrator_demo/agents/classifier.py

import uuid
import datetime as dt
from typing import Dict, Any

from intentusnet import BaseAgent
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


def _make_agent_def() -> AgentDefinition:
    now = dt.datetime.utcnow().isoformat() + "Z"
    caps = [
        Capability(
            intent=IntentRef(name="classifyDocument", version="1.0"),
            inputSchema={},
            outputSchema={},
            fallbackAgents=[]
        )
    ]
    return AgentDefinition(
        name="classifier-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["classifier"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address="classifier-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class ClassifierAgent(BaseAgent):
    """
    Toy classifier:
    - tags document as 'long' or 'short'
    - tags simple topic based on keywords
    """

    def __init__(self, router, emcl):
        super().__init__(_make_agent_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        doc: str = env.payload.get("document", "") or ""

        labels = []
        if len(doc.split()) > 100:
            labels.append("long")
        else:
            labels.append("short")

        lower = doc.lower()
        if "error" in lower or "exception" in lower:
            labels.append("technical")
        if "patient" in lower or "diagnosis" in lower:
            labels.append("medical")
        if "invoice" in lower or "payment" in lower:
            labels.append("finance")

        payload: Dict[str, Any] = {
            "labels": labels,
        }

        return AgentResponse(
            version=env.version,
            status="success",
            payload=payload,
            metadata={
                "agent": self.definition.name,
                "timestamp": dt.datetime.utcnow().isoformat() + "Z",
            },
        )


def create_classifier_agent(router, emcl) -> ClassifierAgent:
    return ClassifierAgent(router, emcl)
