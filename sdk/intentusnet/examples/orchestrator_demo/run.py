# examples/orchestrator_demo/run.py

"""
Run the full orchestrator demo.

Agents:
- orchestrator-agent
- summarizer-agent
- classifier-agent
- primary-storage-agent
- fallback-storage-agent
- secure-storage-agent
- notification-agent
- logger-agent
"""

from intentusnet import IntentusRuntime
from intentusnet.emcl.simple_hmac import SimpleHMACEMCLProvider

from examples.orchestrator_demo.agents.summarizer import create_summarizer_agent
from examples.orchestrator_demo.agents.classifier import create_classifier_agent
from examples.orchestrator_demo.agents.primary_storage import create_primary_storage_agent
from examples.orchestrator_demo.agents.fallback_storage import create_fallback_storage_agent
from examples.orchestrator_demo.agents.secure_storage import create_secure_storage_agent
from examples.orchestrator_demo.agents.notification import create_notification_agent
from examples.orchestrator_demo.agents.logger import create_logger_agent
from examples.orchestrator_demo.agents.orchestrator import create_orchestrator_agent


def main():
    # Configure EMCL (optional but recommended)
    emcl = SimpleHMACEMCLProvider(key="super-secret-demo-key")

    runtime = IntentusRuntime(emcl_provider=emcl)

    # Register agents
    runtime.register_agent(create_summarizer_agent)
    runtime.register_agent(create_classifier_agent)
    runtime.register_agent(create_primary_storage_agent)
    runtime.register_agent(create_fallback_storage_agent)
    runtime.register_agent(create_secure_storage_agent)
    runtime.register_agent(create_notification_agent)
    runtime.register_agent(create_logger_agent)
    runtime.register_agent(create_orchestrator_agent)

    client = runtime.client()

    # Example document
    document = """
    This is a demo document for IntentusNet.
    It shows how an orchestrator agent can coordinate multiple tools:
    summarization, classification, storage, secure metadata vault,
    notifications, and logging — all as separate agents.
    """

    print("=== Running orchestrator demo ===")
    resp = client.send(
        "processDocument",
        {
            "document": document,
            "documentId": "demo-123",
            "user": "balachandar@example.com",
        },
    )

    print("\n=== Orchestrator Response ===")
    print(resp.status)
    print(resp.payload)


if __name__ == "__main__":
    main()
