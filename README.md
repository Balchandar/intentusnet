# 🚀 IntentusNet  
### **Language-Agnostic AI Agent Runtime & Orchestration Framework**  
Secure • Distributed • Multi-Agent • Extensible

IntentusNet is an open-source, language-agnostic **AI Agent Runtime & Orchestration Framework** for building secure, distributed, multi-agent systems.

The core runtime includes optional EMCL encryption, flexible multi-agent orchestration, and protocol-agnostic communication (ZeroMQ, HTTP, WebSockets, local transport).

⚠️ **Note:** The Python & C# SDKs will be released in the *next version*.  
This release focuses on the **core runtime, orchestration engine, tracing, and transport layer**.

---

## ✨ Key Features

### 🧠 AI Agent Runtime (Current Version)

- Language-agnostic, lightweight runtime  
- Multi-agent execution model  
- Agent definition + registration system  
- Intent-based invocation  
- Long-running workflow support  
- Identity & contextual state handling  

Agents can interact via:
- HTTP / JSON  
- ZeroMQ  
- Raw JSON-RPC  
- Local host transport  
- Custom transports  

> Future SDKs will make this simpler with decorators, type-safe models, and automatic registration.

---

### ⚡ Intent Orchestration Layer

Built-in orchestration capabilities include:

- Smart intent routing  
- Multi-agent collaboration  
- Fallback chain logic  
- Priority-based routing  
- Sequential & parallel workflows  
- Rich metadata + trace spans  
- Extensible routing strategies  

This is the **core intelligence layer** of IntentusNet.

---

### 🔐 Optional EMCL Secure Envelope

EMCL (Encrypted Model Context Layer) provides:

- AES-GCM encryption  
- HMAC signing  
- Identity chaining  
- Nonce + timestamp  
- Replay protection  
- Tamper resistance  

Use EMCL **only when needed** (HIPAA, PCI, PHI/PII, SOC2, Zero-Trust).  
Default mode is **unencrypted for maximum performance**.

---

### 🔌 MCP-Friendly Architecture (Adapter Coming Soon)

IntentusNet’s architecture is already designed to support:

- MCP as a transport  
- Calling IntentusNet agents as MCP tools  
- EMCL-secured MCP calls  
- Hybrid ecosystems mixing MCP & non-MCP agents  

A full MCP adapter will be available in the next release.  
(Current version ships with architectural readiness, not the complete adapter.)

---

## 🌐 Language-Agnostic Design

Agents can be written in **any programming language**, because IntentusNet communicates using simple, open formats:

- HTTP / JSON  
- ZeroMQ  
- WebSockets  
- EMCL envelope  
- Custom RPC protocols  

This allows developers to combine Python, C#, Go, Rust, Node.js, or any other runtime.

---

## 📦 SDK Status

### 📌 Coming in Next Version
- **Python SDK**
- **C# / .NET SDK**

These will provide:
- Automatic agent registration  
- Type-safe request/response models  
- Transport helpers  
- EMCL utilities  
- Built-in orchestrator helpers  

### 📌 Current Release
The runtime already supports:

- Manual agent registration  
- HTTP/JSON-RPC integrations  
- ZeroMQ workers  
- EMCL encryption mode  
- Intent routing engine  
- Multi-agent orchestrator demo  
- Trace spans + introspection  
- In-process and external transports  

You can build real systems today using raw protocol-level APIs.

---

## 🧩 Architecture Overview

```
            ┌───────────────────────────────────────────────┐
            │                 User / Application             │
            └───────────────────────┬───────────────────────┘
                                    │
                        Intent Orchestration Layer (L4/L5)
                                    │
                              Agent Runtime (L3)
                                    │
                   (Optional) EMCL Secure Envelope (L2)
                                    │
 ┌───────────────┬──────────────┬─────────────┬─────────────┬────────────┐
 │   MCP*         │   ZeroMQ     │  HTTP/WS    │  Local Host │ Custom RPC │
 └───────────────┴──────────────┴─────────────┴─────────────┴────────────┘
            Agents / Tools / Microservices (ANY Language)
```

\* MCP adapter planned for next release.

---

## 📦 Current Version Capabilities

### ✔ Core Runtime  
### ✔ Intent Router  
### ✔ Fallback Logic  
### ✔ Priority Routing  
### ✔ Parallel Execution Support  
### ✔ Optional EMCL Security  
### ✔ ZeroMQ Transport  
### ✔ HTTP / JSON-RPC Transport  
### ✔ Rich Trace Metadata (TraceSpan)  
### ✔ Multi-Agent Orchestrator Demo  
### ✔ Architecture-level MCP readiness  

### ❌ Python SDK → Next Version  
### ❌ C# SDK → Next Version  
### ❌ MCP Adapter → Next Version  

---

## 🛠 Installation

```bash
git clone https://github.com/<your-repo>/intentusnet
cd intentusnet
```

Run the orchestrator demo:

```bash
intentusctl run-demo orchestrator
```

This showcases:

- Summarizer Agent  
- Classifier Agent  
- Primary/Fallback Storage Agents  
- Notification Agent  
- Logger Agent  
- Full multi-agent workflow orchestration  

---

## 🗺 Roadmap

### 🔜 Next Release
- Python SDK  
- C# SDK  
- Full MCP Transport Adapter  
- EMCL Key Vault + Rotation  

### 🔮 Future Enhancements
- Multi-agent Planning Engine  
- Distributed Memory / State Store  
- Multi-Model Federation  
- Distributed Tracing  
- Agent Trust Levels  
- Cloud Runtime & Deployment Targets  

---

## 🤝 Contributing

IntentusNet is in active development.  
Contributions, issues, and PRs are welcome!

---

## 👤 Author  
**Balachandar Manikandan**

---

## 📄 License  
MIT License — open and commercial-friendly.

---

## 🔑 Keywords
AI Agents, Agent Runtime, Orchestration Framework, Multi-Agent System,
Intent Routing, Fallback Routing, Workflow Orchestrator, EMCL Encryption,
Secure AI, MCP Compatible, Distributed Systems, ZeroMQ Transport,
Language-Agnostic Architecture, Agent Registry, Capability Schema,
JSON-RPC, Tracing & Observability, LLM Tooling, Agent-to-Agent Calls,
Secure Payload Layer.

---

## ⭐ Summary

IntentusNet is a secure, language-agnostic AI Agent Runtime & Orchestration Framework.

- EMCL security → included  
- Multi-agent orchestration → included  
- MCP integration → architecturally ready  
- Python & C# SDKs → next version  

Fast. Flexible. Secure.  
Designed for distributed AI ecosystems.
