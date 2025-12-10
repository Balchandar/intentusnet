from __future__ import annotations

import sys
from typing import Optional

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.transport.inprocess import InProcessTransport
from intentusnet.core.client import IntentusClient
from intentusnet.adapters.mcp_adapter import MCPAdapter
from intentusnet.security.emcl.simple_hmac import SimpleHMACEMCLProvider

from examples.advanced.agents.nlu_agent import NLUAgent
from examples.advanced.agents.research_orchestrator import ResearchOrchestratorAgent
from examples.advanced.agents.comparison_orchestrator import ComparisonOrchestratorAgent
from examples.advanced.agents.web_search_agent import WebSearchAgent
from examples.advanced.agents.alt_search_agent import AltSearchAgent
from examples.advanced.agents.scraper_agent import ScraperAgent
from examples.advanced.agents.cleaner_agent import CleanerAgent
from examples.advanced.agents.summarizer_agent import SummarizerAgent
from examples.advanced.agents.reasoning_agent import ReasoningAgent
from examples.advanced.agents.action_agent import ActionAgent


# ---------------------------------------------------------------------------
# Agent Registration
# ---------------------------------------------------------------------------

def register_all(runtime: IntentusRuntime) -> None:
    """
    Register all advanced demo agents into the runtime's registry.
    """
    registry = runtime.registry
    router = runtime.router

    registry.register(NLUAgent(router))
    registry.register(ResearchOrchestratorAgent(router))
    registry.register(ComparisonOrchestratorAgent(router))
    registry.register(WebSearchAgent(router))
    registry.register(AltSearchAgent(router))
    registry.register(ScraperAgent(router))
    registry.register(CleanerAgent(router))
    registry.register(SummarizerAgent(router))
    registry.register(ReasoningAgent(router))
    registry.register(ActionAgent(router))


# ---------------------------------------------------------------------------
# Trace Viewer
# ---------------------------------------------------------------------------

def show_trace(runtime: IntentusRuntime, trace_id: Optional[str] = None) -> None:
    tracer = runtime.tracer
    
    if tracer is None:
        print("\n(no tracer available)\n")
        return

    spans = tracer.get_spans()

    if trace_id:
        spans = [s for s in spans if s.traceId == trace_id]

    print("\n=== TRACE LOG ===")
    print(f"{'Agent':20} {'Start':24} {'End(ms)':24} {'Status':10}")
 
    for s in spans:
        status = ("Error" if s.attributes.get("error") else "Success") if s.attributes else ""
        agent = s.attributes.get("agent") if s.attributes else ""
        print(f"{agent:20} {s.startTime:24} {s.endTime:24} {status:10}")


# ---------------------------------------------------------------------------
# Workflows (via IntentusClient – Option B)
# ---------------------------------------------------------------------------

def workflow_research(client: IntentusClient, topic: str, runtime: IntentusRuntime) -> None:
    resp = client.send_intent("ResearchIntent", {"topic": topic})

    print("\n==== RESULT ====")
    if resp.error:
        print("Error:", getattr(resp.error, "message", resp.error))
    else:
        # Print full payload – orchestrator decides shape
        print(resp.payload)

    trace_id = None
    meta = getattr(resp, "metadata", None)
    if isinstance(meta, dict):
        trace_id = meta.get("traceId")
    show_trace(runtime, trace_id)


def workflow_compare(client: IntentusClient, topic_a: str, topic_b: str, runtime: IntentusRuntime) -> None:
    query = f"{topic_a} vs {topic_b}"
    resp = client.send_intent("ResearchIntent", {"topic": query})


    print("\n==== RESULT ====")
    if resp.error:
        print("Error:", getattr(resp.error, "message", resp.error))
    else:
        print(resp.payload)

    trace_id = None
    meta = getattr(resp, "metadata", None)
    if isinstance(meta, dict):
        trace_id = meta.get("traceId")
    show_trace(runtime, trace_id)


def workflow_deep_research(client: IntentusClient, topic: str, runtime: IntentusRuntime) -> None:
    query = f"deep {topic}"
    resp = client.send_intent("ResearchIntent", {"topic": query})


    print("\n==== RESULT ====")
    if resp.error:
        print("Error:", getattr(resp.error, "message", resp.error))
    else:
        print(resp.payload)

    trace_id = None
    meta = getattr(resp, "metadata", None)
    if isinstance(meta, dict):
        trace_id = meta.get("traceId")
    show_trace(runtime, trace_id)


# ---------------------------------------------------------------------------
# MCP + EMCL Demos
# ---------------------------------------------------------------------------

def run_mcp_demo(runtime: IntentusRuntime) -> None:
    """
    Minimal MCP-style demo: send a fake MCP tool call through MCPAdapter.
    """
    print("\n=== MCP DEMO ===")
    adapter = MCPAdapter(runtime.router)

    mcp_request = {
        "name": "ResearchIntent",
        "arguments": {"topic": "MCP protocol and agent runtimes"},
    }

    result = adapter.handle_mcp_request(mcp_request)
    print("MCP Response:")
    print(result)


def run_encrypted_http_demo() -> None:
    """
    Minimal EMCL demo – no real HTTP here, just show encrypt/decrypt flow.
    """
    print("\n=== ENCRYPTED HTTP DEMO ===")

    # Simple integrity-only provider for demo (string key, not bytes)
    provider = SimpleHMACEMCLProvider("super-secret-key-123")

    body = {
        "intent": "ResearchIntent",
        "payload": {"topic": "Cybersecurity for AI agents"},
    }

    encrypted = provider.encrypt(body)
    print("Encrypted envelope:", encrypted)

    decrypted = provider.decrypt(encrypted)
    print("Decrypted body:", decrypted)


# ---------------------------------------------------------------------------
# CLI UI (interactive when TTY is available)
# ---------------------------------------------------------------------------

def main() -> None:
    runtime = IntentusRuntime()
    register_all(runtime)

    # Use full transport → router → agent path
    transport = InProcessTransport(runtime.router)
    client = IntentusClient(transport)

    while True:
        print("\n=== IntentusNet Advanced Demo ===")
        print("1. Research a topic")
        print("2. Compare two topics")
        print("3. Deep-dive research")
        print("4. Show trace log (all spans)")
        print("5. Run MCP demo")
        print("6. Run encrypted HTTP demo")
        print("7. Exit")

        choice = input("> ").strip()

        if choice == "1":
            topic = input("Enter topic: ").strip()
            if topic:
                workflow_research(client, topic, runtime)

        elif choice == "2":
            a = input("Topic A: ").strip()
            b = input("Topic B: ").strip()
            if a and b:
                workflow_compare(client, a, b, runtime)

        elif choice == "3":
            topic = input("Deep topic: ").strip()
            if topic:
                workflow_deep_research(client, topic, runtime)

        elif choice == "4":
            # Show all spans collected so far
            show_trace(runtime, trace_id=None)

        elif choice == "5":
            run_mcp_demo(runtime)

        elif choice == "6":
            run_encrypted_http_demo()

        elif choice == "7":
            print("Bye.")
            sys.exit(0)

        else:
            print("Invalid choice")


if __name__ == "__main__":
    # Disable CLI when running in a non-interactive environment (e.g., docker-compose worker)
    if not sys.stdin.isatty():
        print("Non-interactive mode: CLI disabled.")
        sys.exit(0)

    main()
