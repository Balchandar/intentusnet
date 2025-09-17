# RFC-0002: IntentusNet Architecture

## Status
Draft

## Abstract
IntentusNet defines a secure, semantic agent communication framework layered on top of the IXP transport and the EMCL security envelope. It standardizes how agents, registries, and routers cooperate to exchange intents, route them efficiently, and maintain trust in a distributed ecosystem.

---

## Layers

### 1. Application Layer (Agents & Tools)
- Agents expose capabilities (APIs, functions, AI services).
- Tools consume/produce intents.
- Each agent is described in a **Registry schema**.

### 2. Protocol Layer (IntentusNet Core)
- **Intent Router**: routes intents based on type, priority, trust, and fallback rules.
- **Agent Registry**: stores agent metadata, trust scores, and availability.
- **Policy Engine**: applies qualifier relax, access control, and routing policies.
- **Tracer**: records request/response for debugging and observability.

### 3. Security Layer (EMCL)
- AES + HMAC envelope ensures confidentiality and integrity.
- JWT or EMCL-ID chaining provides agent authentication.
- Key vault manages rotation of AES/HMAC keys.

### 4. Transport Layer (IXP)
- Built on **ZeroMQ** for high-performance messaging.
- Supports `REQ/ROUTER`, `ROUTER/DEALER`, and `PUB/SUB` topologies.
- Abstracted to allow TCP, IPC, or WebSocket bindings.

---

## Data Flow

1. **Ingress**  
   A client sends an **Intent** wrapped in EMCL to the **Gateway**.

2. **Policy + Registry Check**  
   Gateway validates the envelope, checks the agent registry, applies fallback and priority.

3. **Routing**  
   Gateway forwards the request to the Intent Router → selected agent(s).

4. **Agent Execution**  
   Agent processes the intent and responds via the router.

5. **Egress**  
   Response is wrapped again in EMCL, logged by Tracer, and returned to client.

---

## Design Principles

- **Interoperability**: Compatible with MCP users since registry + meta are aligned.
- **Security by Default**: All intents encrypted and signed.
- **Scalability**: Supports thousands of agents and routers.
- **Resilience**: Fallback and priority routing ensures availability.
- **Observability**: Tracer enables monitoring, debugging, and auditing.

---

# Example Flow

# Example Flow

```mermaid
flowchart LR
    Client --> Gateway
    Gateway --> Orchestrator
    Orchestrator --> AgentA
    Orchestrator --> AgentB
