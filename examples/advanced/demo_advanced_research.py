from __future__ import annotations

import sys
from typing import Any, Dict

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.core.client import IntentusClient

# Import agents
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



def register_all(runtime: IntentusRuntime):
    """Register all agents required by the advanced demo."""
    runtime.register_agent(lambda router: NLUAgent(router))
    runtime.register_agent(lambda router: WebSearchAgent(router))
    runtime.register_agent(lambda router: AltSearchAgent(router))
    runtime.register_agent(lambda router: ScraperAgent(router))
    runtime.register_agent(lambda router: CleanerAgent(router))
    runtime.register_agent(lambda router: SummarizerAgent(router))
    runtime.register_agent(lambda router: ReasoningAgent(router))
    runtime.register_agent(lambda router: ActionAgent(router))

    # Orchestrators
    runtime.register_agent(lambda router: ResearchOrchestratorAgent(router))
    runtime.register_agent(lambda router: ComparisonOrchestratorAgent(router))


def print_trace(runtime: IntentusRuntime):
    spans = runtime.trace_sink.get_spans()
    print("\n=== TRACE LOG ===")
    print(f"{'Agent':20} {'Intent':20} {'Latency(ms)':12} {'Status':10} {'Error'}")
    for span in spans:
        err = span.error or ""
        print(
            f"{span.agent:20} {span.intent:20} {span.latencyMs:12.2f} "
            f"{span.status:10} {err}"
        )
    print("\n")


def run_demo():
    runtime = IntentusRuntime()
    register_all(runtime)

    client: IntentusClient = runtime.client()

    print("=== IntentusNet Advanced Research Demo ===")

    while True:
        print(
            "\nMenu:\n"
            "1. Research a topic\n"
            "2. Compare two topics\n"
            "3. Show trace log\n"
            "4. Exit\n"
        )
        choice = input("> ").strip()

        if choice == "1":
            topic = input("Enter topic: ").strip()
            response = client.send_intent("ResearchIntent", {"topic": topic})
            print("\n==== RESULT ====")
            print(response.payload)

        elif choice == "2":
            a = input("Enter first topic: ").strip()
            b = input("Enter second topic: ").strip()
            response = client.send_intent("CompareIntent", {"a": a, "b": b})
            print("\n==== RESULT ====")
            print(response.payload)

        elif choice == "3":
            print_trace(runtime)

        elif choice == "4":
            print("Goodbye!")
            sys.exit(0)

        else:
            print("Invalid option.")

if __name__ == "__main__":
    run_demo()
