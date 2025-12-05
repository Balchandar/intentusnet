# RFC-0006 — IntentusNet Tracing & Observability Model

## Status
Draft — v1.0

## Purpose
This RFC defines the tracing, observability, and introspection model for IntentusNet.  
It explains how spans are generated, how trace context flows across agents, and how tracing integrates with routing, fallback, and EMCL-secured transports.

---

# 1. Goals

IntentusNet’s tracing system must:

- Provide full visibility across multi-agent workflows  
- Support distributed tracing semantics (span, traceId, parentSpanId)  
- Produce reliable output even when agents fail  
- Work identically for local, HTTP, ZeroMQ, and MCPLink transports  
- Support external exporters (OTLP, Jaeger, Zipkin, DataDog)  
- Maintain low overhead in production  
- Integrate with fallback, retries, parallel execution  

---

# 2. Core Concepts

## 2.1 TraceId
A globally unique identifier for a single workflow execution.

Generated once per IntentEnvelope (unless overridden by the client).

## 2.2 Span
Represents a single unit of work executed by an agent or router.

### Span Fields
```json
{
  "traceId": "uuid",
  "spanId": "uuid",
  "parentSpanId": "uuid|null",
  "agent": "string",
  "intent": "string",
  "startTime": "ISO Timestamp",
  "endTime": "ISO Timestamp",
  "latencyMs": 12,
  "status": "success|error",
  "error": {
    "code": "ENUM",
    "message": "string"
  }
}
```

## 2.3 TraceSink
A pluggable backend for storing or exporting spans.

Current implementations:
- InMemoryTraceSink
- ConsoleSink (future)
- FileSink (future)
- OTLPExporter (future)

---

# 3. Span Lifecycle

1. Runtime receives an IntentEnvelope  
2. Router generates **router span**  
3. Router chooses agent  
4. Agent execution generates **agent span**  
5. If fallback triggers, a new span is emitted per agent  
6. Final response includes traceId for downstream correlation  

Example trace sequence:

```
Router (start routing)
 → AgentA span
 → AgentA fails
 → AgentB span (fallback)
 → Done
```

---

# 4. Router Span Rules

The router must produce spans for:

### 4.1 Successful routing
Status = `success`  
Intent processed fully by first agent.

### 4.2 Fallback routing
Status = `fallback`  
Agent failed → fallback activated.

### 4.3 RoutingError
Status = `error`  
No agent, misconfigured fallback, invalid envelope.

---

# 5. Agent Span Rules

Agents must emit spans on:

- success  
- error  
- retries  
- internal exceptions  
- EMCL decryption failure  
- capability mismatch  

Spans remain identical whether the agent is local, remote, or MCP-based.

---

# 6. Parent–Child Relationships

IntentusNet uses a simple propagation rule:

- Router span = parent  
- Every agent span uses parentSpanId = router spanId  
- Nested agent workflows (parallel / orchestrator agents) get a new router span inside child workflows  

---

# 7. EMCL Integration

When EMCL is enabled:

- ciphertext is NOT logged  
- error.message is masked  
- agent identity comes from EMCL identityChain  
- timestamp must come from decrypted envelope  

Trace sinks MUST NOT leak secure payloads.

Only the following fields may be logged:

```
intent, agentName, latencyMs, status, errorCode
```

---

# 8. Exporting Traces

Future exporters:

### 8.1 OTLP (OpenTelemetry)
- Standard telemetry pipeline  
- Supports Jaeger, Zipkin, DataDog, Honeycomb  

### 8.2 File Exporter
- JSONL format  
- Rotating files  

### 8.3 Remote Collector
- ZeroMQ or HTTP streaming  

---

# 9. Performance Requirements

- Tracing must introduce **< 1ms overhead** per request  
- Tracing must not allocate unnecessary objects  
- TraceSink must be async-friendly  
- Production mode may disable full tracing  

---

# 10. API Summary

## 10.1 TraceSpan (model)
See models.py for full dataclass.

## 10.2 TraceSink (interface)
```python
class TraceSink(Protocol):
    def record(self, span: TraceSpan) -> None: ...
```

## 10.3 InMemoryTraceSink
```python
class InMemoryTraceSink:
    def record(self, span: TraceSpan):
        self._spans.append(span)
```

## 10.4 Router Integration
Router generates a span for each agent invocation.

## 10.5 Client Access
Runtime exposes:
```python
runtime.trace_sink.get_spans()
```

---

# 11. Future Enhancements

- Distributed context propagation across transports  
- Hierarchical tracing for orchestrator agents  
- Trace sampling  
- Sensitive-field masking rules  
- Live tracer dashboard  
- EMCL trace signing for tamper-proof logs  

---

# 12. Conclusion

This tracing model provides the foundation needed for:

- Multi-agent observability  
- Debugging workflows  
- Benchmarking  
- Production monitoring  
- Security auditing  

It is lightweight today and fully extendable for enterprise-scale distributed tracing in future versions.
