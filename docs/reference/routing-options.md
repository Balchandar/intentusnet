# Routing Options (IntentusNet v1)

This document defines the **RoutingOptions** and **RoutingMetadata** structures used by the
IntentusNet router. It is a reference document aligned exactly with v1 behavior.

Routing options describe **how** an intent should be routed.
Routing metadata records **what happened** during routing.

---

## RoutingOptions

`RoutingOptions` influence router behavior directly.

```python
RoutingOptions(
    strategy: RoutingStrategy,
    targetAgent: Optional[str],
)
```

Only the fields listed above affect routing in v1.

---

## Fields

### `strategy`

Type: `RoutingStrategy`  
Default: `DIRECT`

Specifies which routing strategy the router should apply.

Supported strategies in v1:

- `DIRECT`
- `FALLBACK`
- `BROADCAST`
- `PARALLEL`

If an unknown strategy is provided, the router safely degrades to `FALLBACK`.

---

### `targetAgent`

Type: `Optional[str]`  
Default: `None`

Forces routing to a specific agent by name.

Behavior:

- Used only with `DIRECT` strategy
- If the agent is not registered for the intent, routing fails
- Overrides deterministic ordering

This field provides **explicit control**, not discovery.

---

## RoutingMetadata

`RoutingMetadata` is populated by the router during execution.

```python
RoutingMetadata(
    decisionPath: List[str]
)
```

This structure is **append-only**.

---

## Fields

### `decisionPath`

Type: `List[str]`

Records the sequence of agents considered or executed during routing.

Examples:

- DIRECT success:

  ```text
  ["agent-a"]
  ```

- FALLBACK success:
  ```text
  ["agent-a", "agent-b"]
  ```

The contents are deterministic given the same routing inputs.

---

## How RoutingOptions Are Used

At runtime:

1. The router reads `routing.strategy`
2. Candidate agents are deterministically ordered
3. The strategy is applied to that ordered list
4. `routingMetadata.decisionPath` is appended

Routing options are **not modified** during routing.

---

## Interaction With Agents

Agents:

- May read routing options
- Should not mutate them
- Should not depend on routing metadata for logic

Routing metadata exists for **observability**, not control flow.

---

## RoutingOptions vs Business Logic

Routing options:

- Control _which agent runs_
- Do not affect _what the agent does_

Business logic remains entirely inside agents.

---

## What Routing Options Do NOT Provide

Routing options do not provide:

- Conditional branching
- Dynamic routing
- Load balancing
- Retries
- Timeouts

These concerns are intentionally excluded from v1.

---

## Design Rationale

Routing options are minimal to:

- Keep routing predictable
- Avoid hidden behavior
- Ensure deterministic execution

Additional routing complexity belongs outside the router.

---

## Summary

In IntentusNet v1:

- `RoutingOptions` control routing behavior
- `RoutingMetadata` records routing outcomes
- Both are explicit and deterministic

They exist to make routing behavior visible and explainable.
