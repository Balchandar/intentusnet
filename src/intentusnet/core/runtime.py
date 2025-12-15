from __future__ import annotations

from typing import Optional, Callable, Sequence

from intentusnet.core.middleware import RouterMiddleware

from ..security.emcl.base import EMCLProvider
from .registry import AgentRegistry
from .router import IntentRouter
from .tracing import TraceSink, InMemoryTraceSink
from ..transport.inprocess import InProcessTransport
from ..transport.base import Transport
from .agent import BaseAgent
from .client import IntentusClient


class IntentusRuntime:
    """
    High-level runtime that wires together:

    - AgentRegistry: stores registered agents and their capabilities
    - IntentRouter:  routing + fallback logic over the registry
    - Transport:     how intents are sent/received (in-process by default)
    - TraceSink:     where trace spans are recorded
    - EMCLProvider:  optional encryption layer for transport boundaries

    This is the main entry point used by applications to host agents
    in-process or behind a gateway.
    """

    def __init__(
        self,
        *,
        registry: Optional[AgentRegistry] = None,
        trace_sink: Optional[TraceSink] = None,
        transport: Optional[Transport] = None,
        emcl_provider: Optional[EMCLProvider] = None,
        middlewares: Optional[Sequence[RouterMiddleware]] = None,
    ) -> None:
        self.registry: AgentRegistry = registry or AgentRegistry()
        self.trace_sink: TraceSink = trace_sink or InMemoryTraceSink()

        # Router is runtime-owned and configurable
        self.router: IntentRouter = IntentRouter(
            self.registry,
            trace_sink=self.trace_sink,
            middlewares=middlewares,
        )

        # Optional encryption provider (transport concern)
        self.emcl_provider: Optional[EMCLProvider] = emcl_provider

        # Transport (default: in-process)
        self.transport: Transport = transport or InProcessTransport(self.router)


    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------
    def register_agent(self, factory: Callable[[IntentRouter], BaseAgent]) -> BaseAgent:
        """
        Register an agent with the runtime.

        The factory must accept a single argument (IntentRouter) and return
        a BaseAgent instance. Typical usage:

            runtime.register_agent(lambda router: MyAgent(definition, router))
            # or, if MyAgent(router) is the constructor:
            runtime.register_agent(MyAgent)
        """
        agent = factory(self.router)

        # Allow agent to receive EMCL if it wants it
        if self.emcl_provider and getattr(agent, "emcl", None) is None:
            agent.emcl = self.emcl_provider

        self.registry.register(agent)
        return agent

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------
    def client(self) -> IntentusClient:
        """
        Create a client bound to this runtime's configured transport.

        This is the main way for application code (or demos) to interact
        with the runtime from within the same process.
        """
        return IntentusClient(self.transport)
