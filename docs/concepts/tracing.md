# Traceability (IntentusNet v1)

This document explains **how tracing works** in IntentusNet v1 and what guarantees it provides.

Tracing in v1 is intentionally **minimal, synchronous, and local**. It is designed to make
routing behavior observable without introducing hidden complexity.

---

## What Traceability Means in v1

In IntentusNet v1, traceability means:

- Every routed intent produces **exactly one trace span**
- The span describes _what happened_, not _how it was scheduled_
- Tracing never changes routing behavior

Tracing is observational only.

---

## TraceSpan Model

The router emits a `TraceSpan` for each routed intent.

A v1 trace span contains:

- `agent` – the agent that ultimately handled the intent
- `intent` – intent name
- `status` – `"ok"` or `"error"`
- `latencyMs` – end-to-end routing latency
- `error` – error message (optional)

There is:

- No parent/child hierarchy
- No span trees
- No distributed correlation

This is intentional for v1.

---

## TraceSink Abstraction

Tracing output is handled by a `TraceSink` abstraction.

```python
class TraceSink(ABC):
    def record(self, span: TraceSpan) -> None:
        ...
```

The router:

- Emits spans synchronously
- Calls `record(span)` exactly once per intent
- Does not inspect or store spans itself

The trace sink determines **where spans go**.

---

## InMemoryTraceSink

IntentusNet v1 provides a reference implementation:

```python
class InMemoryTraceSink(TraceSink):
    ...
```

Characteristics:

- Stores spans in memory
- Preserves insertion order
- Returns defensive copies on read

This sink is intended for:

- Local development
- Unit and integration tests
- Interactive demos

It is **not** intended for production workloads.

---

## Trace Retrieval

`TraceSink.get_spans()` is optional.

Why:

- Some sinks only export traces (e.g., OpenTelemetry)
- Not all sinks can retain spans in memory

Code that consumes traces should not assume retrieval is supported.

---

## When Traces Are Recorded

A trace span is recorded:

- After agent execution completes
- Whether the intent succeeded or failed
- After routing strategy resolution

There is no tracing for:

- Individual fallback attempts
- Parallel sub-executions
- Transport-level retries (none exist)

The trace represents the **final routing outcome**.

---

## Error Visibility

If routing or agent execution fails:

- `status` is set to `"error"`
- The error message is captured as a string
- Structured error codes remain in `AgentResponse`

Tracing complements error handling; it does not replace it.

---

## Determinism and Tracing

Tracing is deterministic in v1:

- One span per intent
- Emitted at a single, well-defined point
- No background processing

Given the same execution, the same trace output is produced.

---

## What Traceability Does NOT Provide

Tracing in v1 does not provide:

- Distributed tracing
- Span hierarchies
- Automatic correlation across services
- Metrics aggregation
- Sampling

These features are intentionally out of scope.

---

## Design Rationale

Minimal tracing was chosen to:

- Avoid hidden runtime cost
- Keep router behavior transparent
- Prevent observability concerns from influencing execution

Advanced observability can be layered **outside** IntentusNet.

---

## Summary

IntentusNet v1 tracing is:

- Minimal
- Synchronous
- Deterministic
- Non-intrusive

It exists to make routing behavior observable,
not to act as a full observability platform.
