from __future__ import annotations
from typing import Dict, Any

from intentusnet.protocol.models import (
    IntentEnvelope,
    IntentRef,
    IntentMetadata,
    AgentResponse,
)
from intentusnet.utils import new_id


class IntentusClient:

    def __init__(self, transport):
        self._transport = transport

    def send_intent(self, intent: str, payload: Dict[str, Any]) -> AgentResponse:
        """
        Sends an intent using the configured transport.
        Returns a full AgentResponse object.
        """
        env = IntentEnvelope(
            intent=IntentRef(name=intent),
            payload=payload,
            metadata=IntentMetadata(
                traceId=new_id(),
                requestId=new_id(),
                identityChain=["client"],
            ),
            context=None,
            routing=None,
            routingMetadata=None,
        )

        # Transport MUST return AgentResponse
        res: AgentResponse = self._transport.send_intent(env)

        return res
