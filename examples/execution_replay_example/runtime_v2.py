from intentusnet.core.runtime import IntentusRuntime
from intentusnet.protocol.agent import AgentDefinition, Capability
from intentusnet.protocol.intent import IntentRef

from agents import (
    TicketCoordinatorAgent,
    ClassifierAgent,
    PaymentExpertAgent,
    AccountExpertAgent,
    FraudDetectionAgent,
    HumanFallbackAgent,
)


def create_runtime_v2():
    runtime = IntentusRuntime(
        enable_recording=True,
        record_dir="examples/execution_replay_example/records",
    )

    analyze = IntentRef(name="support.ticket.analyze")
    classify = IntentRef(name="support.ticket.classify")
    payment = IntentRef(name="support.ticket.payment")
    account = IntentRef(name="support.ticket.account")
    fraud = IntentRef(name="support.ticket.fraud")
    escalate = IntentRef(name="support.ticket.escalate")

    runtime.register_agent(
        lambda r: TicketCoordinatorAgent(
            AgentDefinition(name="ticket-coordinator-agent", nodePriority=0, capabilities=[Capability(intent=analyze)]),
            r,
        )
    )

    runtime.register_agent(
        lambda r: ClassifierAgent(
            AgentDefinition(name="classifier-agent", nodePriority=0, capabilities=[Capability(intent=classify)]),
            r,
        )
    )

    runtime.register_agent(
        lambda r: PaymentExpertAgent(
            AgentDefinition(name="payment-expert-agent", nodePriority=0, capabilities=[Capability(intent=payment)]),
            r,
            model_version="v2",
        )
    )

    runtime.register_agent(
        lambda r: AccountExpertAgent(
            AgentDefinition(name="account-expert-agent", nodePriority=0, capabilities=[Capability(intent=account)]),
            r,
        )
    )

    runtime.register_agent(
        lambda r: FraudDetectionAgent(
            AgentDefinition(name="fraud-detection-agent", nodePriority=0, capabilities=[Capability(intent=fraud)]),
            r,
        )
    )

    runtime.register_agent(
        lambda r: HumanFallbackAgent(
            AgentDefinition(name="human-fallback-agent", nodePriority=0, capabilities=[Capability(intent=escalate)]),
            r,
        )
    )

    return runtime
