# intentusnet/cli.py

"""
IntentusNet CLI Tool
--------------------

Provides:
  - Agent discovery
  - Sending intents from command line
  - Running orchestrator demo
"""

from __future__ import annotations
import argparse
import json
import sys
from typing import Any, Dict

from intentusnet import IntentusRuntime
from intentusnet.emcl.simple_hmac import SimpleHMACEMCLProvider


# Optional: load demo agents dynamically
try:
    from intentusnet.examples.orchestrator_demo.agents.summarizer import create_summarizer_agent
    from intentusnet.examples.orchestrator_demo.agents.classifier import create_classifier_agent
    from intentusnet.examples.orchestrator_demo.agents.primary_storage import create_primary_storage_agent
    from intentusnet.examples.orchestrator_demo.agents.fallback_storage import create_fallback_storage_agent
    from intentusnet.examples.orchestrator_demo.agents.secure_storage import create_secure_storage_agent
    from intentusnet.examples.orchestrator_demo.agents.notification import create_notification_agent
    from intentusnet.examples.orchestrator_demo.agents.logger import create_logger_agent
    from intentusnet.examples.orchestrator_demo.agents.orchestrator import create_orchestrator_agent

    DEMO_AVAILABLE = True
except Exception:
    DEMO_AVAILABLE = False


def _parse_json(payload_str: str) -> Dict[str, Any]:
    try:
        return json.loads(payload_str)
    except Exception as e:
        print(f"Invalid JSON payload: {e}")
        sys.exit(1)


def cmd_agents_list(args):
    """
    Lists all agents currently registered in the runtime.
    """
    runtime = IntentusRuntime()
    
    # Only runtime, no agents by default
    agents = runtime.registry.all_agents()

    if not agents:
        print("No agents registered.")
        return

    print("\nRegistered Agents:")
    print("------------------")
    for a in agents:
        print(f"- {a.definition.name}  ({len(a.definition.capabilities)} capabilities)")
    print()


def cmd_send(args):
    """
    Sends an intent with payload using InProcess transport.
    """

    payload = _parse_json(args.payload)

    runtime = IntentusRuntime()
    # User still must register agents in their actual app
    client = runtime.client()

    print(f"\nSending intent: {args.intent}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    resp = client.send(args.intent, payload)

    print("\nResponse:")
    print("---------")
    print(json.dumps(resp.__dict__, indent=2, default=str))


def cmd_run_demo(args):
    """
    Runs the Orchestrator Demo end-to-end.
    """
    if not DEMO_AVAILABLE:
        print("Demo agents not available in this installation.")
        return

    print("Starting Orchestrator Demo...")

    emcl = SimpleHMACEMCLProvider(key="demo-key")
    runtime = IntentusRuntime(emcl_provider=emcl)

    # Register all demo agents
    runtime.register_agent(create_summarizer_agent)
    runtime.register_agent(create_classifier_agent)
    runtime.register_agent(create_primary_storage_agent)
    runtime.register_agent(create_fallback_storage_agent)
    runtime.register_agent(create_secure_storage_agent)
    runtime.register_agent(create_notification_agent)
    runtime.register_agent(create_logger_agent)
    runtime.register_agent(create_orchestrator_agent)

    client = runtime.client()

    demo_doc = """
    This is a demo document processed through IntentusNet Orchestrator.
    It showcases summarization, classification, storage, secure metadata,
    notifications, and workflow logging.
    """

    resp = client.send(
        "processDocument",
        {
            "document": demo_doc,
            "documentId": "cli-demo-123",
            "user": "cli-user@example.com",
        },
    )

    print("\n=== Final Orchestrator Result ===")
    print(json.dumps(resp.payload, indent=2))



def main():
    parser = argparse.ArgumentParser(
        prog="intentusctl",
        description="IntentusNet Command Line Tool"
    )
    sub = parser.add_subparsers(dest="command")

    # agents list
    p_list = sub.add_parser("agents", help="Interact with agents")
    sub_list = p_list.add_subparsers(dest="agents_cmd")
    p_list_list = sub_list.add_parser("list", help="List registered agents")
    p_list_list.set_defaults(func=cmd_agents_list)

    # send intent
    p_send = sub.add_parser("send", help="Send an intent to the runtime")
    p_send.add_argument("--intent", required=True, help="Intent name")
    p_send.add_argument("--payload", required=True, help="JSON payload string")
    p_send.set_defaults(func=cmd_send)

    # demo
    p_demo = sub.add_parser("run-demo", help="Run orchestrator demo")
    p_demo.add_argument("demo_name", choices=["orchestrator"], help="Demo to run")
    p_demo.set_defaults(func=cmd_run_demo)

    # Parse + dispatch
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
