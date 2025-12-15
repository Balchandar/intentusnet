# Runtime Overview (IntentusNet v1)

This document explains how the **IntentusNet runtime** is composed and what guarantees it provides in v1.

The runtime is intentionally minimal. It wires together core components but does **not** act as a framework,
platform, or lifecycle manager.

---

## What the Runtime Is

In IntentusNet v1, the runtime is a **convenience composition** that brings together:

- AgentRegistry
- IntentRouter
- Transport (in-process by default)
- Optional tracing sink
- Optional EMCL provider

Its purpose is to:

- Reduce boilerplate for local execution
- Provide a reference wiring for demos and examples
- Offer a predictable entry point for sending intents

The runtime does **not** introduce new behavior beyond what the router and agents already define.

---

## What the Runtime Is Not

The runtime does **not**:

- Manage agent lifecycles (start/stop/health)
- Perform dependency injection
- Handle retries or scheduling
- Provide persistence or state management
- Enforce authorization or policy
- Coordinate distributed execution

These concerns are intentionally left to the host application.

---

## Core Runtime Components

### AgentRegistry

The registry is responsible for:

- Holding agent instances
- Preventing duplicate agent registration
- Resolving candidate agents for a given intent

The runtime does not modify registry behavior. It simply exposes it as part of the composed runtime.

---

### IntentRouter

The router is the **core execution engine**.

Responsibilities:

- Deterministic agent selection
- Routing strategy execution
- Error normalization
- Trace capture
- Middleware invocation

The runtime configures the router with:

- A registry
- An optional trace sink
- Optional router middleware

All routing semantics are defined entirely inside the router.

---

### Transport (In-Process)

By default, the runtime uses an **in-process transport**:

- Client calls are forwarded directly to the router
- No serialization or network overhead exists
- Behavior matches remote transports semantically

This transport exists to:

- Provide a reference execution path
- Simplify demos and tests
- Establish a baseline for correctness

---

## Intent Flow Through the Runtime

At a high level, intent execution follows this path:

```mermaid
flowchart LR
    Client --> Transport
    Transport --> Router
    Router --> Agent
    Agent --> Router
    Router --> Client
```

Key points:

- The runtime does not alter the envelope
- The router owns execution semantics
- The client receives a single response

---

## Tracing Integration

The runtime optionally wires a `TraceSink` into the router.

In v1:

- Tracing is synchronous
- Exactly one trace span is emitted per intent
- Trace storage is in-memory by default

The runtime does not:

- Aggregate traces
- Export metrics
- Correlate across processes

These responsibilities belong to the host system.

---

## EMCL Integration

If an EMCL provider is supplied:

- Payload encryption/decryption occurs at transport boundaries
- The runtime does not inspect encrypted content
- Routing behavior remains unchanged

EMCL is optional and orthogonal to routing.

---

## Client Interaction

The runtime exposes a simple client interface:

```python
client = runtime.client()
client.send(intent_name, payload)
```

The client:

- Constructs a valid IntentEnvelope
- Delegates execution to the configured transport
- Does not cache or retry requests

---

## Design Constraints (Intentional)

The runtime is constrained to:

- In-memory execution
- Synchronous calls
- Explicit wiring

These constraints:

- Simplify reasoning
- Avoid hidden behavior
- Keep v1 stable and predictable

Advanced runtime behavior can be built **around** IntentusNet,
not inside it.

---

## Summary

IntentusNet v1 runtime is:

- Minimal
- Explicit
- Predictable
- Non-opinionated

It exists to make correct usage easy — not to abstract away system design decisions.
