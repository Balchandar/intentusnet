# IntentusNet Documentation (v1)

Welcome to the **IntentusNet v1 documentation**.

These documents describe the **exact behavior** of IntentusNet v1 as implemented today.
They intentionally avoid roadmap promises, speculative features, or future designs.

If something is not documented here, it should be assumed **out of scope for v1**.

---

## How to Read These Docs

IntentusNet documentation is organized by intent:

1. **Why** the system exists
2. **What** concepts it introduces
3. **How** it is structured internally
4. **Exact protocol references**
5. **Operational guidance**
6. **Executable demos**

You do not need to read everything at once.

---

## Start Here

If you are new to IntentusNet, read in this order:

1. **Why IntentusNet**
   - `why-intentusnet.md`
2. **Trade-offs**
   - `tradeoffs.md`
3. **Intent Routing**
   - `concepts/intent-routing.md`
4. **Deterministic Routing**
   - `concepts/deterministic-routing.md`
5. **Fallback Behavior**
   - `concepts/fallback.md`

This gives you the mental model before details.

---

## Core Concepts

These documents explain _what_ IntentusNet does conceptually:

- `concepts/intent-routing.md`
- `concepts/deterministic-routing.md`
- `concepts/fallback.md`
- `concepts/traceability.md`
- `concepts/emcl.md`

Read these before diving into architecture.

---

## Architecture

These documents explain _how_ IntentusNet is built:

- `architecture/runtime-overview.md`
- `architecture/router-design.md`
- `architecture/transport-layer.md`
- `architecture/mcp-adapter.md`

These are aligned exactly with the current codebase.

---

## Reference

These are **precise protocol references**:

- `reference/intent-envelope.md`
- `reference/routing-options.md`
- `reference/agent-model.md`

They describe fields, structures, and rules — not concepts.

---

## Demos

Demos are **behavioral references**, not benchmarks:

- `demos/deterministic-routing-demo.md` (canonical)
- `demos/advanced-research-demo.md`

If behavior differs from docs, the demo is the source of truth.

---

## Operations

Production-focused guidance:

- `operations/production-considerations.md`

Read this before using IntentusNet in real systems.

---

## What These Docs Do Not Cover

These docs intentionally do not cover:

- Async orchestration
- Persistent workflows
- Automatic retries or backoff
- Load balancing or scheduling
- Distributed consensus or coordination

Those concerns are outside IntentusNet v1.

---

## Versioning

These documents apply to:

- **IntentusNet v1.x**
- Protocol version `"1.0"`

Future versions will introduce new documents
rather than silently changing existing ones.

---

## Contribution Philosophy

Documentation changes must:

- Match actual code behavior
- Avoid future promises
- Preserve deterministic guarantees

If behavior changes, docs must change first.

---

## Summary

IntentusNet v1 documentation is designed to be:

- Honest
- Deterministic
- Bounded
- Reviewable

If you understand these docs, you understand IntentusNet v1.
