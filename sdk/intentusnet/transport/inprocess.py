from __future__ import annotations
from ..protocol.models import IntentEnvelope, AgentResponse
from ..core.router import IntentRouter


class InProcessTransport:
    """
    In-process transport that directly calls the router.
    """

    def __init__(self, router: IntentRouter) -> None:
        self._router = router

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        return self._router.route_intent(env)
