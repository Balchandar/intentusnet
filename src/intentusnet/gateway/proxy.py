"""
MCP Proxy Layer v1.5.1.

Transparent MCP proxy that intercepts and records all tool calls.

Supports:
- stdio: Wraps an MCP server command (e.g., "npx @modelcontextprotocol/server-foo")
- HTTP: Proxies to an HTTP-based MCP server

Architecture:
    MCP Client → [MCPProxyServer] → Existing MCP Server
                       ↓
              [ExecutionInterceptor]
                       ↓
                  WAL + Index

The proxy is fully transparent:
- No protocol modification
- No client changes required
- No server changes required
- Streaming: simple relay (pass-through)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, Optional

from intentusnet.utils.timestamps import now_iso

from .interceptor import ExecutionInterceptor
from .models import GatewayConfig, GatewayMode, GatewayState

logger = logging.getLogger(__name__)


# MCP JSON-RPC methods that represent tool calls (worth recording)
MCP_TOOL_METHODS = {
    "tools/call",
    "tools/list",
    "resources/read",
    "resources/list",
    "prompts/get",
    "prompts/list",
    "completion/complete",
}

# Methods that are protocol-level (pass through without recording)
MCP_PROTOCOL_METHODS = {
    "initialize",
    "initialized",
    "ping",
    "notifications/cancelled",
    "notifications/progress",
}


class MCPProxyServer:
    """
    Transparent MCP proxy server.

    Wraps an existing MCP server and intercepts tool calls
    for recording and later replay.
    """

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        self._interceptor = ExecutionInterceptor(config)
        self._state = GatewayState(
            mode=config.mode,
            target=config.target_command or config.target_url or "",
            pid=os.getpid(),
        )
        self._shutdown = threading.Event()
        self._server_process: Optional[subprocess.Popen] = None

    @property
    def interceptor(self) -> ExecutionInterceptor:
        return self._interceptor

    @property
    def state(self) -> GatewayState:
        return self._state

    def start(self) -> None:
        """
        Start the MCP proxy.

        For stdio mode: launches the target command as a subprocess
        and relays JSON-RPC messages between stdin/stdout.

        For HTTP mode: starts a FastAPI proxy server.
        """
        self._config.validate()
        self._config.ensure_dirs()

        # Recover from any previous crash
        partial = self._interceptor.recover_partial_executions()
        if partial > 0:
            logger.warning("Recovered %d partial executions from previous crash", partial)

        self._state.started_at = now_iso()
        self._state.is_running = True

        if self._config.mode == GatewayMode.STDIO:
            self._run_stdio_proxy()
        elif self._config.mode == GatewayMode.HTTP:
            self._run_http_proxy()

    def stop(self) -> None:
        """Stop the proxy gracefully."""
        self._shutdown.set()
        self._state.is_running = False

        if self._server_process is not None:
            try:
                self._server_process.terminate()
                self._server_process.wait(timeout=5)
            except Exception:
                self._server_process.kill()
            self._server_process = None

    def _run_stdio_proxy(self) -> None:
        """
        Run stdio MCP proxy.

        Reads JSON-RPC from stdin, forwards to subprocess,
        reads response from subprocess stdout, writes to our stdout.
        """
        cmd = self._config.target_command
        logger.info("Starting stdio proxy: %s", cmd)

        # Launch MCP server subprocess
        self._server_process = subprocess.Popen(
            cmd,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Set up signal handler for graceful shutdown
        def _signal_handler(signum, frame):
            self.stop()

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # Relay stderr in background
        stderr_thread = threading.Thread(
            target=self._relay_stderr,
            daemon=True,
        )
        stderr_thread.start()

        try:
            self._stdio_relay_loop()
        except (BrokenPipeError, EOFError):
            logger.info("Client disconnected")
        except Exception as e:
            logger.error("Proxy error: %s", e)
            self._state.last_error = str(e)
        finally:
            self.stop()

    def _stdio_relay_loop(self) -> None:
        """
        Main relay loop for stdio mode.

        Reads MCP JSON-RPC messages from stdin, intercepts tool calls,
        forwards to server, intercepts responses, writes to stdout.
        """
        server_stdin = self._server_process.stdin
        server_stdout = self._server_process.stdout

        while not self._shutdown.is_set():
            # Read request from client (stdin)
            request_line = sys.stdin.buffer.readline()
            if not request_line:
                break  # Client closed

            request_line = request_line.strip()
            if not request_line:
                continue

            try:
                request = json.loads(request_line)
            except json.JSONDecodeError:
                # Pass through non-JSON (could be headers, etc.)
                server_stdin.write(request_line + b"\n")
                server_stdin.flush()
                continue

            method = request.get("method", "")
            execution = None

            # Intercept tool-related methods
            if method in MCP_TOOL_METHODS:
                execution = self._interceptor.begin(request, method=method)
                self._state.execution_count += 1

            # Forward to server
            server_stdin.write(request_line + b"\n")
            server_stdin.flush()

            # Read response from server
            response_line = server_stdout.readline()
            if not response_line:
                if execution:
                    self._interceptor.fail(
                        execution.execution_id, "Server closed connection"
                    )
                break

            response_line = response_line.strip()

            try:
                response = json.loads(response_line)
            except json.JSONDecodeError:
                response = None

            # Complete interception
            if execution and response is not None:
                try:
                    self._interceptor.complete(execution.execution_id, response)
                except Exception as e:
                    logger.error(
                        "Failed to record execution %s: %s",
                        execution.execution_id,
                        e,
                    )

            # Forward response to client (stdout)
            sys.stdout.buffer.write(response_line + b"\n")
            sys.stdout.buffer.flush()

    def _relay_stderr(self) -> None:
        """Relay server stderr to our stderr."""
        if self._server_process is None:
            return
        try:
            for line in self._server_process.stderr:
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()
        except Exception:
            pass

    def _run_http_proxy(self) -> None:
        """
        Run HTTP MCP proxy.

        Creates a FastAPI app that proxies requests to the target URL.
        """
        try:
            import uvicorn
            from fastapi import FastAPI, Request
            from fastapi.responses import JSONResponse
        except ImportError:
            raise RuntimeError(
                "HTTP proxy requires fastapi and uvicorn. "
                "Install with: pip install fastapi uvicorn"
            )

        import httpx

        app = FastAPI(title="IntentusNet MCP Gateway", version="1.5.1")
        target_url = self._config.target_url

        @app.post("/")
        @app.post("/mcp")
        @app.post("/sse")
        async def proxy_request(request: Request):
            body = await request.json()
            method = body.get("method", "")
            execution = None

            # Intercept tool-related methods
            if method in MCP_TOOL_METHODS:
                execution = self._interceptor.begin(body, method=method)
                self._state.execution_count += 1

            # Forward to target
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        target_url,
                        json=body,
                        headers={"Content-Type": "application/json"},
                        timeout=120.0,
                    )
                    response_data = resp.json()
            except Exception as e:
                if execution:
                    self._interceptor.fail(execution.execution_id, str(e))
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": str(e)},
                        "id": body.get("id"),
                    },
                    status_code=502,
                )

            # Complete interception
            if execution:
                try:
                    self._interceptor.complete(execution.execution_id, response_data)
                except Exception as e:
                    logger.error(
                        "Failed to record execution %s: %s",
                        execution.execution_id,
                        e,
                    )

            return JSONResponse(content=response_data)

        @app.get("/gateway/status")
        async def gateway_status():
            return JSONResponse(content=self._state.to_dict())

        @app.get("/gateway/executions")
        async def gateway_executions():
            return JSONResponse(content=self._interceptor.list_executions())

        # Parse host/port from target if needed
        host = "0.0.0.0"
        port = 8765

        logger.info("Starting HTTP proxy on %s:%d → %s", host, port, target_url)
        uvicorn.run(app, host=host, port=port, log_level="info")
