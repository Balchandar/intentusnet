# Execution Recorder & Replay — Demo

## Executive Summary

This demo validates a foundational reliability guarantee for AI systems:

> **The model may change.  
> The execution must not.**

IntentusNet enforces this guarantee by treating AI executions as **immutable facts**.
Executions are recorded, replayed, and explained independently of model evolution.

This is **not** observability, debugging, or monitoring.
It is **execution correctness infrastructure**.

---

## The Problem This Solves

In most AI-powered systems today:

- Model upgrades silently change behavior
- Past decisions cannot be reproduced
- Failures are lost once models change
- Root-cause analysis becomes speculative
- Audit and compliance are unreliable

Logs and traces are insufficient.
They describe _what happened_, but they cannot **replay the execution itself**.

---

## IntentusNet’s Approach

IntentusNet makes **executions first-class artifacts**.

| Traditional AI Systems      | IntentusNet            |
| --------------------------- | ---------------------- |
| Model-centric               | Execution-centric      |
| Logs & traces               | Execution records      |
| Best-effort reproducibility | Deterministic replay   |
| Implicit workflows          | Explicit orchestration |
| History mutates with models | History is immutable   |

The execution record is the source of truth.

---

## Demo Scope (Intentional)

This demo proves **one invariant only**:

> **Model upgrades must not invalidate past executions.**

It intentionally does **not** demonstrate:

- learning or training
- heuristics or prediction
- observability dashboards
- debugging UIs
- distributed tracing

The scope is deliberately narrow to keep the guarantee precise and defensible.

---

## High-Level Scenario

A user submits a support ticket:

```
"Payment failed with error 402"
```

The system processes this request through a **multi-agent workflow**:

1. Analyze the ticket
2. Classify the issue
3. Route to a specialist
4. Produce a final decision

All execution happens inside IntentusNet with recording enabled.

---

## Execution Boundary

The external caller invokes a single intent:

```
support.ticket.analyze
```

This intent defines the **execution boundary**.

IntentusNet records **executions**, not implicit workflows.

---

## Why a Coordinator Agent Exists

A Coordinator Agent handles `support.ticket.analyze` and explicitly orchestrates
the workflow.

This avoids:

- abusing routing priority as a pipeline
- hidden control flow
- non-deterministic execution paths

Workflow composition is explicit, readable, and reviewable.

---

## Agents Involved

| Agent                  | Responsibility                     | Intent                  |
| ---------------------- | ---------------------------------- | ----------------------- |
| TicketCoordinatorAgent | Workflow orchestration             | support.ticket.analyze  |
| ClassifierAgent        | Ticket classification              | support.ticket.classify |
| PaymentExpertAgent     | Payment decision (model-dependent) | support.ticket.payment  |
| AccountExpertAgent     | Account issues                     | support.ticket.account  |
| FraudDetectionAgent    | Fraud analysis                     | support.ticket.fraud    |
| HumanFallbackAgent     | Manual escalation                  | support.ticket.escalate |

Each agent execution is:

- atomic
- deterministic
- independently replayable

---

## Execution Recording Model

Every intent execution produces an **ExecutionRecord** containing:

- Original intent envelope
- Deterministic routing decision
- Ordered execution events
- Agent inputs and outputs
- Final response
- Immutable timestamps
- Envelope hash
- Replayability flag

Records are stored locally as JSON files.

No external interception.
No global hooks.
No hidden state.

---

## Demo Walkthrough

### 1. Live Execution — Model v1

```bash
python run_live_success_v1.py
```

Output:

```json
{
  "workflow": "support.ticket.analyze",
  "category": "payment",
  "selectedAgent": "payment-expert-agent",
  "result": {
    "agent": "payment-expert",
    "modelVersion": "v1",
    "decision": "Retry payment (provider transient failure)"
  }
}
```

This execution is recorded.

---

### 2. Model Upgrade — v2

Without changing routing or orchestration:

```bash
python run_live_success_v2.py
```

Output:

```json
{
  "workflow": "support.ticket.analyze",
  "category": "payment",
  "selectedAgent": "payment-expert-agent",
  "result": {
    "agent": "payment-expert",
    "modelVersion": "v2",
    "decision": "Insufficient funds — ask customer to use another card"
  }
}
```

- Same execution path
- Same agent selection
- Different model behavior

---

### 3. Replay the Latest Execution

```bash
python replay_execution.py
```

Output:

```json
Replayed response: {
  "workflow": "support.ticket.analyze",
  "category": "payment",
  "selectedAgent": "payment-expert-agent",
  "result": {
    "agent": "payment-expert",
    "modelVersion": "v1",
    "decision": "Retry payment (provider transient failure)"
  }
}
Envelope hash match: True
```

Replay guarantees:

- Routing is NOT recomputed
- Models are NOT executed
- Recorded outputs are returned verbatim
- Execution integrity is verified via hash

---

## Execution vs Workflow

IntentusNet records **executions**, not implicit workflows.

- The coordinator execution defines the workflow boundary
- Internal steps remain separate executions
- Replay targets the same intent boundary the user invoked

This keeps execution records:

- atomic
- deterministic
- explainable

---

## Replay Semantics

Replay defaults to:

- the most recent execution
- matching the same intent boundary

This aligns with developer expectations:

> “Replay what just happened.”

---

## What This Demo Is Not

- Not a debugger
- Not a monitoring system
- Not model-specific
- Not heuristic-driven
- Not probabilistic

This is a **reliability primitive**, not an analytics tool.

---

## Strategic Value

This capability enables:

- Regulatory auditability
- Incident reconstruction
- Safe model iteration
- Deterministic agent systems
- Long-lived AI systems with historical integrity

---

## Core Principle

> **The model may change.  
> The execution must not.**
