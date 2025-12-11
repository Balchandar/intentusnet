# FILE: examples/advanced/demo_advanced_research.py

from __future__ import annotations
import json
from intentusnet.core.runtime import IntentusRuntime
from intentusnet.core.tracing import IntentusNetTracer
from intentusnet.protocol.models import IntentRef

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


def ask_user(prompt):
    return input(prompt).strip()

def register_all(runtime: IntentusRuntime):
# REGISTER EXECUTION AGENTS FIRST
    runtime.register_agent(WebSearchAgent)
    runtime.register_agent(AltSearchAgent)
    runtime.register_agent(ScraperAgent)
    runtime.register_agent(CleanerAgent)
    runtime.register_agent(SummarizerAgent)
    runtime.register_agent(ReasoningAgent)
    runtime.register_agent(ActionAgent)

    # REGISTER ORCHESTRATORS
    runtime.register_agent(ResearchOrchestratorAgent)
    runtime.register_agent(ComparisonOrchestratorAgent)

    # REGISTER NLU LAST (IMPORTANT)
    runtime.register_agent(NLUAgent)



def run_demo():
    runtime = IntentusRuntime()
    
    register_all(runtime)

    client = runtime.client()

    print("=== IntentusNet Advanced Demo ===")

    while True:
        print("\n1. Research a topic")
        print("2. Compare two topics")
        print("3. Deep-dive research")
        print("4. Show trace log")
        print("5. Exit")

        choice = ask_user("> ")

        if choice == "1":
            text = ask_user("Enter topic: ")

            # ---- Stage 1: NLU ----
            nlu_resp = client.send_intent("ParseIntent", {"query": text})
            if nlu_resp.status == "error":
                print("NLU error:", nlu_resp.error.message)
                continue

            predicted_intent = nlu_resp.payload["intent"]
            arguments = nlu_resp.payload.get("arguments", {})

            print("\nNLU → Predicted intent:", predicted_intent)
            
            # ---- Stage 2: Execute ResearchIntent ----
            resp = client.send_intent(predicted_intent, arguments)

            print("\n==== RESULT ====")
            print(resp.payload)

        elif choice == "2":
            t1 = ask_user("Topic A: ")
            t2 = ask_user("Topic B: ")
            nlu_resp = client.send_intent("ParseIntent", {"query": f"compare {t1} and {t2}"})
            predicted = nlu_resp.payload["intent"]
            args = nlu_resp.payload.get("arguments", {})
            print(predicted)
            resp = client.send_intent(predicted, args)
            print("\n==== RESULT ====")
            print(resp.payload)

        elif choice == "3":
            topic = ask_user("Deep dive into: ")

            nlu_resp = client.send_intent("ParseIntent", {"query": topic})
            predicted = nlu_resp.payload["intent"]
            args = nlu_resp.payload.get("arguments", {})
            print(predicted)
            resp = client.send_intent(predicted, args)
            print("\n==== RESULT ====")
            print(resp.payload)

        elif choice == "4":
            print("\n=== TRACE LOG ===")
            for span in runtime.trace_sink.export():
                print(
                    f"{span.agent:20} {span.intent:20} "
                    f"{span.latencyMs:8}ms  {span.status}"
                )

        elif choice == "5":
            break
        else:
            print("Invalid choice!")


if __name__ == "__main__":
    run_demo()
