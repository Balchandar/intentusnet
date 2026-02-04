# Deterministic Routing (IntentusNet v1)

This document explains what **deterministic routing** means in IntentusNet v1
and how it is achieved in practice.

Determinism is a **core design guarantee** of v1 and applies regardless of
transport, deployment model, or routing strategy.

---

## What Deterministic Routing Means

In IntentusNet v1, deterministic routing means:

> Given the same intent, the same registered agents, and the same routing options,
> the router will always select and execute agents in the same order.

There is:

- No randomness
- No timing-based selection
- No load-based decision making

All routing decisions are **purely data-driven**.

---

## Why Determinism Matters

Deterministic routing provides:

- Predictable behavior across runs
- Reproducible failures
- Stable fallback order
- Easier debugging and testing
- Confidence when upgrading agents

This is especially important in systems where agents may fail
and fallback behavior must be trusted.

---

## Deterministic Agent Ordering

Before any routing strategy is applied, the router computes a **stable ordering**
of candidate agents.

The ordering rules are applied in this exact sequence:

1. **Local agents first**

   - Agents without a `nodeId` are preferred

2. **Node priority**

   - Lower `nodePriority` values win

3. **Agent name**
   - Lexicographic ordering as a final tie-breaker

This guarantees a total, stable ordering of agents.

---

## Determinism Across Routing Strategies

Deterministic ordering applies to **all routing strategies**.

### DIRECT

- The first agent after deterministic sorting is selected
- Or a specific `targetAgent` override is used

### FALLBACK

- Agents are tried sequentially in deterministic order
- First success wins

### BROADCAST

- Agents are executed sequentially in deterministic order
- No aggregation or reordering occurs

### PARALLEL

- Agents are launched concurrently
- The _first successful completion_ wins
- Launch order is deterministic even though completion order is not

Even in parallel routing, **candidate selection is deterministic**.

**Important (Phase I):** PARALLEL strategy is explicitly **non-deterministic** because the winner depends on completion timing. When `require_determinism=True` (the default), PARALLEL is **blocked** and will raise an error. Use FALLBACK for deterministic multi-agent execution.

---

## What Determinism Does NOT Mean

Deterministic routing does not imply:

- Identical execution timing
- Identical performance
- Identical resource usage

Only **selection order and decision logic** are deterministic.

---

## Determinism vs Load Balancing

IntentusNet v1 intentionally avoids:

- Round-robin selection
- Randomized agent choice
- Dynamic load-based routing

These techniques trade predictability for throughput
and are considered out of scope for v1.

---

## Determinism Across Transports

Transport choice does not affect determinism.

The following transports behave identically:

- In-process
- HTTP
- WebSocket
- ZeroMQ

Transports only move messages;
they never influence routing decisions.

---

## Failure Determinism

When failures occur:

- Errors are handled in a deterministic order
- Fallback always follows the same path
- The same error conditions produce the same outcome

This makes production incidents reproducible
rather than probabilistic.

---

## Design Trade-Offs

IntentusNet v1 explicitly trades:

- Throughput
- Elasticity
- Automatic scaling

in favor of:

- Predictability
- Simplicity
- Auditability

These trade-offs are intentional.

---

## Summary

Deterministic routing in IntentusNet v1 ensures:

- Stable agent selection
- Predictable fallback behavior
- Consistent behavior across environments

This guarantee is foundational to the runtime
and shapes all higher-level behavior.
