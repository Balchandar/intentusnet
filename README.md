# 🚀 IntentusNet
### **Secure Runtime for Intent Routing and Multi-Agent Execution**

Deterministic • Transport-Agnostic • EMCL-Ready • MCP-Compatible

IntentusNet is an open-source, language-agnostic **AI agent execution runtime** for secure, fallback-capable, distributed orchestration.

It enables structured **intent routing** across agents, tools, or microservices — with EMCL encrypted envelopes, full traceability, and pluggable transports such as HTTP, ZeroMQ, WebSocket, and in-process.

> ⚠️ **Python SDK Notice:**  
The **Python Runtime SDK** (router, agents, transports, EMCL, MCP adapter) is *included in this release*.  
A higher-level ergonomic SDK (decorators, auto-registration, PyPI package) arrives in the next version.  
C# SDK also arrives next version.

---

# ✨ Key Features

## 🧠 Secure AI Agent Runtime

- Language-agnostic agent model
- `IntentEnvelope` abstraction for clarity
- Agent registry + capability schema
- Deterministic routing with fallback support
- Contextual memory + traceId + correlationId
- Identity-aware agent execution
- EMCL envelope encryption (optional)

Supported Transports:

- HTTP / JSON
- ZeroMQ
- WebSocket
- In-process
- *(Future)* MCP-native transport

---

## ⚡ Intent-Oriented Orchestration Engine

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

The architecture aligns with MCP:

- Agents can be wrapped as MCP tools  
- Accept MCP tool requests  
- Emit MCP-style responses  
- Optional EMCL-secured MCP envelopes  

The **MCP Adapter** is included in the runtime.

---

# 🌐 Language-Agnostic Design

Agents can be written in:

- Python  
- C#  
- Go  
- Rust  
- Any language speaking HTTP/ZeroMQ/WebSocket  

---

# 📦 SDK Status

## ✔️ Included in This Release — Python Runtime SDK

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

## 📌 Coming Next Version

### Python Ergonomic SDK
- `@agent` decorators  
- Auto-capability registration  
- Schema validation helpers  
- PyPI packaging  
- Workflow utilities  

### C# SDK
- Routing client  
- Agent interfaces  
- EMCL provider  
- Transports  

---

# 🧰 Architecture Snapshot

```
┌──────────────────────────────────────────────────────────────┐
│                   Client / Application                       │
└──────────────────────────────────────────────────────────────┘
                               │
                    Intent Router & Orchestrator
                               │
                       Agent Execution Layer
                               │
                  EMCL Secure Envelope (Optional)
                               │
┌──────────────────────────────────────────────────────────────┐
│ MCP Tools │ ZeroMQ │ HTTP │ WebSocket │ In-Process            │
└──────────────────────────────────────────────────────────────┘
                 Backend Agents / Services (Any Language)
```

---

# 📦 Capabilities Summary

## Included
- Intent router + fallback  
- Capability matching  
- Multi-transport execution  
- EMCL encryption  
- Trace spans  
- Agent identity + correlation IDs  
- MCP-compatible core  
- Python runtime SDK  

## Planned
- Python ergonomic SDK  
- C# SDK  
- Full MCP Adapter (inbound + outbound)  
- EMCL key vault + rotation  

---

# 🛠 Installation

```bash
git clone https://github.com/<your-repo>/intentusnet
cd intentusnet
```

Demo:

```bash
intentusctl run-demo orchestrator
```

---

# 🗺 Roadmap

### Next Release
- Python ergonomic SDK  
- C# SDK  
- MCP Adapter  
- EMCL key rotation  

### Future
- Multi-agent planner  
- Vector memory backend  
- Trust-scored routing  
- Distributed orchestrator  

---

# 👤 Author
**Balachandar Manikandan**

---

# 📍 License
MIT License — Open source & commercial friendly.

---

# 🔐 Keywords
AI Runtime, Multi-Agent Orchestration, Intent Routing Framework,  
EMCL Encryption, ZeroMQ Transport, MCP-Compatible Tools,  
Workflow Engine, Secure Agent Communication.
