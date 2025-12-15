# deterministic_routing_demo

This demo is intentionally **not** about getting better AI answers.

It exists to show what changes **in real production code** when
**routing, fallback, and traceability** are centralized instead of being
manually implemented in application glue code.

All variants execute the **same logical flow**:

1. Search for data
2. If search fails, fall back to another provider
3. Summarize results

The only difference is **where the routing decisions live**.

---

## What this demo demonstrates (in practice)

- How fallback is usually implemented today (manually)
- How routing logic spreads across application code
- How IntentusNet centralizes those decisions
- How the _same agents_ behave differently when routing is explicit
- How traces make fallback visible instead of implicit

This is not a benchmark.
This is not an AI quality comparison.
This is a **code-structure comparison**.

---

## Demo variants

The demo ships **three variants** that all call the same logical capabilities.

### 1. `without` — typical production glue code

Represents how most systems work today.

You will see:

- Direct calls to agents/tools
- Manual try/except fallback
- Explicit control flow in application code
- No central place to reason about routing
- Fallback logic duplicated at call sites

This approach works — until the system grows.

---

### 2. `with` — centralized routing using IntentusNet

The **exact same agents**, but:

- Routing is declared, not coded
- Fallback is a routing strategy, not a try/except block
- The application only expresses _intent_
- The router decides execution order deterministically
- Trace spans show which agent failed and which succeeded

The business logic does not change.
Only **where decisions live** changes.

---

### 3. `mcp` — same routing, remote MCP-backed agent

This variant is identical to `with`, except:

- The fallback search agent is backed by a **mock MCP tool server**
- The router does not care whether the agent is local or remote
- The fallback behavior remains unchanged
- Tracing still shows the same decision path

This demonstrates how MCP-based tools can participate in the same routing
model without special handling in application code.

---

## Why this matters

In real systems, developers usually discover too late that:

- Fallback logic is scattered
- Routing behavior is hard to audit
- Debugging failures requires reading application code
- Local vs remote execution paths drift apart
- Adding a new fallback means touching many files

This demo shows what changes when:

- routing is explicit
- fallback is declarative
- execution is observable

No magic. Just fewer places to make mistakes.

---

## How to run

### Non-interactive (default, Docker-safe)

```bash
python -m examples.deterministic_routing_demo.demo --mode without
python -m examples.deterministic_routing_demo.demo --mode with
python -m examples.deterministic_routing_demo.demo --mode mcp
```
