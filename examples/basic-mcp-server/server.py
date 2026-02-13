"""
Basic MCP Server Example for IntentusNet Gateway.

A minimal HTTP MCP-style server with a deterministic `add(a, b)` tool.
Used to demonstrate the IntentusNet Deterministic MCP Gateway.

Usage:
    python server.py

Then wrap with the IntentusNet gateway:
    intentusnet gateway --http http://localhost:5123

Requirements:
    pip install intentusnet   (includes fastapi + uvicorn)
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler


class MCPHandler(BaseHTTPRequestHandler):
    """Minimal MCP-style JSON-RPC handler."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "Invalid JSON"})
            return

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            self._jsonrpc_response(req_id, {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "basic-math-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            })

        elif method == "tools/list":
            self._jsonrpc_response(req_id, {
                "tools": [
                    {
                        "name": "add",
                        "description": "Add two numbers together. Deterministic.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "number", "description": "First number"},
                                "b": {"type": "number", "description": "Second number"},
                            },
                            "required": ["a", "b"],
                        },
                    }
                ]
            })

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "add":
                a = arguments.get("a", 0)
                b = arguments.get("b", 0)
                result = a + b
                self._jsonrpc_response(req_id, {
                    "content": [
                        {"type": "text", "text": f"{a} + {b} = {result}"}
                    ]
                })
            else:
                self._jsonrpc_error(req_id, -32601, f"Unknown tool: {tool_name}")

        else:
            self._jsonrpc_error(req_id, -32601, f"Unknown method: {method}")

    def _jsonrpc_response(self, req_id, result):
        response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        self._respond(200, response)

    def _jsonrpc_error(self, req_id, code, message):
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
        self._respond(200, response)

    def _respond(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[MCP Server] {args[0]}")


def main():
    port = 5123
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    server = HTTPServer(("0.0.0.0", port), MCPHandler)
    print(f"Basic MCP server running on http://localhost:{port}")
    print(f"Tools available: add(a, b)")
    print(f"Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
