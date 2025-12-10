# intentusnet/core/runtime.py

from __future__ import annotations
from typing import Optional, Dict, Any

from intentusnet.core.registry import AgentRegistry
from intentusnet.core.router import IntentRouter
from intentusnet.core.orchestrator import Orchestrator
from intentusnet.core.tracing import IntentusNetTracer

from intentusnet.protocol.models import (
    IntentEnvelope,
    IntentRef,
    IntentMetadata,
    AgentResponse,
)
from intentusnet.utils import new_id

# Optional typing-only import (prevents circular import issues)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from intentusnet.security.emcl import EMCLProvider


class IntentusRuntime:
    """
    Top-level runtime wiring together:
    - Registry
    - Router (with optional EMCL)
    - Tracer
    - Orchestrator
    """

    def __init__(self, emcl_provider: "EMCLProvider | None" = None):
        # Core components
        self.registry = AgentRegistry()
        self.tracer = IntentusNetTracer()

        # Router gets optional EMCL provider
        self.router = IntentRouter(
            self.registry,
            self.tracer,
            emcl_provider=emcl_provider,   # <-- IMPORTANT PATCH
        )

        self.orchestrator = Orchestrator(self.router, self.tracer)

        # Store provider for external inspection
        self.emcl_provider = emcl_provider

    # ------------------------------------------------------------------
    def handle_intent(self, intent: str, payload: Dict[str, Any]) -> AgentResponse:
        """
        Single-shot intent execution through the router.
        """

        metadata = IntentMetadata(
            traceId=new_id(),
            requestId=new_id(),
            identityChain=["runtime"],
        )

        envelope = IntentEnvelope(
            intent=IntentRef(name=intent),
            payload=payload,
            metadata=metadata,
            context=None,
            routing=None,
            routingMetadata=None,
        )

        return self.router.route(envelope)

    # ------------------------------------------------------------------
    def run_workflow(self, definition, initial_payload: Dict[str, Any]):
        """
        High-level workflow execution (orchestrator).
        """
        return self.orchestrator.run(definition, initial_payload)
