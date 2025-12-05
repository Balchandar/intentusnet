# RFC-0003 — Agent Registry Schema
### IntentusNet Specification Document  
**Status:** Draft  
**Version:** 1.0  
**Author:** Balachandar  
**Last Updated:** 2025-12-05  

---

# 1. Purpose

The **Agent Registry** is the authoritative store of all agent definitions known to an IntentusNet runtime instance.  

It ensures:

- Standardized structure for agents  
- Capability-based routing  
- Registry-level fallback support  
- Versioned intent matching  
- Agent discovery  
- Agent health evaluation  
- Identity + endpoint metadata for distributed deployments  

This RFC formalizes the schema and the validation requirements.

---

# 2. Agent Registry Responsibilities

The registry MUST:

✔ Store all agent definitions  
✔ Support find_agents_for_intent(intentRef)  
✔ Provide fallback chains automatically  
✔ Support agent lookup by name  
✔ Validate capabilities  
✔ Integrate with the router decision process  
✔ Maintain consistent identity & metadata  

The registry MUST NOT:

❌ perform routing logic  
❌ execute agent code  
❌ mutate agent state at runtime  

---

# 3. AgentDefinition Schema

```
AgentDefinition:
  name: string
  version: string
  identity: AgentIdentity
  capabilities: Capability[]
  endpoint: AgentEndpoint
  health: AgentHealth
  runtime: AgentRuntimeInfo
```

Constraints:

- name MUST be unique per runtime instance  
- capabilities MUST contain at least one entry  
- endpoint.type MUST match the transport adapter  

---

# 4. Capability Schema (Updated for Fallback Routing)

```
Capability:
  intent: IntentRef
  inputSchema: object
  outputSchema: object
  examples: object[]
  fallbackAgents: string[]   # NEW
  priority: number           # optional
```

Key Behavior:

- fallbackAgents MUST be evaluated by the router if and only if env.routing.fallbackAgents is empty.  
- Order defines the failover sequence.  
- Router MUST match by (intent.name, intent.version).  

---

# 5. IntentRef Schema

```
IntentRef:
  name: string
  version: string = "1.0"
```

Matching rules:

intentA.name == intentB.name  
AND  
intentA.version == intentB.version  

---

# 6. AgentIdentity Schema

```
AgentIdentity:
  agentId: string
  roles: string[]
  signingKeyId: string|null
```

---

# 7. AgentEndpoint Schema

```
AgentEndpoint:
  type: string
  address: string
```

Supported types: local, http, zeromq, grpc, websocket, mcp.

---

# 8. AgentHealth Schema

```
AgentHealth:
  status: string
  lastHeartbeat: string
```

Router SHOULD prefer healthy agents.  

---

# 9. AgentRuntimeInfo Schema

```
AgentRuntimeInfo:
  language: string
  environment: string
  scaling: string
```

---

# 10. Registry Interface

```
register(agentDefinition)
deregister(agentName)
get_agent(name)
find_agents_for_intent(intentRef)
all_agents()
```

Validation:

- Unique agent names  
- Valid IntentRef  
- fallbackAgents reference existing agents  
- No circular fallback  
- Schemas must be valid structures  

---

# 11. Fallback Resolution Logic

Precedence:

1. Envelope-level fallback  
2. Registry fallback (capability.fallbackAgents)  
3. No fallback → error  

Router behavior:

- On primary failure, pop next fallback agent  
- Continue until success or exhaustion  

---

# 12. Example: Primary → Secondary Storage

Primary:

```
capability.fallbackAgents: ["secondaryStorage"]
```

Secondary:

```
fallbackAgents: []
```

---

# 13. Validation Rules

Registry must enforce:

- Unique agent names  
- Valid capability declaration  
- Valid fallback references  
- No cyclic fallback chains  
- IntentRef matching rules  
- At least one capability per agent  

---

# 14. Router + Registry Interaction

1. Registry provides matching agents via capability  
2. Router selects primary  
3. Router extracts fallbackAgents from capability  
4. If agent fails, fallback triggers  
5. Execution continues until success or last fallback fails  

---

# 15. Future Extensions

- Weighted routing  
- Health-score routing priority  
- Distributed registry synchronization  
- Hot-reloadable agent definitions  

---

# 16. Status

This RFC is **APPROVED** for IntentusNet v1.0 and matches the implementation in:

- models.py  
- router.py  
- registry.py  
- demo agents  

