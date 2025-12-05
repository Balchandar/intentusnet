# RFC-0002 — IntentusNet Architecture (Draft, Updated)
### Status: Draft
### Author: Balachandar Manikandan
### Last Updated: 2025-12-05
### Tags: Architecture, Runtime, Routing, Transports, EMCL, Agents

# 1. Overview

This RFC defines the **high-level architecture** of IntentusNet—its runtime components, layer model, execution flow, and extensibility points.  
This document acts as the canonical reference for anyone implementing:

- SDKs (Python, C#, Rust, Go)
- Transports (HTTP, ZeroMQ, MCP)
- Agent runtimes
- Developer tooling
- EMCL-secured environments

IntentusNet is designed to be:  
**language-agnostic, transport-agnostic, secure, and modular.**

---

# 2. Layered Architecture Model

IntentusNet is divided into **five logical layers**, each responsible for a clear set of responsibilities.

```
L5 — Workflows / Planners (Future)
L4 — Intent Orchestration Layer
L3 — Agent Runtime
L2 — EMCL Secure Envelope (Optional)
L1 — Transport Layer (HTTP, ZeroMQ, MCP, Local)
```

---

# 3. L1: Transport Layer

The transport layer defines how envelopes move between:

- client → runtime  
- runtime → agents  
- agent → agent  

Supported transports:

| Transport | Status | Description |
|----------|--------|-------------|
| InProcess | Available | Fastest; used for demo/runtime embedding |
| HTTP/JSON | Available | Language-agnostic REST style |
| ZeroMQ | Available | High-performance distributed messaging |
| WebSocket | Planned | For streaming + persistent channels |
| MCP Adapter | Planned | MCP → IntentusNet conversion |
| Custom RPC | Supported | Users can implement their own |

Transport responsibilities:

- Encoding/decoding envelope messages  
- (Optional) EMCL wrapping/unwrapping  
- Retry mechanisms  
- Delivery guarantees (best-effort only for now)

Transports **must not** understand business semantics — only message delivery.

---

# 4. L2: EMCL Secure Envelope (Optional)

EMCL acts as a security layer that wraps the envelope:

```
Plain Envelope → EMCL Encrypt & Sign → Transport → EMCL Verify & Decrypt → Runtime
```

EMCL provides:

- AES-GCM encryption  
- HMAC signing  
- Nonce & timestamp  
- Replay protection  
- Identity chaining  

This layer is **optional** and only enabled in regulated environments.

---

# 5. L3: Agent Runtime

This is the core of IntentusNet.

Responsibilities:

- Load & register agents  
- Maintain registry of intent capabilities  
- Manage agent lifecycle  
- Execute agent method calls  
- Collect trace spans  
- Surface agent-level errors  
- Enforce routing decisions  

Agent runtime APIs:

```
registry.register(agent)
router.route(envelope)
agent.handle_intent(envelope)
```

Agents may be:

- Embedded (in-process Python)  
- Remote (HTTP/ZeroMQ)  
- Secured (EMCL-wrapped)  
- Hybrid  

The runtime guarantees **consistent agent invocation semantics** across all SDKs and transports.

---

# 6. L4: Intent Orchestration Layer

This layer contains the system’s intelligence:

- Intent routing  
- Multi-agent collaboration  
- Fallback logic  
- Priority routing  
- Sequential & parallel workflows  
- Workflow metadata  
- TraceSpan generation  

Routing follows RFC‑0001 rules.

Future enhancements planned:

- DAG-style workflows  
- Multi-agent planning  
- Agent-based decision making  
- Heuristic routing  
- LLM-driven orchestration  

This layer is where the **Orchestrator Agent** concept lives.

---

# 7. L5: Planner / Workflow Engine (Future)

Future versions will introduce a full AI-driven orchestration engine:

- Multi-agent task decomposition  
- Intent rewriting  
- Long-horizon workflows  
- Context-based agent selection  
- Vector-search memory integration  
- Execution graphs  

This RFC intentionally does not define workflow semantics.

---

# 8. Agent Model

Agents declare what intents they support:

```json
{
  "name": "summarizer",
  "capabilities": [
    { "intent": "summarizeText", "version": "1.0" }
  ]
}
```

Agent responsibilities:

- Validate payload  
- Execute logic  
- Return standardized response  
- Never mutate envelope except `context.memory`/`context.history`  

Types of agents:

- **Worker agents** → perform specific tasks  
- **Orchestrator agents** → coordinate other agents  
- **Fallback agents** → invoked if primary fails  
- **Secure agents** → wrapped in EMCL  

---

# 9. Registry

Registry acts as the source of truth for:

- agent definitions  
- capabilities  
- health status (future)  
- trust level (future)  

APIs:

```
registry.register(agent)
registry.find_agents_for_intent("summarizeText")
registry.get_agent("summarizer")
```

---

# 10. Router

Router responsibilities:

- match intent → candidate agents  
- select appropriate agent  
- apply fallback logic  
- propagate trace spans  
- produce routing decisions  

Router must behave **deterministically** under identical conditions.

---

# 11. Trace Architecture

Every agent invocation produces a `TraceSpan`:

```
traceId
spanId
parentSpanId
agent
intent
startTime
endTime
latencyMs
status
error?
```

Trace spans allow:

- debugging  
- visual execution maps  
- performance metrics  
- audit trails  

Traces may be sent to:

- in-memory sink  
- future distributed tracing (Jaeger, Tempo, etc.)  
- future UI visualization layer  

---

# 12. Error Model

Errors must map into:

```
ErrorInfo {
  code,
  message,
  retryable,
  details
}
```

Router may wrap or forward errors.

Error codes are stable across SDKs.

---

# 13. Extensibility Points

IntentusNet is explicitly designed for:

### 🔧 Custom Transports  
ZeroMQ, custom RPC, MCP, HTTP, embedded.

### 🔧 Custom Agents  
In any language.

### 🔧 Custom Orchestrators  
User-defined decision engines.

### 🔧 EMCL Policies  
Custom identity chain, key rotation.

### 🔧 Custom Routing Strategies (future)  
Plugin-based routing.

---

# 14. Security Considerations

- EMCL should be enabled in regulated workloads.  
- Transport-level TLS is recommended for remote agents.  
- Agents should validate input schema.  
- Routing metadata must not leak sensitive data.  

Threat model includes:

- replay attacks  
- tampering  
- agent impersonation  
- malformed envelopes  

EMCL mitigates many of these.

---

# 15. Revisions

| Version | Date | Notes |
|---------|---------|--------|
| Draft-1 | 2025-12-05 | Initial architecture RFC |
