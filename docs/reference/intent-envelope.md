# Intent Envelope (IntentusNet v1)

This document defines the **IntentEnvelope** structure used throughout IntentusNet v1.
It is a reference document and mirrors the protocol model exactly.

The intent envelope is the **unit of routing**. All routing decisions operate on this structure.

---

## Overview

An `IntentEnvelope` combines:

- Intent identity
- Input payload
- Execution context
- Routing instructions
- Routing metadata
- Tracing metadata

It is immutable in intent, but parts of its metadata may be appended during routing.

---

## IntentEnvelope Structure

```python
IntentEnvelope(
    version: str,
    intent: IntentRef,
    payload: Dict[str, Any],
    context: IntentContext,
    metadata: IntentMetadata,
    routing: RoutingOptions,
    routingMetadata: RoutingMetadata,
)
```

---

## Field Definitions

### `version`

- Protocol version string
- v1 always uses `"1.0"`

Used for forward compatibility only.

---

### `intent`

Type: `IntentRef`

```python
IntentRef(
    name: str,
    version: str
)
```

Defines **what** operation is being requested.

Routing matches on:

- intent name
- intent version

---

### `payload`

Type: `Dict[str, Any]`

- Input data for the intent
- Fully opaque to the router
- Interpreted only by agents

The router never inspects payload contents.

---

### `context`

Type: `IntentContext`

Carries execution-scoped information.

Common fields include:

- Source agent
- Priority
- Tags
- Timestamps

Context is passed unchanged through routing.

---

### `metadata`

Type: `IntentMetadata`

Contains system-level metadata such as:

- `traceId`
- `requestId`
- Source identifiers
- Creation timestamps

Metadata may be **augmented** by the router or agents
(e.g., ensuring `traceId` exists).

---

### `routing`

Type: `RoutingOptions`

Specifies **how** routing should occur.

Includes:

- Routing strategy
- Target agent overrides
- Fallback configuration

Routing options directly influence router behavior.

---

### `routingMetadata`

Type: `RoutingMetadata`

Records information about the routing process itself.

Typical contents:

- Decision path
- Attempt order
- Internal routing state

This metadata is appended during routing.

---

## Mutability Rules

During routing:

- `payload` is never mutated by the router
- `intent` identity is immutable
- `routingMetadata` may be appended
- `metadata` may be augmented (traceId, timestamps)

Agents should avoid mutating routing semantics.

---

## Envelope Lifecycle

1. Created by client or agent
2. Passed into router
3. Routed through agents
4. Used to produce an `AgentResponse`

Each routing cycle uses **one envelope**.

---

## Envelope vs Transport Frame

The intent envelope:

- Is a logical routing structure
- Exists in memory

Transport frames:

- Wrap envelopes for transport
- Handle serialization and encryption

The router never sees transport frames.

---

## Error Handling

Malformed envelopes:

- Are rejected before routing
- Result in routing-level errors

Once routing begins, the envelope is assumed valid.

---

## Design Rationale

The intent envelope is explicit to:

- Centralize routing data
- Avoid hidden parameters
- Make routing behavior observable

All routing decisions are explainable by inspecting the envelope.

---

## Summary

The `IntentEnvelope` is:

- The core routing unit
- Transport-agnostic
- Explicit and inspectable

Understanding this structure is essential to understanding IntentusNet v1.
