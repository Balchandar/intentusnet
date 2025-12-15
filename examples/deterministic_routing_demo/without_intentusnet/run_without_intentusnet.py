from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..shared.trace_printer import print_glue_trace

@dataclass
class Tool:
    name: str
    call: Callable[[Dict[str, Any]], Dict[str, Any]]

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in self._tools:
            raise KeyError(f"tool not found: {tool_name}")
        return self._tools[tool_name].call(args)

class LocalSearchTool:
    def __init__(self) -> None:
        self._fail_once = True

    def __call__(self, args: Dict[str, Any]) -> Dict[str, Any]:
        q = (args.get("query") or "").strip()
        if not q:
            raise ValueError("missing query")
        if self._fail_once:
            self._fail_once = False
            raise RuntimeError("local search warming up (simulated failure)")
        return {"results": [f"local:{q}:a", f"local:{q}:b"]}

class RemoteSearchTool:
    def __call__(self, args: Dict[str, Any]) -> Dict[str, Any]:
        q = (args.get("query") or "").strip()
        if not q:
            raise ValueError("missing query")
        return {"results": [f"remote:{q}:1", f"remote:{q}:2", f"remote:{q}:3"]}

class SummarizeTool:
    def __call__(self, args: Dict[str, Any]) -> Dict[str, Any]:
        results = args.get("results") or []
        if not results:
            raise ValueError("no results")
        return {"summary": f"summary(len={len(results)})"}

def run_without_intentusnet(*, query: str) -> None:
    trace: list[dict[str, Any]] = []
    reg = ToolRegistry()

    local_search = LocalSearchTool()
    remote_search = RemoteSearchTool()
    summarize = SummarizeTool()

    reg.register(Tool("search_local", local_search))
    reg.register(Tool("search_remote", remote_search))
    reg.register(Tool("summarize", summarize))

    tools = reg.list_tools()
    trace.append({"step": "discover", "component": "registry", "status": "ok", "details": f"tools={tools}"})

    search_order = ["search_local", "search_remote"]
    trace.append({"step": "select", "component": "app", "status": "ok", "details": f"order={search_order}"})

    search_result: Optional[dict[str, Any]] = None
    last_err: Optional[Exception] = None

    for tool_name in search_order:
        try:
            trace.append({"step": "call.search", "component": tool_name, "status": "try"})
            search_result = reg.call(tool_name, {"query": query})
            trace.append({"step": "call.search", "component": tool_name, "status": "ok"})
            break
        except Exception as ex:
            last_err = ex
            trace.append({"step": "call.search", "component": tool_name, "status": "fail", "details": str(ex)})
            continue

    if search_result is None:
        raise RuntimeError(f"search failed after fallback: {last_err}")

    try:
        trace.append({"step": "call.summary", "component": "summarize", "status": "try"})
        summary = reg.call("summarize", {"results": search_result["results"]})
        trace.append({"step": "call.summary", "component": "summarize", "status": "ok"})
    except Exception as ex:
        trace.append({"step": "call.summary", "component": "summarize", "status": "fail", "details": str(ex)})
        raise

    print("\nWITHOUT IntentusNet")
    print("result:", summary)
    print_glue_trace(trace)
