from __future__ import annotations
from typing import Any, Dict

def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "SearchIntent":
        q = (arguments.get("query") or "").strip()
        if not q:
            raise ValueError("missing query")
        return {"results": [f"mcp:{q}:x", f"mcp:{q}:y", f"mcp:{q}:z"]}
    raise ValueError(f"unknown tool: {name}")
