from __future__ import annotations

from typing import Optional, List

from intentusnet.core.agent import BaseAgent
from intentusnet.core.router import IntentRouter
from intentusnet.transport.base import Transport
from intentusnet.protocol.intent import IntentEnvelope, IntentRef
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.agent import (
    AgentDefinition,
    AgentIdentity,
    AgentEndpoint,
    AgentHealth,
    AgentRuntimeInfo,
    Capability,
)
from intentusnet.protocol.enums import ErrorCode


class RemoteAgentProxy(BaseAgent):
    """
    Represents an agent hosted on another IntentusNet node.

    Router treats this exactly like a local agent.
    """

    def __init__(
        self,
        router: IntentRouter,
        *,
        agent_name: str,
        node_id: str,
        transport: Transport,
        intents: Optional[List[str]] = None,
        priority: int = 20,
    ) -> None:

        capabilities: List[Capability] = []
        for intent_name in intents or ["*"]:
           capabilities.append(
                Capability(
                    intent=IntentRef(name=intent_name, version="*"),
                    inputSchema={},
                    outputSchema={},
                )
            )


        definition = AgentDefinition(
            name=agent_name,
            version="1.0",
            identity=AgentIdentity(agentId=f"{node_id}:{agent_name}"),
            capabilities=capabilities,
            endpoint=AgentEndpoint(
                type="remote",
                address=f"node://{node_id}",
            ),
            health=AgentHealth(status="unknown", lastHeartbeat=""),
            runtime=AgentRuntimeInfo(
                language="remote",
                environment="distributed",
                scaling="external",
            ),
        )

        super().__init__(definition, router)

        self._transport = transport
        self._remote_node_id = node_id
        self._remote_agent_name = agent_name

    # ------------------------------------------------------------------
    # Business logic (router-safe)
    # ------------------------------------------------------------------
    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        """
        Forward intent to remote node via transport.
        """

        # Identity chain is already handled by BaseAgent.handle()
        # We only add proxy-specific info
        env.metadata.identityChain.append(
            f"proxy:{self._remote_node_id}:{self._remote_agent_name}"
        )

        try:
            response = self._transport.send_intent(env)
        except Exception as ex:
            return AgentResponse(
                version=env.version,
                status="error",
                payload=None,
                metadata={
                    "agent": self.definition.name,
                    "viaNode": self._remote_node_id,
                    "remote": True,
                },
                error=self.error(
                    f"Remote agent '{self._remote_agent_name}' on node "
                    f"'{self._remote_node_id}' failed: {ex}",
                    code=ErrorCode.INTERNAL_AGENT_ERROR,
                ),
            )

        # Mark response as remote
        response.metadata.setdefault("viaNode", self._remote_node_id)
        response.metadata.setdefault("viaAgent", self._remote_agent_name)
        response.metadata.setdefault("remote", True)

        return response
