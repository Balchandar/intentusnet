# Roadmap (IntentusNet)

This document outlines the **IntentusNet roadmap**.
It is intentionally conservative and separates **released guarantees** from **future exploration**.

Anything not marked as released should be considered **non-committal**.

---

## Released

### v1.5.1 — Provable Determinism (Current)

IntentusNet v1.5.1 introduces provable determinism:

- Execution fingerprinting (SHA-256)
- Deterministic-safe CI/CD (9-gate verification pipeline)
- Drift detection (automatic nondeterminism identification)
- WAL replay verification
- Entropy scanning (static analysis gate)
- Project Blackbox demo (8-act end-to-end proof)
- Enterprise features (gateway enforcement, federation, Time Machine UI)

See [release-notes/v1.5.1.md](release-notes/v1.5.1.md) for full details.

### v4.0 — Enterprise & Deterministic Runtime

IntentusNet v4.0 provides:

- Deterministic intent routing
- Explicit routing strategies (DIRECT, FALLBACK, BROADCAST, PARALLEL)
- Synchronous, bounded execution
- Agent programming model
- Transport abstraction (in-process, HTTP, WebSocket, ZeroMQ)
- WAL-backed crash recovery with hash chaining
- Execution recording and historical response retrieval
- Ed25519 signed WAL (REGULATED mode)
- EMCL payload encryption (AES-256-GCM)
- Compliance modes (DEVELOPMENT, STANDARD, REGULATED)
- Execution contracts and typed failures
- MCP adapter
- Enterprise gateway enforcement and federation
- CLI tooling

---

## Near-Term (v1.x)

The following may be considered for v1.x **without breaking guarantees**:

- Bug fixes and correctness improvements
- Documentation clarifications
- Performance tuning without semantic change
- Additional CI gate scripts
- Minor API ergonomics (non-breaking only)

No new routing semantics will be introduced in v1.x.

---

## Under Exploration (v5 Candidates)

The following ideas are being explored but **not committed**:

- Python ergonomic SDK (decorators, auto-registration)
- C# SDK
- TypeScript SDK
- Async / await-based routing engine
- MCP adapter improvements
- EMCL key rotation
- Structured retry and backoff policies
- Timeouts and cancellation semantics
- Richer trace hierarchies
- Policy hooks and authorization layers
- Pluggable scheduling strategies
- Stronger EMCL identity validation

These items require design RFCs.

---

## Explicit Non-Goals

The following are **not goals** for IntentusNet:

- Becoming a workflow engine
- Acting as a job queue
- Replacing message brokers
- Providing a full observability stack
- Owning key management or auth

IntentusNet remains a deterministic execution runtime.

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

- Align proposals with IntentusNet's deterministic philosophy
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
