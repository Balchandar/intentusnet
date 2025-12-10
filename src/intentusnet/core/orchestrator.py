# intentusnet/core/orchestrator.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time
import uuid

from intentusnet.core.router import IntentRouter
from intentusnet.core.tracing import IntentusNetTracer
from intentusnet.protocol.models import (
    IntentEnvelope,
    IntentRef,
    IntentMetadata,
    IntentContext,
    RoutingOptions,
    RoutingMetadata,
    AgentResponse,
    ErrorInfo,
    ErrorCode,
)
from intentusnet.utils import new_id


# ----------------------------------------------------------------------
# WORKFLOW MODELS
# ----------------------------------------------------------------------

@dataclass
class WorkflowStep:
    """
    Single step in a workflow.

    - name:   key used in context (ctx[name] = step_output)
    - intent: intent name to send to router
    - routing: (optional) per-step routing overrides
    """
    name: str
    intent: str
    routing: Optional[RoutingOptions] = None


@dataclass
class WorkflowDefinition:
    """
    Declarative workflow: ordered list of steps.
    """
    name: str
    steps: List[WorkflowStep]


# ----------------------------------------------------------------------
# ORCHESTRATOR
# ----------------------------------------------------------------------

class Orchestrator:
    """
    Simple multi-step orchestrator on top of IntentRouter.

    - Shares a dict context (ctx) across steps via env.payload
    - Each step is an intent routed by IntentRouter
    - Stops on first error and returns partial context + error
    - Uses a single traceId across all steps for tracing
    """

    def __init__(self, router: IntentRouter, tracer: Optional[IntentusNetTracer] = None):
        self._router = router
        self._tracer = tracer or IntentusNetTracer()

    # ------------------------------------------------------------------
    def _now_iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ------------------------------------------------------------------
    def run(
        self,
        definition: WorkflowDefinition,
        initial_payload: Dict[str, Any],
        *,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow steps in order.

        Returns:
            {
              "result": ctx,                 # on success
            }
        or:
            {
              "error": ErrorInfo,
              "context": ctx,               # partial context
              "failedStep": step.name,
            }
        """

        trace_id = trace_id or new_id()
        session_id = session_id or new_id()
        workflow_id = workflow_id or new_id()

        ctx: Dict[str, Any] = {"_initial": initial_payload}

        workflow_start = self._now_iso()
        workflow_span_id = str(uuid.uuid4())
        failed_step_name: Optional[str] = None
        error_info: Optional[ErrorInfo] = None

        for step in definition.steps:
            step_start = self._now_iso()
            step_span_id = str(uuid.uuid4())

            # Build per-step context object (metadata context, not payload)
            context = IntentContext(
                sessionId=session_id,
                workflowId=workflow_id,
                memory={},   # optional: you can map ctx into memory later
                history=[],  # optional future extension
            )

            metadata = IntentMetadata(
                traceId=trace_id,
                requestId=new_id(),
                identityChain=["orchestrator"],
            )

            routing = step.routing or RoutingOptions()

            env = IntentEnvelope(
                intent=IntentRef(name=step.intent),
                payload=ctx,  # <--- FULL WORKFLOW CONTEXT as payload
                metadata=metadata,
                context=context,
                routing=routing,
                routingMetadata=RoutingMetadata(),
            )

            res: AgentResponse = self._router.route(env)

            # Record per-step span
            self._tracer.record(
                traceId=trace_id,
                span={
                    "id": step_span_id,
                    "name": f"workflow_step:{definition.name}:{step.name}",
                    "start": step_start,
                    "end": self._now_iso(),
                    "attributes": {
                        "workflow": definition.name,
                        "step": step.name,
                        "intent": step.intent,
                        "selectedAgent": env.routingMetadata.selectedAgent if env.routingMetadata else None,
                        "candidates": env.routingMetadata.candidates if env.routingMetadata else [],
                        "error": bool(res.error),
                        "errorCode": res.error.code.value if res.error else None,
                    },
                },
            )

            if res.error:
                failed_step_name = step.name
                error_info = res.error
                break

            # Success: store step output in context
            ctx[step.name] = res.payload

        # Top-level workflow span
        self._tracer.record(
            traceId=trace_id,
            span={
                "id": workflow_span_id,
                "name": f"workflow:{definition.name}",
                "start": workflow_start,
                "end": self._now_iso(),
                "attributes": {
                    "workflow": definition.name,
                    "steps": [s.name for s in definition.steps],
                    "failedStep": failed_step_name,
                    "error": bool(error_info),
                },
            },
        )

        if error_info:
            return {
                "error": error_info,
                "context": ctx,
                "failedStep": failed_step_name,
            }

        return {
            "result": ctx,
        }
