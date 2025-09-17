# IntentusNet

**IntentusNet** is a next-generation protocol for secure, intent-based communication between agents.  
It builds on the [Encrypted Model Context Layer (EMCL)](https://github.com/Balchandar/emcl-protocol) and extends the ideas from [IXP](https://github.com/Balchandar/IXP) into a complete framework for **routing, registry, and observability**.

---

## ✨ Key Features
- 🔒 **Secure envelopes** — all messages use EMCL for signing, encryption, and replay protection.
- 🧭 **Intent-based routing** — agents are addressed by *intents* (e.g., `summarize.text`) instead of raw endpoints.
- 📑 **Agent registry** — declarative adverts with trust scores, health metrics, and priority.
- 🔄 **Routing modes** — `FIRST_OK`, `ALL`, `RACE`, `MAJORITY`, with fallback and qualifier relaxation.
- 🛠 **Transport adapters** — ZeroMQ (MVP), gRPC (planned), extensible for custom backends.
- 📊 **Observability** — trace IDs, policy redaction, metrics for latency, fallback %, and health.
- 📦 **SDKs** — minimal client libraries in **TypeScript** and **Python**.

---
