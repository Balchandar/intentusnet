from __future__ import annotations
from typing import Protocol

from intentusnet.protocol import IntentEnvelope, AgentResponse
from intentusnet.core.router import IntentRouter


class Transport(Protocol):
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:  # pragma: no cover
        ...


class InProcessTransport:
    """
    Fastest transport — directly calls the IntentRouter in the same process.
    No EMCL, no network, no metadata mutation.
    """

    def __init__(self, router: IntentRouter) -> None:
        self._router = router

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        return self._router.route_intent(env)
