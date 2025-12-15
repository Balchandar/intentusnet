# Fallback Behavior (IntentusNet v1)

This document explains **fallback behavior** in IntentusNet v1: when it occurs,
how it is executed, and what guarantees it provides.

Fallback is an explicit, deterministic routing mechanism used when
multiple agents can handle the same intent.

---

## What Fallback Means

In IntentusNet v1, fallback means:

> Attempting multiple candidate agents **sequentially** until one succeeds
> or all candidates fail.

Fallback is **not automatic recovery**. It is a controlled routing strategy.

---

## When Fallback Is Used

Fallback is used when:

- `RoutingStrategy.FALLBACK` is explicitly selected, or
- An unsupported routing strategy is provided (safe fallback behavior)

Fallback is **not** triggered by:

- Transport errors
- Timeouts
- Partial failures outside the router

---

## Candidate Agent Set

Fallback operates on a **precomputed agent list**:

1. Agents are selected by capability
2. Agents are deterministically ordered
3. The ordered list becomes the fallback sequence

This list is fixed for the lifetime of the routing call.

---

## Execution Semantics

During fallback routing:

- Agents are executed **one at a time**
- Each agent receives the same intent envelope
- The next agent is tried only if the previous one fails

There is:

- No parallel execution
- No retries of the same agent
- No backtracking

---

## Success Conditions

Fallback stops when:

- An agent returns a successful `AgentResponse`
- The response is immediately returned to the caller

The first success always wins.

---

## Failure Conditions

Fallback fails when:

- All agents return errors, or
- All agents throw exceptions

In this case:

- The **last error** is returned
- The routing result is deterministic

---

## Error Handling

Errors during fallback may come from:

- Agent-returned errors
- Unhandled agent exceptions

Unhandled exceptions are converted into:

- `INTERNAL_AGENT_ERROR`

The router never propagates raw exceptions.

---

## Determinism Guarantees

Fallback behavior is deterministic because:

- Agent ordering is stable
- Execution is sequential
- No randomness or timing influence exists

Given the same setup, fallback will always follow the same path.

---

## Fallback vs Retry

Fallback is **not retry logic**.

Differences:

| Fallback            | Retry              |
| ------------------- | ------------------ |
| Moves to next agent | Re-runs same agent |
| Deterministic       | Often time-based   |
| Capability-based    | Failure-based      |
| No backoff          | Often uses backoff |

IntentusNet v1 does not implement retries.

---

## Observability

Fallback execution results in:

- A single trace span
- The final agent recorded
- No per-attempt tracing

Fallback attempts are **not individually traced** in v1.

---

## Design Rationale

Fallback exists to:

- Provide resilience without complexity
- Avoid hidden retry behavior
- Preserve predictability

Advanced recovery logic belongs outside the router.

---

## Summary

In IntentusNet v1, fallback is:

- Explicit
- Sequential
- Deterministic
- Bounded

It provides controlled resilience without introducing nondeterminism.
