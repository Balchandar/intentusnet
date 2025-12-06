# examples/orchestrator_demo/agents/notification.py

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
            intent=IntentRef(name="sendNotification", version="1.0"),
            inputSchema={},
            outputSchema={},
            fallbackAgents=[]
        )
    ]
    return AgentDefinition(
        name="notification-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["notifier"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address="notification-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class NotificationAgent(BaseAgent):
    """
    Notification agent for demo:
    - Just prints notification to console.
    """

    def __init__(self, router, emcl):
        super().__init__(_make_agent_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        kind = env.payload.get("kind", "info")
        message = env.payload.get("message", "")
        target = env.payload.get("target", "console")

        print(f"[NotificationAgent] [{kind}] to={target}: {message}")

        payload: Dict[str, Any] = {
            "delivered": True,
            "kind": kind,
            "target": target,
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


def create_notification_agent(router, emcl) -> NotificationAgent:
    return NotificationAgent(router, emcl)
