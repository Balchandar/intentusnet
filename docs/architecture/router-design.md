# Router Design (IntentusNet v1)

This document describes the **actual routing behavior** implemented in
`intentusnet/core/router.py` for IntentusNet v1.

The router is intentionally **synchronous, deterministic, and bounded**.
No background execution, retries, scheduling, or persistence occurs inside the router.

---

## Responsibilities

The IntentRouter is responsible for:

- Resolving an intent to candidate agents via `AgentRegistry`
- Deterministically ordering agents
- Applying the requested routing strategy
- Executing agent handlers
- Capturing minimal trace spans
- Invoking router middleware hooks

The router **does not**:

- Manage agent lifecycles
- Perform retries or backoff
- Persist state
- Enforce authorization
- Schedule work asynchronously

---

## Routing Entry Point

All intent execution flows through a single method:

```python
IntentRouter.route_intent(env: IntentEnvelope) -> AgentResponse
```

Key properties:

- Fully synchronous (blocking)
- Single response per intent
- Errors are normalized into `AgentResponse`

---

## Deterministic Agent Resolution

### Capability Matching

The router first asks the registry for all agents that declare support for the intent:

```python
agents = registry.find_agents_for_intent(env.intent)
```

If no agents are found:

- Routing fails immediately
- `CAPABILITY_NOT_FOUND` is returned

---

### Deterministic Ordering (Critical Guarantee)

Before any routing strategy is applied, candidate agents are **sorted deterministically**:

Order rules:

1. **Local agents first** (`definition.nodeId is None`)
2. **Lower nodePriority wins**
3. **Lexicographic agent name** (final tie-breaker)

This guarantees:

- Stable routing across runs
- Predictable fallback order
- No randomness or timing influence

This ordering applies to **all strategies**.

---

## Routing Strategy Resolution

The router selects a strategy from:

```python
env.routing.strategy or RoutingStrategy.DIRECT
```

Supported strategies in v1:

- `DIRECT`
- `FALLBACK`
- `BROADCAST`
- `PARALLEL`

If an unknown strategy is provided, the router safely degrades to `FALLBACK`.

---

## Strategy Semantics

### DIRECT

Behavior:

- If `routing.targetAgent` is set, that agent is selected
- Otherwise, the **first agent after deterministic sorting** is used
- Exactly **one agent** is executed

Failure conditions:

- Target agent not registered → routing error
- Agent throws or returns error → error response

This is the **default and recommended v1 strategy**.

---

### FALLBACK

Behavior:

- Agents are executed **sequentially**, in deterministic order
- First successful response wins
- Errors are collected but not retried

Failure conditions:

- All agents fail → last error is returned

Guarantees:

- No parallelism
- No retries
- No state mutation between attempts

---

### BROADCAST

Behavior:

- All agents are executed **sequentially**
- All failures are tolerated
- The **last successful response**, if any, is returned

Notes:

- Execution order is deterministic
- All agents receive the same envelope instance
- No aggregation of responses is performed

If no agent succeeds:

- The last error is returned

---

### PARALLEL

Behavior:

- All agents are executed concurrently using a thread pool
- The **first successful response wins**
- Remaining executions are ignored (not cancelled)

Important constraints:

- No shared state protection is provided
- Envelope is shared across threads
- No timeout or cancellation support exists in v1

Failure conditions:

- All agents fail → last error is returned

---

## Error Handling

Errors can originate from:

- Registry resolution
- Agent execution
- Unexpected exceptions

All errors are normalized into:

```python
AgentResponse(
  status="error",
  error=ErrorInfo(...)
)
```

Unhandled exceptions are converted into:

- `ROUTING_ERROR` or `INTERNAL_AGENT_ERROR`

The router never raises exceptions to the caller.

---

## Tracing Behavior (v1)

For every routing attempt, exactly **one TraceSpan** is recorded.

Captured fields:

- agent
- intent
- status (`ok` | `error`)
- latencyMs
- error (string, optional)

No parent-child spans or distributed tracing exist in v1.

---

## Middleware Hooks

If router middleware is registered, the following hooks are invoked:

- `before_route(env)`
- `after_route(env, response)`
- `on_error(env, error)`

Middleware failures:

- Are logged
- Never interrupt routing

Middleware is **best-effort only**.

---

## Design Constraints (Intentional)

The router is intentionally limited to:

- Synchronous execution
- Deterministic ordering
- In-memory operation

These constraints ensure:

- Predictable behavior
- Easy reasoning
- Safe v1 stability

More advanced orchestration belongs **outside** the router.

---

## Summary

IntentusNet v1 routing is:

- Deterministic
- Explicit
- Synchronous
- Bounded

If you understand this file, you understand the entire runtime behavior of IntentusNet v1.
