from __future__ import annotations

from typing import Dict, Any

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse

from intentusnet.transport.inprocess import InProcessTransport
from intentusnet.core.client import IntentusClient


# -----------------------------
# 1) Coordinator (workflow agent)
# -----------------------------
class TicketCoordinatorAgent(BaseAgent):
    """
    The ONLY agent that handles: support.ticket.analyze

    It composes a real workflow:
      analyze -> classify -> specialist -> final response

    This is the correct, production-faithful way to model multi-step behavior
    without abusing router priority as a "pipeline".
    """

    def __init__(self, definition, router):
        super().__init__(definition, router)
        self._client = IntentusClient(InProcessTransport(router))

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        text = env.payload.get("text", "")

        # Step 1: classification (deterministic target)
        classify_resp = self._client.send_intent(
            intent_name="support.ticket.classify",
            payload={"text": text},
            target_agent="classifier-agent",
        )

        category = (classify_resp.payload or {}).get("category", "other")

        # Step 2: specialist route (deterministic mapping)
        if category == "payment":
            specialist_intent = "support.ticket.payment"
            specialist_agent = "payment-expert-agent"
        elif category == "account":
            specialist_intent = "support.ticket.account"
            specialist_agent = "account-expert-agent"
        elif category == "fraud":
            specialist_intent = "support.ticket.fraud"
            specialist_agent = "fraud-detection-agent"
        else:
            specialist_intent = "support.ticket.escalate"
            specialist_agent = "human-fallback-agent"

        specialist_resp = self._client.send_intent(
            intent_name=specialist_intent,
            payload={"text": text},
            target_agent=specialist_agent,
        )

        # Final composed response
        return AgentResponse(
            version="1.0",
            status="ok",
            payload={
                "workflow": "support.ticket.analyze",
                "category": category,
                "selectedAgent": specialist_agent,
                "result": (specialist_resp.payload or {}),
            },
            metadata={},
            error=None,
        )


# -----------------------------
# 2) Classifier
# -----------------------------
class ClassifierAgent(BaseAgent):
    """
    Handles: support.ticket.classify
    """

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        text = env.payload.get("text", "").lower()

        if "payment" in text or "402" in text or "card" in text:
            category = "payment"
        elif "login" in text or "password" in text or "account" in text:
            category = "account"
        elif "fraud" in text or "suspicious" in text:
            category = "fraud"
        else:
            category = "other"

        return AgentResponse(
            version="1.0",
            status="ok",
            payload={"category": category},
            metadata={"agent": "classifier"},
            error=None,
        )


# -----------------------------
# 3) Payment expert (model swap lives here)
# -----------------------------
class PaymentExpertAgent(BaseAgent):
    """
    Handles: support.ticket.payment
    Model version is injected per runtime (v1/v2).
    """

    def __init__(self, definition, router, model_version: str):
        super().__init__(definition, router)
        self.model_version = model_version

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        # model swap behavior
        if self.model_version == "v1":
            decision = "Retry payment (provider transient failure)"
        else:
            decision = "Insufficient funds — ask customer to use another card"

        return AgentResponse(
            version="1.0",
            status="ok",
            payload={
                "agent": "payment-expert",
                "modelVersion": self.model_version,
                "decision": decision,
            },
            metadata={},
            error=None,
        )


# -----------------------------
# 4) Account expert
# -----------------------------
class AccountExpertAgent(BaseAgent):
    """
    Handles: support.ticket.account
    """

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        return AgentResponse(
            version="1.0",
            status="ok",
            payload={"agent": "account-expert", "decision": "Reset password / verify login"},
            metadata={},
            error=None,
        )


# -----------------------------
# 5) Fraud detection
# -----------------------------
class FraudDetectionAgent(BaseAgent):
    """
    Handles: support.ticket.fraud
    """

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        return AgentResponse(
            version="1.0",
            status="ok",
            payload={"agent": "fraud-detection", "decision": "Flag for manual review"},
            metadata={},
            error=None,
        )


# -----------------------------
# 6) Human fallback
# -----------------------------
class HumanFallbackAgent(BaseAgent):
    """
    Handles: support.ticket.escalate
    """

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        return AgentResponse(
            version="1.0",
            status="ok",
            payload={"agent": "human-fallback", "decision": "Escalate to support specialist"},
            metadata={},
            error=None,
        )
