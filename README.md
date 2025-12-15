## 🚀 IntentusNet

### **Secure Runtime for Intent Routing and Multi-Agent Execution**

Deterministic • Transport-Agnostic • EMCL-Ready • MCP-Compatible

IntentusNet is an open-source, language-agnostic **AI agent execution runtime** for secure, fallback-capable, distributed orchestration.

<!-- Badges -->

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)
[![MCP](https://img.shields.io/badge/MCP-compatible-brightgreen)](#)
[![Architecture](https://img.shields.io/badge/architecture-intent--router-orange)](#)

It enables structured **intent routing** across agents, tools, or microservices — with EMCL encrypted envelopes, full traceability, and pluggable transports such as HTTP, ZeroMQ, WebSocket, and in-process.

> ⚠️ **Python SDK Notice:**  
> The **Python Runtime SDK** (router, agents, transports, EMCL, MCP adapter) is _included in this release_.  
> A higher-level ergonomic SDK (decorators, auto-registration, PyPI package) arrives in the next version.  
> C# SDK also arrives next version.

---

### ✨ Key Features

- Language-agnostic agent model
- `IntentEnvelope` abstraction for clarity
- Agent registry + capability schema
- Deterministic routing with fallback support
- Identity-aware agent execution
- EMCL envelope encryption (optional)

Supported Transports:

- HTTP / JSON
- ZeroMQ
- WebSocket
- In-process
- _(Future)_ MCP-native transport

---

### ⚡ Intent-Oriented Routing Engine

- Capability-driven routing
- Envelope-defined fallback chain
- Sequential or parallel intent flows
- Priority-based routing
- Trace spans with metadata
- `RouterDecision` for auditing workflows

---

### 🔐 EMCL Secure Envelope (Optional)

- AES-GCM authenticated encryption
- HMAC-SHA256 signing (demo provider)
- Identity-chain propagation
- Nonce/timestamp/anti-replay logic

---

### 🔗 MCP-Compatible Architecture

The architecture aligns with MCP:

- Agents can be wrapped as MCP tools
- Accept MCP tool requests
- Emit MCP-style responses
- Optional EMCL-secured MCP envelopes

The **MCP Adapter** is included in the runtime.

---

### 🌐 Language-Agnostic Design

Agents can be written in:

- Python
- C#
- Go
- TypeScript
- Rust
- Any language speaking HTTP/ZeroMQ/WebSocket

---

### 📦 SDK Status

#### ✔️ Included in This Release — Python Runtime SDK

- Agent base class
- Router + fallback engine
- AgentRegistry
- Transports: ZeroMQ, HTTP, WebSocket, In-process
- EMCL providers (AES-GCM, HMAC)
- MCP Adapter
- Protocol models & validators
- Trace sink
- Example agents & demos

---

### 🧪 Demos (What Changes in Practice)

IntentusNet demos focus on **code structure and execution behavior**, not AI output quality.

The primary demo is:

#### `deterministic_routing_demo`

This demo compares **three real-world approaches** using the same logical capabilities:

- **without** — typical production glue code  
  Manual tool calls, explicit retries, hand-written fallback logic.

- **with** — centralized routing using IntentusNet  
  Routing, fallback, and traceability are expressed as routing options and handled by the router.

- **mcp** — same routing flow backed by a mock MCP tool server  
  Demonstrates local + remote agents participating in the same routing model.

The demo is intentionally **non-interactive by default** and safe to run in Docker or CI.

python -m examples.deterministic_routing_demo.demo --mode without
python -m examples.deterministic_routing_demo.demo --mode with
python -m examples.deterministic_routing_demo.demo --mode mcp

---

### 📌 Coming Next Version

#### Python Ergonomic SDK

- `@agent` decorators
- Auto-capability registration
- Schema validation helpers
- PyPI packaging
- Workflow utilities

#### C# SDK

- Routing client
- Agent interfaces
- EMCL provider
- Transports

---

```bash

### 🧰 Architecture Snapshot

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

### 📦 Capabilities Summary

### Included

- Intent router + fallback
- Capability matching
- Multi-transport execution
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

### 🗺 Roadmap

#### Next Release

- Python ergonomic SDK
- C# SDK
- TypeScript SDK
- MCP Adapter
- EMCL key rotation

### Future

- Multi-agent planner
- Trust-scored routing

---

### 👤 Author

**Balachandar Manikandan**

---

### 📍 License

MIT License — Open source & commercial friendly.

---

#### 🔐 Keywords

AI agent runtime, intent routing, deterministic routing, agent fallback,
MCP routing adapter, MCP tool routing, tool routing layer,
multi-agent orchestration, MCP tools, Model Context Protocol,
agent router, tool routing, distributed agent execution,
AI workflow runtime, agent traceability, EMCL encryption,
ZeroMQ agent transport, WebSocket agent runtime,
secure agent communication, enterprise AI infrastructure
