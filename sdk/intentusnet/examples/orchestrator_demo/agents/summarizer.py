# examples/orchestrator_demo/agents/summarizer.py

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
            intent=IntentRef(name="summarizeDocument", version="1.0"),
            inputSchema={},
            outputSchema={},
            fallbackAgents=[]
        )
    ]
    return AgentDefinition(
        name="summarizer-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["summarizer"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address="summarizer-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class SummarizerAgent(BaseAgent):
    """
    Very simple text summarizer for demo:
    - returns first N characters and word count.
    """

    def __init__(self, router, emcl):
        super().__init__(_make_agent_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        doc: str = env.payload.get("document", "") or ""
        max_len = int(env.payload.get("maxLength", 200))

        summary = doc[:max_len]
        words = len(doc.split())

        payload: Dict[str, Any] = {
            "summary": summary,
            "wordCount": words,
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


def create_summarizer_agent(router, emcl) -> SummarizerAgent:
    return SummarizerAgent(router, emcl)
