# Roadmap (IntentusNet)

This document outlines the **IntentusNet roadmap**.
It is intentionally conservative and separates **released guarantees** from **future exploration**.

Anything not marked as released should be considered **non-committal**.

---

## Released

### v1.0.0 — Stable (Current)

IntentusNet v1.0.0 provides:

- Deterministic intent routing
- Explicit routing strategies (DIRECT, FALLBACK, BROADCAST, PARALLEL)
- Synchronous, bounded execution
- Agent programming model
- Transport abstraction (in-process, HTTP, WebSocket, ZeroMQ)
- Optional EMCL payload encryption
- Minimal traceability
- MCP adapter
- Complete, frozen documentation

This release is **feature-frozen** except for bug fixes.

---

## Near-Term (v1.x)

The following may be considered for v1.x **without breaking guarantees**:

- Bug fixes and correctness improvements
- Documentation clarifications
- Performance tuning without semantic change
- Additional examples or demos
- Minor API ergonomics (non-breaking only)

No new routing semantics will be introduced in v1.x.

---

## Under Exploration (v2 Candidates)

The following ideas are being explored but **not committed**:

- Async / await–based routing engine
- Structured retry and backoff policies
- Timeouts and cancellation semantics
- Richer trace hierarchies
- Policy hooks and authorization layers
- Pluggable scheduling strategies
- Stronger EMCL identity validation
- Language-native runtimes (TypeScript, C#)

These items require design RFCs.

---

## Explicit Non-Goals

The following are **not goals** for IntentusNet:

- Becoming a workflow engine
- Acting as a job queue
- Replacing message brokers
- Providing a full observability stack
- Owning key management or auth

IntentusNet remains a routing runtime.

---

## How the Roadmap Is Governed

Roadmap changes follow these rules:

- Behavior changes require an RFC
- Major semantic changes require a major version
- Documentation is updated before code
- Backward compatibility is preserved whenever possible

---

## Contribution Expectations

Contributors should:

- Align proposals with IntentusNet’s deterministic philosophy
- Avoid feature creep
- Prefer explicit over automatic behavior
- Respect version boundaries

---

## Summary

The IntentusNet roadmap is:

- Intentional
- Conservative
- RFC-driven
- Stability-first

IntentusNet evolves deliberately to preserve trust.
