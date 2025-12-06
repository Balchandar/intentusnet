# examples/orchestrator_demo/agents/primary_storage.py

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
            intent=IntentRef(name="storeDocumentPrimary", version="1.0"),
            inputSchema={},
            outputSchema={},
            fallbackAgents=["fallback-storage-agent"]
        )
    ]
    return AgentDefinition(
        name="primary-storage-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["storage", "primary"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address="primary-storage-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class PrimaryStorageAgent(BaseAgent):
    """
    Primary storage agent.
    For demo:
      - Fails if documentId contains 'fail' to trigger fallback.
    """

    def __init__(self, router, emcl):
        super().__init__(_make_agent_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        # Uncomment below for check fallback
        # raise Exception("Primary storage service is DOWN (simulated for demo)")
        doc_id = env.payload.get("documentId") or str(uuid.uuid4())
        summary = env.payload.get("summary")
        labels = env.payload.get("labels", [])

        # Artificial failure to test fallback
        if "fail" in doc_id.lower():
            raise RuntimeError(f"Primary storage failed for documentId={doc_id}")

        record: Dict[str, Any] = {
            "documentId": doc_id,
            "summary": summary,
            "labels": labels,
            "storedAt": dt.datetime.utcnow().isoformat() + "Z",
            "storageTier": "primary",
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


def create_primary_storage_agent(router, emcl) -> PrimaryStorageAgent:
    return PrimaryStorageAgent(router, emcl)
