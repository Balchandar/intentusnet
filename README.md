# 🚀 IntentusNet

### **Secure Runtime for Intent Routing and Multi-Agent Execution**

Deterministic • Transport-Agnostic • EMCL-Ready • MCP-Compatible

IntentusNet is an open-source, language-agnostic **AI agent execution runtime** for secure, fallback-capable, and distributed orchestration.

It enables structured intent routing across agents, tools, or microservices — with built-in EMCL envelope encryption, traceability, and support for HTTP, ZeroMQ, WebSocket, and in-process transports.

⚠️ **Note:** The Python & C# SDKs will be released in the *next version*.
This release focuses on the **core runtime, routing engine, EMCL layer, and transport infrastructure**.

---

## ✨ Key Features

### 🧠 Secure AI Agent Runtime

* Language-agnostic agent communication model
* IntentEnvelope abstraction for message-level clarity
* Agent registry + capabilities schema
* Deterministic routing with fallback resolution
* Contextual memory, trace IDs, correlation IDs
* Identity-aware execution with optional EMCL envelope

Agents can talk via:

* HTTP / JSON
* ZeroMQ
* WebSocket
* In-process
* (Future) MCP / Custom Transports

> SDKs coming soon will simplify agent definition and integration.

---

### ⚡ Intent-Oriented Orchestration Engine

* Capability-based routing
* Envelope-driven fallback chain logic
* Parallel or sequential intent flows
* Priority-based resolution
* Full trace span logging + observability hooks
* RouterDecision audit metadata

This is the **core intelligence layer** enabling deterministic multi-agent workflows.

---

### 🔐 EMCL Secure Envelope (Optional)

* AES-GCM encryption
* HMAC-SHA256 signing (demo mode)
* Identity chain propagation
* Nonce, timestamp, and anti-replay guards

EMCL adds message-layer integrity for zero-trust or compliance-grade scenarios.
Can be toggled on or off per transport instance.

---

### 🔗 MCP-Compatible Architecture

Designed for:

* Supporting MCP-compliant tool calls
* Wrapping agents as MCP tools
* Accepting or emitting EMCL-secured MCP calls

The runtime already aligns with MCP’s intent + args + result format.
MCP adapter arrives in the **next version**.

---

## 🌐 Language-Agnostic Design

Works with any language:

* Agents can run in **Python**, **C#**, **Go**, **Rust**, etc.
* Communication via standard HTTP/JSON, ZeroMQ, or WebSocket
* Transport-agnostic and stateless by design

---

## 📦 SDK Status

### 📌 Coming Soon

* Python SDK
* C# SDK

Will provide:

* Type-safe agent stubs
* Auto-registration & decorators
* EMCL helpers + config injection
* Request/response schema support

### 📌 Current

* Core runtime + manual registration
* ZeroMQ / HTTP transports
* EMCL envelope processing
* Router + fallback engine
* Trace sink (in-memory)

---

## 🧰 Architecture Snapshot

```
┌─────────────────────────────────────────────────────────┐
│                 Client / Application          │
└───────────────────────────────────────────────────┘
                        │
            Intent Router & Orchestrator (L5)
                        │
                  Agent Execution Layer (L4)
                        │
           EMCL Secure Envelope (Optional, L3)
                        │
┌────────────────────────────────────────────────┐
│   MCP        │   ZeroMQ     │   HTTP       │  WebSocket  │
└────────────────────────────────────────────────┘
        Backend Tools / Agents (Any Language)
```

---

## 📦 Capabilities Summary

### ✅ Included

* IntentRouter with fallback support
* Trace spans with metadata
* Multi-transport execution (inproc / HTTP / ZeroMQ)
* Optional EMCL envelope layer
* AgentRegistry with capability matching
* Agent identity + traceId/correlationId support
* MCP architecture-ready core

### ❌ Planned

* Python SDK  → Next
* C# SDK      → Next
* MCP Adapter → Next
* EMCL key rotation & vault → Future

---

## 🛠 Installation

```bash
git clone https://github.com/<your-repo>/intentusnet
cd intentusnet
```

Run a demo:

```bash
intentusctl run-demo orchestrator
```

---

## 🗺 Roadmap

### 🔜 Next

* Python & C# SDKs
* Full MCP adapter (inbound & outbound)
* EMCL key vault, key rotation

### 🌟 Future

* Multi-agent planner engine
* Vector memory backend
* Multi-model federation
* Agent-level trust scoring
* Distributed orchestration runtime

---

## 👤 Author

**Balachandar Manikandan**

---

## 📍 License

MIT License — open source & commercial use allowed.

---

## 🔐 Keywords

AI Runtime, Multi-Agent, Intent Routing, Secure Orchestration,
EMCL Envelope, Agent Framework, Traceable AI, Fallback Routing,
ZeroMQ Agent Transport, MCP Protocol, Open AI Orchestration,
Compliance-Aware Agents, Pluggable Routing, Envelope Signing,
Encrypted Agent RPC, Transport-Agnostic Runtime.
