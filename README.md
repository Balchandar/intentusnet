# 🚀 IntentusNet  
### **Language-Agnostic AI Agent Runtime & Orchestration Framework**  
Secure. Distributed. Multi-Agent. MCP-Compatible.

IntentusNet is an open-source, language-agnostic AI Agent Runtime & Orchestration Framework for building secure, distributed, multi-agent systems.  
It includes optional EMCL encryption, multi-agent orchestration, and protocol-flexible communication (MCP, ZeroMQ, HTTP).

⚠️ **Note:** Python & C# SDKs will release in the *next version*.  
The core runtime, orchestration engine, and transport layers are part of the current version.

---

## ✨ Key Features

### 🧠 **AI Agent Runtime (Current Version)**
- Language-agnostic runtime  
- Multi-agent execution  
- Agent registration + lifecycle  
- Long-running tasks  
- Intent-driven execution logic  
- Identity & state support  

Agents can still interact via:
- HTTP  
- ZeroMQ  
- Raw JSON-RPC  
- Custom transports  

SDKs will simplify this later.

---

### ⚡ **Intent Orchestration Layer (Current Version)**
Includes:
- Intent routing  
- Multi-agent collaboration  
- Fallback chain  
- Priority-based routing  
- Multi-step workflows  
- Parallel/Sequential execution  

This is the **core intelligence layer** of IntentusNet.

---

### 🔐 **Optional EMCL Secure Envelope (Current Version)**
EMCL provides:
- AES-GCM encryption  
- HMAC signing  
- Identity chain  
- Nonce + timestamp  
- Replay protection  

**Enabled only when needed**, e.g.:  
HIPAA, PCI, PHI/PII, SOC2, Zero-Trust.

Default = fastest unencrypted mode.

---

### 🔌 **MCP Compatibility (Planned, Current Version Architecture Ready)**
The architecture already supports:
- MCP as a transport  
- MCP tool routing  
- EMCL-over-MCP  
- Mixing MCP + non-MCP agents  

Actual MCP adapter implementation is in progress.

---

## 🌐 Language-Agnostic Design (Current Version)

Agents can be built in **any language** using simple protocols:

- HTTP / JSON  
- ZeroMQ  
- EMCL envelope  
- WebSockets  
- Custom RPC  

SDKs only make integration easier later.

---

## 📦 SDK Status

### 📌 **Available in NEXT VERSION**
- **Python SDK**
- **C#/.NET SDK**

These will add:
- auto-agent registration  
- EMCL utilities  
- transport helpers  
- type-safe request/response models  
- built-in orchestrator helpers  

### 📌 **Current Version**
The runtime already supports:
- manual agent registration  
- HTTP/JSON-RPC integrations  
- custom agent implementations  
- ZeroMQ workers  
- EMCL envelope mode  
- intent routing  

You can build agents today using direct protocol-level integration.

---

## 🧩 Architecture Overview
            ┌───────────────────────────────────────────────┐
            │              User / Application                │
            └───────────────────────┬───────────────────────┘
                                    │
                          Intent Orchestration Layer (L4/L5)
                                    │
                               Agent Runtime
                                    │
                     (optional) EMCL Secure Envelope (L2)
                                    │
┌─────────────┬────────────┬─────────────┬─────────────┬────────────┐
│   MCP*      │  ZeroMQ    │   HTTP/WS   │  Local Host │  Custom RPC │
└─────────────┴────────────┴─────────────┴─────────────┴────────────┘
           Tools / Agents / Microservices (Any Language)

---

## 📦 Current Version Capabilities

### ✔ Core Runtime  
### ✔ Optional EMCL  
### ✔ Intent Router  
### ✔ Fallback logic  
### ✔ Priority routing  
### ✔ Parallel execution  
### ✔ ZeroMQ support  
### ✔ HTTP transport  
### ✔ JSON-RPC support  
### ✔ Architecture-level MCP support  

### ❌ Python SDK → Next Version  
### ❌ C#/.NET SDK → Next Version  
### ❌ MCP adapter → Under development  

---

## 🛠 Installation
The runtime can run as a process or service.  
Full SDK-based setup will be available next version.

---

## 🗺 Roadmap

### 🔜 **Next Version**
- Python SDK  
- C# SDK  
- MCP Adapter  
- EMCL Key Vault  

### 🔮 Future Enhancements
- Multi-agent Planner Engine  
- Distributed Memory Store  
- Multi-model federation  
- Distributed tracing  

---

## 🤝 Contributing
IntentusNet is in active development.  
Contributions, discussions, and PRs are welcome!

---

## 👤 Author
**Balachandar Manikandan**  

---

## 📄 License
MIT License — Open Source & Commercial Friendly.

---

## 🔑 Keywords
AI Agents, Agent Runtime, Orchestration Framework, EMCL, Secure AI, 
MCP Compatible, Multi-Agent System, Intent Routing, JSON-RPC Encryption,
AI Workflow Engine, LLM Orchestration, Language-Agnostic, ZeroMQ Transport,
Distributed Agents, Agent Registry, Multi-Model Coordination, 
Fallback Routing, HIPAA-Friendly AI, Secure Payload Encryption

----

## ⭐ Summary

**IntentusNet is a language-agnostic AI Agent Runtime & Orchestration Framework.**  
- EMCL is included today and optional.  
- MCP integration is architecturally supported.  
- Python & C# SDKs will ship in the next version.

This keeps IntentusNet fast, flexible, and secure for all environments.

