from __future__ import annotations

from intentusnet.core.runtime import IntentusRuntime

from ..with_intentusnet.agents.search_agents import LocalSearchAgent, SummarizeAgent
from ..with_intentusnet.agents.flow_agent import SearchAndSummarizeFlowAgent
from .mcp_transport_agent import MCPBackedSearchAgent
from ..shared.trace_printer import print_intentus_trace

def _register(runtime: IntentusRuntime) -> None:
    runtime.register_agent(LocalSearchAgent)
    runtime.register_agent(MCPBackedSearchAgent)
    runtime.register_agent(SummarizeAgent)
    runtime.register_agent(SearchAndSummarizeFlowAgent)

def run_with_intentusnet_mcp(*, query: str) -> None:
    runtime = IntentusRuntime()
    _register(runtime)

    client = runtime.client()
    resp = client.send_intent("SearchAndSummarizeIntent", {"query": query})

    print("\nWITH IntentusNet (MCP-backed remote search)")
    if resp.error:
        print("error:", resp.error)
    else:
        print("result:", resp.payload)

    print_intentus_trace(runtime)
