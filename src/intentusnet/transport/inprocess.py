from __future__ import annotations
from intentusnet.protocol.models import IntentEnvelope, AgentResponse
from intentusnet.core.router import IntentRouter


class InProcessTransport:
    """
    Fastest transport — calls router directly.
    """

    def __init__(self, router: IntentRouter):
        self._router = router

    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        env.metadata.identityChain.append("inprocess-transport")
        return self._router.route(env)
