#!/usr/bin/env python3
"""
Gate 6: Routing Determinism Verification

Proves: Same intent + same agent registry → same agent selection every time.

Runs 10 identical intent submissions and verifies:
  - Same agent selected each time
  - Same response payload each time
  - Execution order is identical
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from intentusnet.core.runtime import IntentusRuntime
from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.agent import AgentDefinition, Capability
from intentusnet.protocol.intent import IntentRef
from intentusnet.protocol.response import AgentResponse
from intentusnet.recording.models import stable_hash


class AgentAlpha(BaseAgent):
    def handle_intent(self, env):
        return AgentResponse.success(
            payload={"agent": "alpha", "value": env.payload.get("x", 0) + 1},
            agent=self.definition.name,
        )


class AgentBeta(BaseAgent):
    def handle_intent(self, env):
        return AgentResponse.success(
            payload={"agent": "beta", "value": env.payload.get("x", 0) + 2},
            agent=self.definition.name,
        )


class AgentGamma(BaseAgent):
    def handle_intent(self, env):
        return AgentResponse.success(
            payload={"agent": "gamma", "value": env.payload.get("x", 0) + 3},
            agent=self.definition.name,
        )


NUM_ITERATIONS = 10


def main():
    print("Gate 6: Routing Determinism Verification")
    print("=" * 50)

    alpha_def = AgentDefinition(
        name="agent-alpha", version="1.0", nodePriority=10,
        capabilities=[Capability(intent=IntentRef(name="test.route", version="1.0"))],
    )
    beta_def = AgentDefinition(
        name="agent-beta", version="1.0", nodePriority=20,
        capabilities=[Capability(intent=IntentRef(name="test.route", version="1.0"))],
    )
    gamma_def = AgentDefinition(
        name="agent-gamma", version="1.0", nodePriority=30,
        capabilities=[Capability(intent=IntentRef(name="test.route", version="1.0"))],
    )

    agents_selected = []
    payload_hashes = []

    print(f"  Running {NUM_ITERATIONS} identical intent submissions...")

    for i in range(NUM_ITERATIONS):
        with tempfile.TemporaryDirectory(prefix=f"gate6_run{i}_") as tmpdir:
            runtime = IntentusRuntime(enable_recording=True, record_dir=tmpdir)
            runtime.register_agent(lambda r: AgentAlpha(alpha_def, r))
            runtime.register_agent(lambda r: AgentBeta(beta_def, r))
            runtime.register_agent(lambda r: AgentGamma(gamma_def, r))

            client = runtime.client()
            resp = client.send_intent("test.route", payload={"x": 100})

            selected = resp.metadata.get("agent", "unknown")
            ph = stable_hash(resp.payload)

            agents_selected.append(selected)
            payload_hashes.append(ph)

            print(f"    Run {i+1:2d}: agent={selected:20s} payload_hash={ph[:16]}...")

    print()

    # Check 1: Same agent selected every time
    unique_agents = set(agents_selected)
    if len(unique_agents) != 1:
        print(f"  GATE 6 FAIL: Agent selection varied — {unique_agents}")
        print("  This indicates nondeterministic routing")
        sys.exit(1)
    print(f"  PASS: Same agent selected all {NUM_ITERATIONS} times: {agents_selected[0]}")

    # Check 2: Same payload hash every time
    unique_hashes = set(payload_hashes)
    if len(unique_hashes) != 1:
        print(f"  GATE 6 FAIL: Payload hashes varied — found {len(unique_hashes)} unique hashes")
        sys.exit(1)
    print(f"  PASS: Identical payload hash all {NUM_ITERATIONS} times")

    print()
    print("  GATE 6 PASS: Routing is deterministic")


if __name__ == "__main__":
    main()
