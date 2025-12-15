from __future__ import annotations
from typing import Any

def print_glue_trace(trace: list[dict[str, Any]]) -> None:
    print("\nTRACE (glue code)")
    print(f"{'step':18} {'component':18} {'status':10} details")
    for row in trace:
        print(f"{row['step'][:18]:18} {row['component'][:18]:18} {row['status'][:10]:10} {row.get('details','')}")

def print_intentus_trace(runtime: Any) -> None:
    sink = getattr(runtime, "trace_sink", None)
    if sink is None or not hasattr(sink, "get_spans"):
        print("\nTRACE (IntentusNet): trace sink not available")
        return

    spans = sink.get_spans()
    if not spans:
        print("\nTRACE (IntentusNet): (no spans recorded)")
        return

    print("\nTRACE (IntentusNet)")
    print(f"{'agent':22} {'intent':22} {'latencyMs':10} {'success':7} error")
    for s in spans:
        agent = getattr(s, "agent", "unknown")
        intent = getattr(s, "intent", "unknown")
        latency = getattr(s, "latencyMs", getattr(s, "latency_ms", 0))
        success = getattr(s, "success", getattr(s, "status", "ok") == "ok")
        error = getattr(s, "errorCode", getattr(s, "error", None))
        if hasattr(error, "value"):
            error = error.value
        print(f"{str(agent)[:22]:22} {str(intent)[:22]:22} {int(latency):10} {str(success)[:7]:7} {error or ''}")
