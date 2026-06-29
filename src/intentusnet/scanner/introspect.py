"""
MCP introspection: enumerate a server's tools without invoking them.

Two transports, mirroring the gateway:
- stdio: launch the server command, exchange newline-delimited JSON-RPC
- http:  POST JSON-RPC to the server URL

Read-only: we only call `initialize` and `tools/list`. We never call `tools/call`.
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import ToolDef

_INIT_PARAMS = {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "intentus-scan", "version": "0.1.0"},
}


def _parse_tools(result: Dict[str, Any]) -> List[ToolDef]:
    tools = result.get("result", {}).get("tools", [])
    return [ToolDef.from_mcp(t) for t in tools if isinstance(t, dict)]


def introspect_http(url: str, *, timeout: float = 30.0) -> List[ToolDef]:
    """Enumerate tools from an HTTP MCP server."""
    import httpx

    with httpx.Client(timeout=timeout) as client:
        client.post(url, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS,
        })
        resp = client.post(url, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        return _parse_tools(resp.json())


def introspect_stdio(command: str, *, timeout: float = 30.0) -> List[ToolDef]:
    """Enumerate tools from a stdio MCP server launched via `command`."""
    proc = subprocess.Popen(
        command,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=1,
        text=True,
    )
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS})
        _read_until(proc, 1, timeout)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        result = _read_until(proc, 2, timeout)
        return _parse_tools(result or {})
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


def _send(proc: subprocess.Popen, msg: Dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()


def _read_until(proc: subprocess.Popen, want_id: int, timeout: float) -> Optional[Dict[str, Any]]:
    """Read JSON-RPC lines until one matches `want_id`, or timeout."""
    assert proc.stdout is not None
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == want_id:
            return msg
    return None


def introspect(
    *, stdio: Optional[str] = None, http: Optional[str] = None, timeout: float = 30.0
) -> Tuple[str, str, List[ToolDef]]:
    """
    Enumerate tools from a target.

    Returns (target, transport, tools).
    """
    if stdio:
        return stdio, "stdio", introspect_stdio(stdio, timeout=timeout)
    if http:
        return http, "http", introspect_http(http, timeout=timeout)
    raise ValueError("introspect() requires either stdio= or http=")
