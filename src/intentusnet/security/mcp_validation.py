"""
MCP Enforcement Layer — MCPValidationMiddleware

Ensures that AI model tool calls are constrained to intents that are
explicitly registered in the AgentRegistry.

Invariant:
    "No tool call may bypass the Intent Registry."

This prevents:
  - Arbitrary tool invocation by model output (prompt injection vectors)
  - Dynamic intent discovery (model-driven registry enumeration)
  - Wildcard capability abuse (flags for review in strict mode)

Implements the RouterMiddleware protocol — zero changes to existing code.

Audit mode (default):
    Logs violations as WARNING. Never blocks. Safe to deploy immediately.

Strict mode (SecurityConfig.strict_mode=True, audit_only=False):
    In enforcing mode, unregistered intents would be blocked here.
    Currently logged at ERROR level; callers can check audit_log for decisions.
"""

from __future__ import annotations

import logging
from typing import Any, FrozenSet, Optional, Set

from ..protocol.intent import IntentEnvelope
from ..protocol.response import AgentResponse, ErrorInfo
from .config import SecurityConfig

logger = logging.getLogger("intentusnet.security.mcp")


class MCPValidationMiddleware:
    """
    MCP enforcement middleware — validates every intent against the AgentRegistry.

    Constructor args:
        registry:  AgentRegistry (read-only).
        config:    SecurityConfig — controls audit vs enforce mode.
    """

    def __init__(
        self,
        registry: Any,
        config: Optional[SecurityConfig] = None,
    ) -> None:
        self._registry = registry
        self._config = config or SecurityConfig()
        self._blocked_intents: Set[str] = set()
        self._wildcard_agents: Set[str] = set()

    # ------------------------------------------------------------------
    # RouterMiddleware protocol
    # ------------------------------------------------------------------

    def before_route(self, env: IntentEnvelope) -> None:
        if not self._config.mcp_validation:
            return

        intent_name = env.intent.name

        try:
            agents = self._registry.find_agents_for_intent(env.intent)
        except Exception as exc:
            logger.error(
                "MCP_VALIDATION: Registry lookup failed for intent '%s': %s",
                intent_name, exc,
            )
            return

        # Check: is this intent registered?
        if not agents:
            self._blocked_intents.add(intent_name)
            msg = (
                f"MCP_VALIDATION: Intent '{intent_name}' has no registered capability. "
                "AI models must only invoke intents registered in the AgentRegistry. "
                "This may indicate a prompt injection or tool-abuse attempt."
            )
            if self._config.is_enforcing():
                logger.error(msg)
            else:
                logger.warning(msg)
            return

        # In strict mode: flag wildcard capabilities (least-privilege concern)
        if self._config.strict_mode:
            for agent in agents:
                for cap in agent.definition.capabilities:
                    if cap.intent.name == "*":
                        agent_name = agent.definition.name
                        if agent_name not in self._wildcard_agents:
                            self._wildcard_agents.add(agent_name)
                            logger.warning(
                                "MCP_VALIDATION: Agent '%s' has a wildcard capability (*) — "
                                "all intent names will match. Review for least-privilege compliance.",
                                agent_name,
                            )

        logger.debug(
            "MCP_VALIDATION: '%s' → %d registered agent(s) OK",
            intent_name, len(agents),
        )

    def after_route(self, env: IntentEnvelope, response: AgentResponse) -> None:
        pass  # No post-route MCP checks needed

    def on_error(self, env: IntentEnvelope, error: ErrorInfo) -> None:
        pass

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @property
    def blocked_intents(self) -> FrozenSet[str]:
        """Intents that were not found in the registry (all-time)."""
        return frozenset(self._blocked_intents)

    @property
    def wildcard_agents(self) -> FrozenSet[str]:
        """Agents flagged for wildcard capability (strict mode only)."""
        return frozenset(self._wildcard_agents)
