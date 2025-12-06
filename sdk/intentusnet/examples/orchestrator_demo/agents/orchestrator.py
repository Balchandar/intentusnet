# examples/orchestrator_demo/agents/orchestrator.py

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
    IntentContext,
)
from intentusnet.protocol.enums import Priority


def _make_agent_def() -> AgentDefinition:
    now = dt.datetime.utcnow().isoformat() + "Z"
    caps = [
        Capability(
            intent=IntentRef(name="processDocument", version="1.0"),
            inputSchema={},
            outputSchema={},
            fallbackAgents=[]
        )
    ]
    return AgentDefinition(
        name="orchestrator-agent",
        version="1.0.0",
        identity=AgentIdentity(agentId=str(uuid.uuid4()), roles=["orchestrator"]),
        capabilities=caps,
        endpoint=AgentEndpoint(type="local", address="orchestrator-agent"),
        health=AgentHealth(status="healthy", lastHeartbeat=now),
        runtime=AgentRuntimeInfo(language="python", environment="local", scaling="manual"),
    )


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator agent that coordinates:
      1) summarizer-agent
      2) classifier-agent
      3) primary-storage-agent (with fallback to fallback-storage-agent)
      4) secure-storage-agent (for sensitive metadata)
      5) notification-agent
      6) logger-agent
    """

    def __init__(self, router, emcl):
        super().__init__(_make_agent_def(), router, emcl)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        document: str = env.payload.get("document", "") or ""
        document_id: str = env.payload.get("documentId") or str(uuid.uuid4())
        user: str = env.payload.get("user", "demo-user")

        # Use the same context across child calls for better tracing
        ctx: IntentContext = env.context
        print("Starts")
        # 1) Summarize
        sum_resp = self.emit_intent(
            "summarizeDocument",
            payload={"document": document, "maxLength": 300},
            context=ctx,
            tags=["orchestrator", "summarize"],
        )
        if sum_resp.status != "success":
            raise RuntimeError("Summarizer failed")

        summary = sum_resp.payload["summary"]
        word_count = sum_resp.payload["wordCount"]

        # 2) Classify
        cls_resp = self.emit_intent(
            "classifyDocument",
            payload={"document": document},
            context=ctx,
            tags=["orchestrator", "classify"],
        )
        if cls_resp.status != "success":
            raise RuntimeError("Classifier failed")

        labels = cls_resp.payload["labels"]

        # 3) Store (primary, then fallback)
        storage_payload: Dict[str, Any] = {
            "documentId": document_id,
            "summary": summary,
            "labels": labels,
        }

        primary_resp = self.emit_intent(
            "storeDocumentPrimary",
            payload=storage_payload,
            context=ctx,
            tags=["storage", "primary"],
        )

        if primary_resp.status == "success":
            storage_record = primary_resp.payload["record"]
        else:
            # Fallback storage
            fb_resp = self.emit_intent(
                "storeDocumentFallback",
                payload=storage_payload,
                context=ctx,
                tags=["storage", "fallback"],
            )
            if fb_resp.status != "success":
                raise RuntimeError("Both primary and fallback storage failed")
            storage_record = fb_resp.payload["record"]

        # 4) Secure storage for sensitive data (for demo: wordCount + labels)
        sensitive_metadata = {
            "user": user,
            "wordCount": word_count,
            "labels": labels,
        }
        secure_resp = self.emit_intent(
            "storeSensitiveMetadata",
            payload={"sensitiveMetadata": sensitive_metadata},
            context=ctx,
            tags=["secure", "metadata"],
        )
        if secure_resp.status != "success":
            raise RuntimeError("Secure storage failed")

        # 5) Notify
        msg = f"Document {document_id} processed for user={user}, labels={labels}"
        notif_resp = self.emit_intent(
            "sendNotification",
            payload={"kind": "info", "message": msg, "target": user},
            context=ctx,
            tags=["notification"],
        )
        if notif_resp.status != "success":
            raise RuntimeError("Notification failed")

        # 6) Log workflow result
        final_result = {
            "documentId": document_id,
            "summary": summary,
            "labels": labels,
            "storageRecord": storage_record,
            "secureMetadata": sensitive_metadata,
            "notified": True,
        }

        log_resp = self.emit_intent(
            "logWorkflowResult",
            payload={"result": final_result},
            context=ctx,
            tags=["logging"],
        )
        if log_resp.status != "success":
            raise RuntimeError("Logger failed")

        return AgentResponse(
            version=env.version,
            status="success",
            payload=final_result,
            metadata={
                "agent": self.definition.name,
                "timestamp": dt.datetime.utcnow().isoformat() + "Z",
            },
        )


def create_orchestrator_agent(router, emcl) -> OrchestratorAgent:
    return OrchestratorAgent(router, emcl)
