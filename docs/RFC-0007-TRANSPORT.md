# RFC-0007 — Transport Layer Specification

## Status
Draft — v1.0

## Purpose
This RFC defines the **Transport Layer (L1)** of IntentusNet.  
The transport layer is responsible for carrying IntentEnvelopes and AgentResponses between:

- Local agents
- Remote agents (HTTP/WS/ZeroMQ)
- MCP-compatible agents (future)
- Encrypted EMCL channels

This layer MUST remain **language-agnostic**, **protocol-flexible**, and **extensible**.

---

# 1. Goals

Transport must:

- Support **multiple interchangeable protocols**
- Maintain a unified envelope format (`TransportEnvelope`)
- Allow **encrypted or plaintext** messaging
- Support **request/response** and **streaming** modes
- Allow remote agents to seamlessly register and serve capabilities
- Work identically across Python, C#, Node, Go, Java (future SDKs)

---

# 2. Transport Model Overview

```
Client → Transport → Router → Agent
Client ← Transport ← Router ← Agent
```

The Transport layer is **not aware of business logic**, it only:

- Wraps the message into a TransportEnvelope  
- Sends it over the chosen channel  
- Hands off to the router when message arrives locally  
- Applies EMCL encryption when enabled  

---

# 3. TransportEnvelope Schema

```json
{
  "protocol": "local|http|zeromq|websocket|mcp",
  "protocolNegotiation": {
    "minVersion": "1.0",
    "maxVersion": "1.0"
  },
  "messageType": "intent|response|event",
  "headers": {
    "contentType": "application/json",
    "signature": "...optional...",
    "traceId": "uuid"
  },
  "body": {
    "... IntentEnvelope or AgentResponse ..."
  }
}
```

### Requirements

- MUST support JSON serialisation  
- MUST allow EMCL-wrapped ciphertext in body  
- MUST include protocol version negotiation  

---

# 4. Supported Transport Types

## 4.1 InProcessTransport (Default)
Used for:
- Local development
- Demo environments
- High-performance monolithic agent execution

Routes directly:

```
send_intent() → router.route_intent()
```

## 4.2 HTTP Transport (Optional Plugin)
Supports:
- JSON-RPC
- REST POST
- Long-running tasks

Configuration options:
- Endpoint URL
- Timeout
- Headers
- Retry policy

## 4.3 WebSocket Transport
Used for:
- Bi-directional streaming
- Real-time agent communication
- Agent events & observability stream

## 4.4 ZeroMQ Transport
Used for:
- High-performance distributed architectures
- Worker queues
- Horizontal agent autoscaling

Supports:
- PUSH/PULL
- REQ/REP
- PUB/SUB (for agent events)

## 4.5 MCP Transport (Future)
The transport adapter will allow:

```
MCP Tool Request → IntentEnvelope
IntentReply → MCP Tool Response
```

MCP is NOT replacing the transport layer—it's simply a format adapter.

---

# 5. Transport API

All transports must implement:

```python
class Transport(Protocol):
    def send_intent(self, env: IntentEnvelope) -> AgentResponse:
        ...
```

Optional streaming API (future):

```python
async def send_stream(self, env): ...
async def subscribe(self, eventType): ...
```

---

# 6. EMCL Transport Integration

If EMCL is enabled:

### Before sending:
- IntentEnvelope → JSON
- JSON → ciphertext
- Wrap in EMCLEnvelope:

```json
{
  "emclVersion": "1.0",
  "ciphertext": "...",
  "nonce": "...",
  "hmac": "...",
  "identityChain": []
}
```

### On receipt:
- Validate HMAC
- Decrypt ciphertext
- Reconstruct IntentEnvelope

Transport MUST NOT log decrypted payload.

---

# 7. Routing with Transport

Transport does **NOT** select agents.

Steps:

1. Transport receives IntentEnvelope  
2. Passes to router  
3. Router resolves agent  
4. If remote agent → send back through transport’s remote channel  

---

# 8. Error Handling

Transport errors must be mapped to:

### Transport-level errors:
- CONNECTION_FAILURE
- TIMEOUT
- PAYLOAD_TOO_LARGE
- MALFORMED_MESSAGE

These propagate as:

```json
{
  "status": "error",
  "error": {
    "code": "TRANSPORT_ERROR",
    "message": "..."
  }
}
```

---

# 9. Performance Requirements

- Local transport: <1ms overhead  
- Remote transport: supports batching  
- ZeroMQ transport must reuse sockets  
- HTTP transport must use keep-alive  

---

# 10. Future Extensions

### 10.1 Auto-discovery of remote agents  
Agents can broadcast capability announcements.

### 10.2 Multi-channel routing  
Different agents use different transports automatically.

### 10.3 Prioritised channels  
High-priority intents route through fast-path transport.

### 10.4 Transport health scoring  
Part of the future Planner Engine.

---

# 11. Conclusion

The Transport Layer defines the **communication backbone** of IntentusNet:

- Pluggable
- Secure-ready (EMCL)
- Multi-protocol
- Language-agnostic
- Production-scale capable

This RFC lays the foundation for distributed agent topologies and future cross-language SDKs.

Implementation Status:
- Core Features: Implemented
- Extended Features: Roadmap (not yet available)
