from __future__ import annotations
from typing import Protocol
from ..protocol.models import IntentEnvelope, AgentResponse


class Transport(Protocol):
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        ...
