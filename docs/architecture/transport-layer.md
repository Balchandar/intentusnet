# Transport Layer (IntentusNet v1)

This document describes the **transport layer contract and implementations** in IntentusNet v1.
It reflects the exact behavior of the current transport code and does not assume future features.

The transport layer is responsible only for **moving intent messages** between a client and a router.
It does not participate in routing decisions.

---

## Transport Contract

All transports implement the following protocol:

```python
class Transport(Protocol):
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        ...

    def send_frame(self, frame: TransportEnvelope) -> TransportEnvelope:
        ...
```

### Core Rules

- Transports **must never raise exceptions**
- All failures are converted into `AgentResponse(status="error")`
- Routing semantics are unchanged across transports
- Transports are synchronous in v1

---

## Intent vs Transport Frames

Two layers exist:

- **IntentEnvelope** – routing-level structure
- **TransportEnvelope** – wire-level structure

Transports:

- Wrap `IntentEnvelope` into a transport frame
- Send it across a boundary (process, network)
- Decode the response frame back into `AgentResponse`

The router never sees transport frames.

---

## In-Process Transport

### Purpose

The in-process transport is the **reference implementation**.

Characteristics:

- No serialization
- No network calls
- Direct router invocation

```python
def send_intent(self, env: IntentEnvelope) -> AgentResponse:
    return self._router.route_intent(env)
```

This transport defines the baseline behavior for all others.

---

## HTTP Transport

### Characteristics

- Uses HTTP POST
- Sends JSON-encoded transport frames
- Blocking request-response model

### Error Handling

- Network or decoding failures are caught
- Errors are returned as `TRANSPORT_ERROR`
- `retryable=True` is set for transport failures

The HTTP transport never raises exceptions to the caller.

---

## WebSocket Transport

### Characteristics

- Full-duplex WebSocket connection
- Single request-response per intent
- Optional EMCL encryption

### Execution Model

- Opens a connection
- Sends one frame
- Receives one frame
- Closes the connection

No streaming or long-lived sessions exist in v1.

---

## ZeroMQ Transport

### Characteristics

- Blocking REQ/REP pattern
- Explicit send and receive timeouts
- Optional EMCL support

### Safety Guarantees

- Receive and send timeouts prevent infinite blocking
- Socket errors are converted into `TRANSPORT_ERROR`
- Caller always receives an `AgentResponse`

---

## EMCL Interaction

If EMCL is enabled:

- Payloads are encrypted before transport
- Decryption occurs after receiving a frame
- Routing behavior remains unchanged

Transport failures still return transport-level errors.

---

## What the Transport Layer Does NOT Do

Transports do not:

- Retry requests
- Perform backoff
- Cache responses
- Mutate routing instructions
- Influence agent selection
- Guarantee delivery

These concerns belong to the host system.

---

## Determinism and Consistency

Because transports do not affect routing logic:

- In-process, HTTP, WebSocket, and ZeroMQ behave identically
- Determinism is preserved across boundaries
- Debugging remains consistent

---

## Summary

In IntentusNet v1, the transport layer is:

- Thin
- Synchronous
- Failure-safe
- Semantically neutral

Its only responsibility is **message delivery**, nothing more.
