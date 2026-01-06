"""
Canonical Demo Agents for IntentusNet.

Demonstrates:
- Multi-target intent resolution
- Target filtering (exclude dangerous targets)
- Deterministic execution via agents
- WAL-based crash safety and recovery
"""

from __future__ import annotations

from typing import Any, Dict, List

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol import AgentDefinition, Capability, IntentRef
from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse


# -----------------------------------------------------------------------------
# Target Power Agents
# -----------------------------------------------------------------------------


class ServerPowerAgent(BaseAgent):
    """
    Handles: system.power.server
    Controls server power state (reversible - can be turned back on).
    """

    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="server-power-agent",
            version="1.0",
            nodePriority=10,
            capabilities=[
                Capability(intent=IntentRef(name="system.power.server", version="1.0"))
            ],
        )
        super().__init__(definition=definition, router=router)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        action = env.payload.get("action", "shutdown")
        target = env.payload.get("target", "server")

        return AgentResponse.success(
            payload={
                "target": target,
                "action": action,
                "status": "completed",
                "message": f"Server power {action} executed successfully",
            },
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )


class LightsPowerAgent(BaseAgent):
    """
    Handles: system.power.lights
    Controls lighting systems (reversible).
    """

    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="lights-power-agent",
            version="1.0",
            nodePriority=20,
            capabilities=[
                Capability(intent=IntentRef(name="system.power.lights", version="1.0"))
            ],
        )
        super().__init__(definition=definition, router=router)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        action = env.payload.get("action", "off")
        target = env.payload.get("target", "lights")

        return AgentResponse.success(
            payload={
                "target": target,
                "action": action,
                "status": "completed",
                "message": f"Lights power {action} executed successfully",
            },
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )


class CCTVPowerAgent(BaseAgent):
    """
    Handles: system.power.cctv
    Controls CCTV systems (DANGEROUS - should be filtered).
    """

    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="cctv-power-agent",
            version="1.0",
            nodePriority=30,
            capabilities=[
                Capability(intent=IntentRef(name="system.power.cctv", version="1.0"))
            ],
        )
        super().__init__(definition=definition, router=router)

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        action = env.payload.get("action", "off")
        target = env.payload.get("target", "cctv")

        return AgentResponse.success(
            payload={
                "target": target,
                "action": action,
                "status": "completed",
                "message": f"CCTV power {action} executed (DANGEROUS)",
            },
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )


# -----------------------------------------------------------------------------
# Maintenance Coordinator Agent
# -----------------------------------------------------------------------------


class MaintenanceCoordinatorAgent(BaseAgent):
    """
    Handles: system.maintenance.poweroff
    Orchestrates multi-target power operations for maintenance.

    This agent:
    1. Resolves targets from the intent
    2. Filters out dangerous targets (cctv)
    3. Executes power-off on allowed targets
    4. Returns a summary of operations

    Uses IntentusClient for downstream intent emission.
    """

    def __init__(self, router: Any):
        definition = AgentDefinition(
            name="maintenance-coordinator",
            version="1.0",
            nodePriority=1,
            capabilities=[
                Capability(
                    intent=IntentRef(name="system.maintenance.poweroff", version="1.0")
                )
            ],
        )
        super().__init__(definition=definition, router=router)

        # Client for downstream intents
        from intentusnet.core.client import IntentusClient
        from intentusnet.transport.inprocess import InProcessTransport

        self._client = IntentusClient(InProcessTransport(router))

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        # Extract targets from payload
        targets: List[str] = env.payload.get("targets", ["server", "lights", "cctv"])
        reason: str = env.payload.get("reason", "maintenance")

        # Dangerous targets that must be excluded
        excluded_targets = {"cctv"}

        # Filter targets
        allowed_targets = [t for t in targets if t not in excluded_targets]
        filtered_targets = [t for t in targets if t in excluded_targets]

        results: List[Dict[str, Any]] = []
        completed_steps: List[str] = []
        failed_steps: List[str] = []

        # Execute power-off for each allowed target
        for target in allowed_targets:
            intent_name = f"system.power.{target}"
            step_id = f"poweroff-{target}"

            try:
                response = self._client.send_intent(
                    intent_name=intent_name,
                    payload={"action": "shutdown", "target": target, "reason": reason},
                    target_agent=f"{target}-power-agent",
                )

                if response.error is None:
                    results.append(
                        {
                            "step_id": step_id,
                            "target": target,
                            "status": "success",
                            "response": response.payload,
                        }
                    )
                    completed_steps.append(step_id)
                else:
                    results.append(
                        {
                            "step_id": step_id,
                            "target": target,
                            "status": "failed",
                            "error": response.error.message,
                        }
                    )
                    failed_steps.append(step_id)

            except Exception as ex:
                results.append(
                    {
                        "step_id": step_id,
                        "target": target,
                        "status": "error",
                        "error": str(ex),
                    }
                )
                failed_steps.append(step_id)

        # Build summary
        summary = {
            "reason": reason,
            "requested_targets": targets,
            "allowed_targets": allowed_targets,
            "filtered_targets": filtered_targets,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "results": results,
            "all_success": len(failed_steps) == 0,
        }

        return AgentResponse.success(
            payload=summary,
            agent=self.definition.name,
            trace_id=env.metadata.traceId,
        )


# -----------------------------------------------------------------------------
# Agent Registration Helper
# -----------------------------------------------------------------------------


def register_all_agents(runtime) -> None:
    """
    Register all canonical demo agents with the runtime.
    """
    runtime.register_agent(ServerPowerAgent)
    runtime.register_agent(LightsPowerAgent)
    runtime.register_agent(CCTVPowerAgent)
    runtime.register_agent(MaintenanceCoordinatorAgent)
