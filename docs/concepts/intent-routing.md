# Intent Routing (IntentusNet v1)

This document explains what **intent routing** means in IntentusNet v1 and how it works at a conceptual level.

It describes _what happens_ when an intent is sent into the system, without focusing on specific routing strategies or transport details.

---

## What Is an Intent

An intent represents a **unit of work** expressed declaratively.

An intent consists of:

- A name (e.g., `SearchIntent`)
- A version (v1 uses `"1.0"`)
- A payload describing input data

Intents describe _what should be done_, not _how it should be done_.

---

## What Is Intent Routing

Intent routing is the process of:

1. Receiving an intent
2. Identifying agents capable of handling it
3. Selecting one or more agents deterministically
4. Executing agent logic
5. Returning a single response

Routing is synchronous and bounded in v1.

---

## Routing Responsibilities

In IntentusNet v1, routing is responsible for:

- Capability-based agent selection
- Deterministic ordering
- Strategy-based execution (direct, fallback, etc.)
- Error normalization
- Trace emission

Routing does **not** include:

- Scheduling
- Persistence
- Retry logic
- Policy enforcement

---

## Capability-Based Matching

Agents declare which intents they support via **capabilities**.

During routing:

- The router queries the registry
- All agents matching the intent name and version are collected
- No filtering beyond declared capability occurs

If no agents match, routing fails immediately.

---

## Routing Is Explicit

All routing behavior is driven by data in the intent envelope:

- Intent name and version
- Routing options (strategy, target agent)
- Registered agent definitions

There are no implicit defaults beyond documented behavior.

---

## Single Entry Point

All intents enter the system through a single logical entry point:

```text
Intent → Transport → Router → Agent → Router → Response
```

This makes routing:

- Observable
- Testable
- Predictable

---

## One Response Guarantee

For each routed intent:

- Exactly one `AgentResponse` is returned
- Either success or error
- No partial or streaming responses exist

This guarantee holds across all routing strategies.

---

## Intent Chaining

Agents may emit additional intents during execution.

Each emitted intent:

- Starts a new routing cycle
- Is routed independently
- Produces its own response

There is no implicit workflow or transaction boundary in v1.

---

## Determinism and Routing

Intent routing is deterministic:

- Agent selection order is stable
- Fallback paths are predictable
- Errors follow the same resolution path

This is a foundational design property.

---

## What Intent Routing Is Not

Intent routing is not:

- A workflow engine
- A job queue
- A message bus
- A scheduler
- A distributed system coordinator

It is a **routing mechanism**, nothing more.

---

## Design Rationale

Intent routing is intentionally simple to:

- Keep behavior understandable
- Avoid hidden execution paths
- Enable safe composition by host applications

Complex orchestration belongs outside the router.

---

## Summary

In IntentusNet v1, intent routing is:

- Explicit
- Deterministic
- Synchronous
- Capability-driven

It provides a clear and reliable mechanism for dispatching intent-based work.
