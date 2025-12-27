# IntentusNet

### **Secure Runtime for Intent Routing and Multi-Agent Execution**

Deterministic • Transport-Agnostic • EMCL-Ready • MCP-Compatible

IntentusNet is an open-source, language-agnostic **execution runtime for multi-agent systems**, designed to make routing, fallback, and failures **deterministic, replayable, explainable, and production-operable**.

It focuses on execution semantics — not planning or intelligence — ensuring that **routing, fallback, and failure behavior remain predictable even when models are not**.

<!-- Badges -->

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)
[![MCP](https://img.shields.io/badge/MCP-compatible-brightgreen)](#)
[![Architecture](https://img.shields.io/badge/architecture-intent--router-orange)](#)

---

## 🎯 Why IntentusNet Exists

Modern LLM systems are observable, but **not debuggable**.

Failures are often:

- irreproducible
- incorrectly attributed to models
- impossible to replay
- obscured by implicit retries and hidden fallback logic

IntentusNet addresses this by enforcing **deterministic execution semantics around LLMs**, allowing failures to become:

- **Replayable**
- **Attributable**
- **Explainable**

### 🔁 Execution Recorder & Replay

IntentusNet treats **executions as immutable facts**, not transient logs.

Each intent execution can be:

- **Recorded** as a first-class artifact
- **Replayed deterministically**, without re-running models
- **Explained**, even after model upgrades or failures

This enables:

- reliable root-cause analysis
- auditability and compliance
- safe model iteration without rewriting history

> **The model may change.  
> The execution must not.**

This design philosophy is formalized in:

📄 **RFC-0001 — Debuggable Execution Semantics for LLM Systems**  
→ [`rfcs/RFC-0001-debuggable-llm-execution.md`](rfcs/RFC-0001-debuggable-llm-execution.md)

**Non-goals:** IntentusNet does not plan tasks, generate tools, or control model reasoning.

---

> ⚠️ **Python SDK Notice:**  
> The **Python Runtime SDK** (router, agents, transports, EMCL, MCP adapter) is _included in this release_.  
> A higher-level ergonomic SDK (decorators, auto-registration, PyPI package) arrives in the next version.  
> C# SDK also arrives next version.

---

## ✨ Key Features

- Language-agnostic agent model
- `IntentEnvelope` abstraction for clarity
- Agent registry + capability schema
- Deterministic routing with fallback support
- Identity-aware agent execution
- Execution recording & deterministic replay
- EMCL envelope encryption (optional)

Supported Transports:

- HTTP / JSON
- ZeroMQ
- WebSocket
- In-process
- _(Future)_ MCP-native transport

---

## ⚡ Intent-Oriented Routing Engine

- Capability-driven routing
- Envelope-defined fallback chain
- Sequential or parallel intent flows
- Priority-based routing
- Trace spans with metadata
- `RouterDecision` for auditing workflows

---

## 🔐 EMCL Secure Envelope (Optional)

- AES-GCM authenticated encryption
- HMAC-SHA256 signing (demo provider)
- Identity-chain propagation
- Nonce/timestamp/anti-replay logic

---

## 🔗 MCP-Compatible Architecture

The architecture is compatible with MCP:

- Agents can be wrapped as MCP tools
- Accept MCP tool requests
- Emit MCP-style responses
- Optional EMCL-secured MCP envelopes

The **MCP Adapter** is included in the runtime.

---

## 🌐 Language-Agnostic Design

Agents can be written in:

- Python
- C#
- Go
- TypeScript
- Rust
- Any language speaking HTTP/ZeroMQ/WebSocket

---

## 📦 SDK Status

### ✔️ Included in This Release — Python Runtime SDK

- Agent base class
- Router + fallback engine
- AgentRegistry
- Transports: ZeroMQ, HTTP, WebSocket, In-process
- EMCL providers (AES-GCM, HMAC)
- MCP Adapter
- Protocol models & validators
- Trace sink
- Execution recorder & replay engine
- Example agents & demos

---

## 🧪 Demos (What Changes in Practice)

IntentusNet demos focus on **code structure and execution behavior**, not AI output quality.

### `deterministic_routing_demo`

This demo compares **three real-world approaches** using the same logical capabilities:

- **without** — typical production glue code
- **with** — centralized routing using IntentusNet
- **mcp** — same routing flow backed by a mock MCP tool server

```bash
python -m examples.deterministic_routing_demo.demo --mode without
python -m examples.deterministic_routing_demo.demo --mode with
python -m examples.deterministic_routing_demo.demo --mode mcp
```

### `execution_replay_example`

Demonstrates how **model upgrades change live behavior** while **past executions remain replayable and explainable**.

---

## 🧰 Architecture Snapshot

```
┌──────────────────────────────────────────────────────────────┐
│                    Client / Application                      │
└──────────────────────────────────────────────────────────────┘
                               │
                          Intent Router
                               │
                       Agent Execution Layer
                               │
                  EMCL Secure Envelope (Optional)
                               │
┌──────────────────────────────────────────────────────────────┐
│ MCP Tools │ ZeroMQ │ HTTP │ WebSocket │ In-Process           │
└──────────────────────────────────────────────────────────────┘
           Backend Agents / Services (Any Language)
```

---

## 📦 Capabilities Summary

### Included

- Intent router + fallback
- Capability matching
- Multi-transport execution
- Execution recording & deterministic replay
- EMCL encryption
- Trace spans
- Agent identity + correlation IDs
- MCP-compatible core
- Python runtime SDK

### Planned

- Python ergonomic SDK
- C# SDK, TypeScript SDK
- Full MCP Adapter (inbound + outbound)
- EMCL key vault + rotation

---

## 🗺 Roadmap

### Next Release

- Python ergonomic SDK
- C# SDK
- TypeScript SDK
- MCP Adapter
- EMCL key rotation

### Future

- Multi-agent planner (research / explicitly optional)
- Trust-scored routing

---

## 👤 Author

**Balachandar Manikandan**

---

## 📍 License

MIT License — Open source & commercial friendly.

---

#### 🔐 Keywords

AI agent execution runtime, deterministic execution semantics,
intent routing, explicit fallback chains, debuggable LLM systems,
agent routing engine, execution traceability, replayable agent flows,
MCP-compatible runtime, MCP tool execution, Model Context Protocol,
distributed agent execution, transport-agnostic agent runtime,
secure agent communication, EMCL encrypted envelopes,
ZeroMQ agent transport, WebSocket agent transport,
production AI infrastructure, LLM orchestration runtime
