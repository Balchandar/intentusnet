"""Mock LLM and tool agents used by the IntentusNet demo.

Agents are deterministic by design. ``MockToolAgent.mutation`` is the hook
that lets the divergence scenario flip a single field after a recording.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MockLLMAgent:
    name: str = "llm-planner"
    latency_ms: float = 35.0

    def plan(self, prompt: str) -> Dict[str, Any]:
        time.sleep(self.latency_ms / 1000.0)
        return {
            "agent": self.name,
            "tool": "complaints_db.query",
            "tool_params": {"topic": "billing", "since_days": 30},
            "summary_template": "Found {count} complaints; top issue: {top_issue}",
        }


@dataclass
class MockToolAgent:
    name: str = "complaints_db"
    base_latency_ms: float = 12.0
    default_response: Dict[str, Any] = field(default_factory=lambda: {
        "rows": [
            {"id": 1, "topic": "billing", "severity": 3},
            {"id": 2, "topic": "billing", "severity": 5},
            {"id": 3, "topic": "billing", "severity": 2},
        ],
        "count": 3, "top_issue": "duplicate charge", "total": 120,
    })
    mutation: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    latency_override_ms: Optional[float] = None
    fail_next: bool = False

    def query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("mock tool transient failure")
        delay = self.latency_override_ms if self.latency_override_ms is not None else self.base_latency_ms
        time.sleep(delay / 1000.0)
        response = copy.deepcopy(self.default_response)
        return self.mutation(response) if self.mutation else response


def _step(seq: int, actor: str, action: str, payload: Dict[str, Any],
          latency_ms: float, error: Optional[str] = None) -> Dict[str, Any]:
    return {
        "seq": seq, "actor": actor, "action": action, "payload": payload,
        "latency_ms": round(latency_ms, 2), "error": error,
    }


def baseline_run(llm: MockLLMAgent, tool: MockToolAgent, prompt: str) -> Dict[str, Any]:
    """Direct LLM + tool call — no tracing, no signals, no enforcement."""
    plan = llm.plan(prompt)
    rows = tool.query(plan["tool_params"])
    summary = plan["summary_template"].format(count=rows["count"], top_issue=rows["top_issue"])
    return {"summary": summary, "tool_response": rows, "plan": plan}


def intentus_run(llm: MockLLMAgent, tool: MockToolAgent, prompt: str) -> Dict[str, Any]:
    """Same workload, structured trace captured per actor."""
    steps: List[Dict[str, Any]] = [_step(1, "intent", "summarize_complaints", {"prompt": prompt}, 0.0)]

    t0 = time.perf_counter()
    plan = llm.plan(prompt)
    steps.append(_step(2, llm.name, "plan", {"plan": plan}, (time.perf_counter() - t0) * 1000.0))

    t0 = time.perf_counter()
    error: Optional[str] = None
    rows: Optional[Dict[str, Any]] = None
    try:
        rows = tool.query(plan["tool_params"])
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    steps.append(_step(
        3, tool.name, "query",
        {"params": plan["tool_params"], "rows": rows},
        (time.perf_counter() - t0) * 1000.0, error,
    ))

    summary = (
        plan["summary_template"].format(count=rows["count"], top_issue=rows["top_issue"])
        if rows is not None else "<failed>"
    )
    return {
        "summary": summary, "tool_response": rows, "plan": plan,
        "steps": steps, "error": error,
        "latency_ms_total": sum(s["latency_ms"] for s in steps),
    }
