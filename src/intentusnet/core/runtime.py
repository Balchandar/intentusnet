# FILE: src/intentusnet/core/runtime.py

from __future__ import annotations
from typing import Optional, Callable

from ..security.emcl.base import EMCLProvider
from .registry import AgentRegistry
from .router import IntentRouter
from .tracing import TraceSink, InMemoryTraceSink
from ..transport.inprocess import InProcessTransport
from ..transport.base import Transport
from ..agents.base import BaseAgent
from .client import IntentusClient


class IntentusRuntime:
    """
    High-level runtime that wires:
    - AgentRegistry
    - IntentRouter
    - Transport (in-process by default)
    - Optional EMCL provider
    """

    def __init__(
        self,
        *,
        trace_sink: Optional[TraceSink] = None,
        emcl_provider: Optional[EMCLProvider] = None,
    ) -> None:
        self.registry = AgentRegistry()
        self.trace_sink = trace_sink or InMemoryTraceSink()
        self.router = IntentRouter(self.registry, trace_sink=self.trace_sink)
        self.transport: Transport = InProcessTransport(self.router)
        self.emcl_provider = emcl_provider

    def register_agent(
        self,
        factory: Callable[[IntentRouter, Optional[EMCLProvider]], BaseAgent],
    ) -> BaseAgent:
        """
        Agent factory receives (router, emcl_provider) and returns a BaseAgent.
        """
        agent = factory(self.router)
        self.registry.register(agent)
        return agent

    def client(self) -> IntentusClient:
        return IntentusClient(self.transport)
