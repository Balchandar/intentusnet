# examples/orchestrator_demo/agents/secure_storage.py

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
            intent=IntentRef(name="storeSensitiveMetadata", version="1.0"),
            inputSchema={},
            outputSchema={},
            fallbackAgents=[]
        )
    ]
    return AgentDefinition(
        name="secure-storage-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["secure-storage"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address="secure-storage-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class SecureStorageAgent(BaseAgent):
    """
    Simulated secure storage that would typically rely on EMCL.
    Here we just echo back payload and mark 'storedInSecureVault'.
    """

    def __init__(self, router, emcl):
        super().__init__(_make_agent_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        sensitive = env.payload.get("sensitiveMetadata", {})

        record: Dict[str, Any] = {
            "sensitiveMetadata": sensitive,
            "storedInSecureVault": True,
            "storedAt": dt.datetime.utcnow().isoformat() + "Z",
        }

        return AgentResponse(
            version=env.version,
            status="success",
            payload=record,
            metadata={
                "agent": self.definition.name,
                "timestamp": dt.datetime.utcnow().isoformat() + "Z",
            },
        )


def create_secure_storage_agent(router, emcl) -> SecureStorageAgent:
    return SecureStorageAgent(router, emcl)
