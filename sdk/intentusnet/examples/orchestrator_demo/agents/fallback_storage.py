# examples/orchestrator_demo/agents/fallback_storage.py

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
            intent=IntentRef(name="storeDocumentFallback", version="1.0"),
            inputSchema={},
            outputSchema={},
            fallbackAgents=[]
        )
    ]
    return AgentDefinition(
        name="fallback-storage-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["storage", "fallback"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address="fallback-storage-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class FallbackStorageAgent(BaseAgent):
    """
    Fallback storage agent.
    Always succeeds for demo.
    """

    def __init__(self, router, emcl):
        super().__init__(_make_agent_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        doc_id = env.payload.get("documentId") or str(uuid.uuid4())
        summary = env.payload.get("summary")
        labels = env.payload.get("labels", [])

        record: Dict[str, Any] = {
            "documentId": doc_id,
            "summary": summary,
            "labels": labels,
            "storedAt": dt.datetime.utcnow().isoformat() + "Z",
            "storageTier": "fallback",
        }

        return AgentResponse(
            version=env.version,
            status="success",
            payload={"record": record},
            metadata={
                "agent": self.definition.name,
                "timestamp": dt.datetime.utcnow().isoformat() + "Z",
            },
        )


def create_fallback_storage_agent(router, emcl) -> FallbackStorageAgent:
    return FallbackStorageAgent(router, emcl)
