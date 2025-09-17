# RFC-0008: IntentusNet Agent Registry & Discovery

## Status
Draft

## Abstract
This RFC defines the **Agent Registry and Discovery** system in IntentusNet, enabling agents to register, be discovered, and be prioritized for handling intents securely and efficiently.

---

## 1. Agent Registration

Each agent must register with the registry including:

```json
{
  "agent_id": "string (UUID)",
  "name": "string",
  "version": "string",
  "capabilities": ["capability1", "capability2"],
  "priority": 1,
  "active": true,
  "jwt": "authentication token"
}
```

- `capabilities`: list of intent types the agent can handle.
- `priority`: lower numbers indicate higher priority.
- `jwt`: agent uses JWT for secure registration.

---

## 2. Discovery Protocol

1. **Local discovery** – agents query a nearby gateway/router for available agents.
2. **Global discovery** – agents query the central registry or distributed hash tables (DHT).
3. **Version compatibility** – clients can filter agents by supported protocol/EMCL versions.
4. **Fallback handling** – if a high-priority agent is unavailable, the next agent in priority is chosen.

---

## 3. Agent Heartbeat & Status

- Agents must send heartbeat signals periodically.
- Status includes:
  - `active`: true/false
  - `load`: number of current requests
  - `last_seen`: timestamp
- Gateways use this to update discovery and routing decisions.

---

## 4. Security & Authentication

- Registry accepts only authenticated requests via JWT.
- Each registration, update, or discovery request is verified.
- Unauthorized or expired tokens are rejected.

---

## 5. Use Cases

- Dynamically discover capable agents for new intents.
- Maintain fallback and priority logic.
- Ensure security and reliability across distributed deployments.
- Track agent versions for backward compatibility.

---

## Notes

- Registry can be centralized or distributed.
- Optional: integrate with monitoring tools for agent load and health metrics.
- Supports hot-reload: agents can register/unregister without downtime.

---

## Copyright
All text, diagrams, and specifications in this RFC are part of the IntentusNet project.
Copyright © 2025 Balachandar Manikandan.
Licensed under the MIT License.

---

*File format: .md*
