# examples/advanced/mcp_demo.py

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.adapters.mcp_adapter import MCPAdapter
from examples.advanced.demo_advanced_research import register_all

runtime = IntentusRuntime()
register_all(runtime)

adapter = MCPAdapter(runtime.router)

result = adapter.handle_mcp_request({
    "name": "ResearchIntent",
    "arguments": {"topic": "Quantum Computing"}
})

print("MCP Output:", result)
