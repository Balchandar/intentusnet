# IntentusNet

### Deterministic Execution Runtime for Intent Routing and Multi-Agent Systems

**Deterministic • Transport-Agnostic • EMCL-Ready • MCP-Compatible**

IntentusNet is an open-source, language-agnostic **execution runtime for multi-agent and tool-driven systems**.
It makes routing, fallback, and failure handling **deterministic, recorded, explainable, and production-operable**.

IntentusNet focuses strictly on **execution semantics** (not planning, reasoning, or prompt intelligence) — ensuring that **execution behavior remains predictable even when models are not**.

---

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)
[![MCP](https://img.shields.io/badge/MCP-compatible-brightgreen)](#)
[![Architecture](https://img.shields.io/badge/architecture-execution--runtime-orange)](#)

---

## Documentation

📚 **Docs site:** https://intentusnet.com

Start here:

- **Introduction** — what IntentusNet is (and isn't)
- **Guarantees** — the execution contract
- **Architecture** — routing, execution, recording
- **CLI** — inspect, trace, retrieve, diff

---

## Quickstart

Install the Python runtime:

```bash
pip install intentusnet
```

Run a deterministic intent execution:

```python
from intentusnet.runtime import IntentRuntime
from intentusnet.intent import Intent

runtime = IntentRuntime.load_default()

result = runtime.execute(
    Intent(
        name="summarize_text",
        payload={"text": "Hello world"},
    )
)

print(result.output)
```

Inspect and retrieve the stored response (no model re-run):

```bash
intentusnet records list
intentusnet records show <execution-id>
intentusnet retrieve <execution-id>
```

---

## Why IntentusNet

Modern LLM systems are observable, but **not debuggable**.

In real production systems, failures are often:

- irreproducible
- incorrectly blamed on models
- hidden behind retries and fallback logic
- impossible to replay or audit

IntentusNet enforces **deterministic execution semantics around LLMs and tools**, so failures become:

- **Retrievable** — stored responses can be inspected without re-execution
- **Attributable** — routing decisions are recorded and traceable
- **Explainable** — execution paths are deterministic given identical input

---

## Guarantees at a Glance

IntentusNet provides an explicit execution contract:

| Guarantee                    | Status                | Description                                      |
| ---------------------------- | --------------------- | ------------------------------------------------ |
| Deterministic Routing        | **Provided**          | Same input → same agent selection order          |
| Execution Recording          | **Provided**          | Every execution captured with stable hash        |
| Historical Response Retrieval| **Provided**          | Stored response returned, no model re-execution  |
| Policy Filtering             | **Provided**          | Partial allow/deny with continuation             |
| Structured Errors            | **Provided**          | Typed error codes, no silent failures            |
| Crash Recovery               | **Provided**          | WAL-backed execution state & recovery            |
| Signed WAL (REGULATED)       | **Provided**          | Ed25519 per-entry signatures for audit trail     |

➡️ Full guarantee details: https://intentusnet.com/docs/guarantees

---

## Execution Recording & Historical Retrieval

IntentusNet treats **executions as immutable facts**, not transient logs.

Each execution is:

- recorded as a first-class artifact
- retrievable without re-running models (returns stored response)
- inspectable after crashes or upgrades

This enables:

- reliable root-cause analysis
- auditability (with signed WAL for REGULATED mode)
- safe model iteration without rewriting history

> **The model may change.**
> **The recorded execution remains intact.**

**Important:** "Retrieve" returns the stored response exactly as recorded. It does not re-execute agent code or validate that the current system would produce the same result.

This design is formalized in:  
**RFC-0001 — Debuggable Execution Semantics for LLM Systems**  
→ `rfcs/RFC-0001-debuggable-llm-execution.md`

**Non-goals:** IntentusNet does not plan tasks, reason about goals, evaluate outputs, or optimize prompts.

---

## Core Capabilities

- Deterministic intent routing (DIRECT, FALLBACK, BROADCAST strategies)
- Explicit fallback chains
- Execution recording (**WAL-backed**, hash-chained)
- Historical response retrieval
- Crash-safe recovery
- Typed failures & execution contracts
- Signed WAL entries (REGULATED mode, Ed25519)
- Compliance enforcement (DEVELOPMENT / STANDARD / REGULATED)
- Operator-grade CLI
- Transport-agnostic execution

---

## Intent-Oriented Routing

- Capability-driven routing
- Explicit fallback sequences
- Sequential or parallel execution
- Priority-based routing
- Auditable routing decisions
- Trace spans with execution metadata

Routing decisions are **deterministic and recorded**, not heuristic.

---

## EMCL Secure Envelope (Optional)

IntentusNet supports **EMCL (Encrypted Model Context Layer)**:

- AES-GCM authenticated encryption
- HMAC-SHA256 signing (demo provider)
- Identity-chain propagation
- Anti-replay protections

EMCL is optional and transport-agnostic.

---

## Compliance Modes

IntentusNet supports three compliance modes, enforced at router initialization:

| Mode          | Determinism | Signed WAL | PII Policy | Use Case                     |
| ------------- | ----------- | ---------- | ---------- | ---------------------------- |
| DEVELOPMENT   | Optional    | No         | No         | Local testing                |
| STANDARD      | Required    | No         | No         | Production (default)         |
| REGULATED     | Required    | Required   | Required   | HIPAA/SOC2/PCI-DSS workloads |

**REGULATED mode** requires:
- `require_determinism=True` (PARALLEL strategy blocked)
- Ed25519-signed WAL entries
- PII redaction policy configured

Configuration is validated at startup. Non-compliant configurations fail fast with explicit errors.

**Note:** IntentusNet is designed to support regulated workloads. Actual compliance certification depends on deployment configuration and organizational controls.

---

## MCP Compatibility

IntentusNet is **MCP-compatible by design**:

- Agents can be wrapped as MCP tools
- MCP tool requests can be accepted
- MCP-style responses can be emitted
- Optional EMCL-secured MCP envelopes

IntentusNet provides deterministic execution semantics **around MCP tools**, not a replacement for MCP.

📘 **MCP Documentation:**  
https://intentusnet.com/docs/mcp

📦 **MCP Adapter Source:**  
https://github.com/Balchandar/intentusnet/tree/main/src/intentusnet/mcp

---

## Language-Agnostic Design

Agents can be implemented in any language that supports:

- HTTP / JSON
- ZeroMQ
- WebSocket

Including: Python, C#, Go, TypeScript, Rust.

---

## SDK Status

### Included — Python Runtime SDK

- Intent router & fallback engine
- Agent base classes
- Agent registry
- Multi-transport execution
- Execution recorder & historical retrieval engine
- WAL-backed crash recovery
- EMCL providers
- MCP adapter
- CLI tooling
- Example agents & demos

> **Note:** Higher-level ergonomic SDKs (decorators, auto-registration) and C#/TypeScript SDKs are planned next.

---

## Demos

All demos are runnable and deterministic. Execution responses are recorded and retrievable.

📂 **Demo Index:**  
https://intentusnet.com/docs/demos

---

### `deterministic_routing_demo`

Compares three approaches using identical capabilities:

- **without** — ad-hoc production glue code
- **with** — deterministic routing via IntentusNet
- **mcp** — routing backed by a mock MCP tool server

📘 **Demo Documentation:**  
https://intentusnet.com/docs/demos/deterministic-routing

📦 **Source Code:**  
https://github.com/Balchandar/intentusnet/tree/main/examples/deterministic_routing_demo

```bash
python -m examples.deterministic_routing_demo.demo --mode without
python -m examples.deterministic_routing_demo.demo --mode with
python -m examples.deterministic_routing_demo.demo --mode mcp
```

---

### `execution_retrieval_example`

Demonstrates how model upgrades change live behavior while **past execution responses remain retrievable** without re-running models.

📘 **Demo Documentation:**  
https://intentusnet.com/docs/demos/execution-replay

📦 **Source Code:**  
https://github.com/Balchandar/intentusnet/tree/main/examples/execution_replay_example

---

## Operational Scope (Important)

IntentusNet is a **deterministic execution runtime**, not an autonomous agent framework.

### Guarantees

- Deterministic routing, fallback, and failures
- Crash-safe execution recording (WAL with hash chaining)
- Historical response retrieval without re-execution
- Explicit contracts and typed failures
- CLI-first operational control

### Explicit Non-Goals

- No task planning or reasoning
- No evaluation of model outputs
- No replacement for workflow engines
- No distributed consensus in v1

### Determinism Boundary

Determinism is enforced at the **execution layer**, not the **model layer**.  
Non-deterministic model behavior is detected, recorded, and surfaced — never hidden.

---

## Roadmap

**Next**

- Python ergonomic SDK
- C# SDK
- TypeScript SDK
- MCP adapter improvements
- EMCL key rotation

**Future (Optional)**

- Multi-agent planning layer (research)
- Trust-scored routing

---

## Author

**Balachandar Manikandan**

---

## License

MIT License

---

### Keywords

Deterministic execution runtime, intent routing, explicit fallback chains, recorded agent workflows, debuggable LLM systems, execution recording, WAL-backed recovery, signed WAL, compliance modes, MCP-compatible runtime, EMCL-secured agent communication, transport-agnostic AI infrastructure.
