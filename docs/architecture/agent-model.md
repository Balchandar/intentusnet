# Agent Model (IntentusNet v1)

This document describes the **agent programming model** used in IntentusNet v1.
It is a factual reference aligned exactly with the `BaseAgent` implementation.

Agents are **synchronous, in-memory components** that execute business logic for a given intent.

---

## What an Agent Is

An agent is:

- A Python class extending `BaseAgent`
- Registered explicitly with the runtime
- Invoked synchronously by the router
- Responsible for handling one or more intents

Agents are **not** services, workers, or processes.
They execute inside the host application runtime.

---

## BaseAgent Contract

All agents must extend the abstract base class:

```python
class BaseAgent(ABC):
    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        ...
```

The router never calls `handle_intent` directly.
It always calls the router-facing entrypoint `handle()`.

---

## Router-Facing Execution (`handle`)

The router invokes:

```python
agent.handle(env: IntentEnvelope) -> AgentResponse
```

Responsibilities handled automatically by `BaseAgent.handle`:

- Ensure a `traceId` exists
- Append agent name to `routingMetadata.decisionPath`
- Catch unhandled exceptions
- Normalize failures into `AgentResponse`
- Populate response metadata

Agents **must not override** this method.

---

## Business Logic (`handle_intent`)

Agent-specific logic is implemented in:

```python
def handle_intent(self, env: IntentEnvelope) -> AgentResponse
```

Rules:

- Must be synchronous
- Must return an `AgentResponse`
- Must not raise exceptions (they are caught, but discouraged)

Any exception thrown is converted into:

- `INTERNAL_AGENT_ERROR`

---

## Agent Definition

Each agent is constructed with an `AgentDefinition`.

The definition declares:

- Agent name
- Supported intents (capabilities)
- Optional node metadata (nodeId, nodePriority)

The router relies entirely on the definition for routing decisions.

---

## Emitting Downstream Intents

Agents may emit additional intents using:

```python
self.emit_intent(intent_name, payload, ...)
```

Behavior:

- A new `IntentEnvelope` is created
- A new `traceId` is generated
- Routing starts from the router again
- Execution is synchronous

There is **no implicit parent-child span tracking** in v1.

---

## Context and Metadata Handling

Agents receive a full `IntentEnvelope` containing:

- `intent`: intent name and version
- `payload`: input data
- `context`: execution context
- `metadata`: tracing and request identifiers
- `routing`: routing instructions
- `routingMetadata`: routing history

Agents may read from these fields.
They should **not mutate routing semantics**.

---

## Error Creation Helper

Agents can construct structured errors using:

```python
self.error("message", code=..., retryable=...)
```

This produces an `ErrorInfo` object that can be returned inside `AgentResponse`.

Agents should prefer structured errors over exceptions.

---

## Threading and Concurrency

In v1:

- Agents are assumed to be **thread-safe**
- No locking or synchronization is provided
- Parallel routing executes agents concurrently

Agents should avoid:

- Mutating shared global state
- Relying on execution order

---

## What Agents Must Not Do

Agents must not:

- Block indefinitely
- Spawn background threads
- Persist state implicitly
- Depend on retry behavior
- Assume transport-level guarantees

These concerns belong outside IntentusNet.

---

## Summary

In IntentusNet v1, agents are:

- Explicit
- Synchronous
- Deterministic
- In-process

They are designed to be simple, testable units of intent-handling logic,
not distributed services.
