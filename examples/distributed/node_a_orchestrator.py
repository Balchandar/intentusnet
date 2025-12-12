from __future__ import annotations

"""
Node A — Orchestrator node

This node:
  - Has local agents (e.g., summarizer, orchestrator)
  - Adds a RemoteAgentProxy for WebSearchAgent hosted on Node B
  - Uses HTTPRemoteAgentTransport to call Node B securely
"""

import uvicorn

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.routing import Routing
from intentusnet.transport.http_remote import HTTPRemoteAgentTransport
from intentusnet.core.remote_agent import RemoteAgentProxy
from intentusnet.security.node_identity import NodeIdentity, NodeSigner
from .node_execution import app as gw_app  # reused HTTP server for demo


# -------------------------------------------------------------------
# Setup Node A runtime
# -------------------------------------------------------------------
runtime = IntentusRuntime()

# Node A identity for signing outbound frames
NODE_A_IDENTITY = NodeIdentity(
    nodeId="node-a",
    sharedSecret="super-secret"
)
node_signer = NodeSigner(NODE_A_IDENTITY)

# Transport for calling Node B's WebSearchAgent
remote_transport = HTTPRemoteAgentTransport(
    base_url="http://localhost:8001",
    agent_name="web-search-agent",
    node_signer=node_signer,   # <-- node-to-node HMAC signing
)

# Register proxy - router thinks this is just an agent
proxy = RemoteAgentProxy(
    router=runtime.router,
    agent_name="web-search-agent",
    node_id="node-b",
    transport=remote_transport,
)
runtime.registry.register(proxy)

# Reuse the simple FastAPI web_server for interactive testing
app = gw_app


# -------------------------------------------------------------------
# Test API: Try calling remote agent
# -------------------------------------------------------------------
@app.get("/test-remote")
def test_remote():
    env = IntentEnvelope(
        intent={"name": "WebSearchIntent", "version": "1.0"},
        payload={"query": "OpenAI GPT"},
        routing=Routing(strategy="DIRECT", targetAgent="web-search-agent"),
    )

    resp = runtime.router.route_intent(env)
    return {"result": resp.payload, "error": resp.error}


# -------------------------------------------------------------------
# Run server
# -------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "node_a_orchestrator:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
