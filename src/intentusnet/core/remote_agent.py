from __future__ import annotations

"""
RemoteAgentProxy — an agent that forwards execution to a remote IntentusNet node.

This enables distributed IntentusNet clusters:

    Node A router → RemoteAgentProxy → HTTP/ZMQ → Node B gateway → local agent → response

The router does NOT need to know the agent is remote.
This is the key abstraction that allows seamless multi-node orchestration.
"""

import dataclasses
from typing import Optional, List

from intentusnet.core.agent import BaseAgent
from intentusnet.core.router import IntentRouter
from intentusnet.transport.base import Transport
from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.agent import AgentDefinition, Capability


class RemoteAgentProxy(BaseAgent):
    """
    Represents an agent hosted on another IntentusNet node.

    Router sees this as:
        - name:      <remote agent name>
        - intents:   ["*"] or supplied capabilities
        - nodeId:    <remote node ID>
        - priority:  controls routing strategy (local-first, remote fallback, etc.)

    Internally, this class:
      - converts IntentEnvelope -> Transport call
      - forwards to remote node using the given Transport
      - returns AgentResponse as if it were local

    Benefits:
      - Unified routing across local + remote agents
      - Easy fallback/parallel multi-node execution
      - Transparent to the orchestrator / NLU / client
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
        """
        :param router: Router used by this node
        :param agent_name: Name of the agent on the remote node
        :param node_id: Unique ID for the remote node
        :param transport: Any Transport (HTTP/ZMQ/WS) to contact remote node
        :param intents: Capabilities exposed by the remote agent
        :param priority: Routing priority (lower = preferred)
        """
        definition = AgentDefinition(
            name=agent_name,
            capabilities=[
                Capability(
                    name=f"remote-{agent_name}",
                    intents=intents or ["*"],
                    priority=priority,
                )
            ],
            nodeId=node_id,
        )

        super().__init__(definition, router)

        self._transport = transport
        self._remote_agent_name = agent_name
        self._remote_node_id = node_id

    # ----------------------------------------------------------------------
    # Core agent behavior: forward to remote node
    # ----------------------------------------------------------------------
    def handle(self, env: IntentEnvelope) -> AgentResponse:
        """
        Forward execution to a remote node.
        """
        # Append hop to identityChain for trace/debug
        chain = getattr(env.metadata, "identityChain", []) or []
        chain.append(f"proxy:{self._remote_node_id}:{self._remote_agent_name}")
        env.metadata.identityChain = chain

        # Add routing hint (useful for debugging or remote auth)
        env.metadata.origin = env.metadata.__dict__.get("origin", "local-node")
        env.metadata.remoteNode = self._remote_node_id
        env.metadata.remoteAgent = self._remote_agent_name

        # Delegate to transport (HTTP/ZMQ/WS)
        try:
            response = self._transport.send_intent(env)
        except Exception as ex:
            # Always surface this as an AgentResponse (never crash the router)
            return AgentResponse.failure(
                self.error(
                    f"Remote agent '{self._remote_agent_name}' on node "
                    f"'{self._remote_node_id}' failed: {ex}"
                )
            )

        # Attach node metadata
        response.metadata.setdefault("viaNode", self._remote_node_id)
        response.metadata.setdefault("viaAgent", self._remote_agent_name)
        response.metadata.setdefault("remote", True)

        return response
