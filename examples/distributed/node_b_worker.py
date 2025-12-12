from __future__ import annotations

"""
Node B — Remote Execution Node

This node:
  - Starts an IntentusRuntime
  - Registers one or more local agents
  - Exposes the NodeExecutionGateway (HTTP)
  - Validates node-to-node HMAC signatures
  - Executes agent logic
"""

import uvicorn
from fastapi import FastAPI

from intentusnet.core.runtime import IntentusRuntime
from ..advanced.agents.web_search_agent import WebSearchAgent
from intentusnet.security.node_identity import NodeIdentity
from intentusnet.security.emcl.aes_gcm import AESGCMProvider
from .node_execution import app as gateway_app   # reuse gateway file


# -------------------------------------------------------------------
# Create runtime for Node B
# -------------------------------------------------------------------

runtime = IntentusRuntime()

# Give Node B a stable identity
NODE_IDENTITY = NodeIdentity(
    nodeId="node-b",
    sharedSecret="super-secret"
)

# Optional: EMCL
EMCL_PROVIDER = AESGCMProvider("my-emcl-key-16bytes")

runtime.set_emcl_provider(EMCL_PROVIDER)

# Register agents that Node B can execute
runtime.registry.register(WebSearchAgent(runtime.router))

# Attach runtime to the gateway (simple pattern)
gateway_app.state.runtime = runtime
gateway_app.state.node_identity = NODE_IDENTITY
gateway_app.state.emcl_provider = EMCL_PROVIDER

app = gateway_app


# -------------------------------------------------------------------
# Run HTTP Server
# -------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "node_b_worker:app",
        host="0.0.0.0",
        port=8001,
        reload=False
    )
