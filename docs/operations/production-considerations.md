# Production Considerations (IntentusNet v1)

This document describes **what to consider before using IntentusNet v1 in production**.
It is intentionally conservative and reflects only current, proven behavior.

IntentusNet v1 is a **routing runtime**, not a full platform.

---

## Scope Reminder

Before using IntentusNet in production, be clear about its scope.

IntentusNet v1 provides:

- Deterministic intent routing
- Explicit fallback behavior
- Synchronous execution
- Transport abstraction
- Optional payload encryption (EMCL)

It does **not** provide operational guarantees by itself.

---

## Deployment Model

IntentusNet v1 is designed to run:

- Embedded inside an application
- As part of an API service
- Inside a worker or controller process

It is **not** a standalone server by default.
You own the process lifecycle.

---

## Concurrency and Throughput

Key points:

- Routing and agents execute synchronously
- Parallel routing uses threads, not async I/O
- No concurrency limits are enforced by the runtime

Production guidance:

- Run multiple process instances if needed
- Apply request limits at the API boundary
- Avoid long-running agent logic

---

## Failure Handling

IntentusNet guarantees:

- No uncaught exceptions leak to callers
- Errors are normalized into `AgentResponse`

IntentusNet does not:

- Retry failed requests
- Apply circuit breakers
- Perform backoff or rate limiting

These mechanisms must be implemented externally.

---

## Timeouts

Important notes:

- Transports may apply timeouts (HTTP, ZeroMQ)
- Router does not enforce execution time limits
- Agents can block indefinitely if miswritten

Production guidance:

- Enforce timeouts at the transport or API layer
- Keep agent execution bounded

---

## State Management

IntentusNet v1 is stateless by design.

- No persistence layer
- No shared state between requests
- No transactional guarantees

If state is required:

- Store it externally (DB, cache)
- Pass references via intent payloads

---

## Observability

Built-in tracing provides:

- One trace span per intent
- Agent name
- Intent name
- Latency and status

Production guidance:

- Export traces via a custom `TraceSink`
- Integrate with existing logging/metrics systems
- Do not rely on in-memory tracing

---

## Security

IntentusNet v1 security model:

- Optional payload encryption via EMCL
- No authentication or authorization
- No key management

Production guidance:

- Use TLS at the transport layer
- Manage EMCL keys securely if enabled
- Enforce auth outside IntentusNet

---

## Transport Selection

Choose transport based on environment:

- In-process: fastest, simplest
- HTTP: interoperable, higher latency
- WebSocket: duplex communication
- ZeroMQ: low-latency, controlled environments

Transport choice does not affect routing semantics.

---

## Resource Management

Be mindful of:

- Thread usage in parallel routing
- Memory usage from payload size
- Connection pooling (HTTP/WebSocket)

Production guidance:

- Monitor resource usage
- Avoid unbounded parallel routing

---

## Versioning and Upgrades

IntentusNet v1 follows:

- Explicit versioning
- No silent behavior changes
- Conservative evolution

Production guidance:

- Pin exact versions
- Read release notes carefully
- Test routing behavior during upgrades

---

## When Not to Use IntentusNet

Do not use IntentusNet v1 if you need:

- Async pipelines
- Persistent workflows
- Automatic retries and backoff
- High-throughput stream processing

Other tools are better suited for those needs.

---

## Summary

IntentusNet v1 can be used in production if:

- You understand its boundaries
- You provide external operational controls
- You value determinism and clarity

It is a **building block**, not a complete platform.
