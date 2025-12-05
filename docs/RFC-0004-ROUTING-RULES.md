# RFC-0004 — IntentusNet Routing Rules Specification
### Status: Draft  
### Version: 1.0  
### Author: Balachandar  
### Last Updated: 2025-12-05  

---

# 1. Purpose

This RFC defines the **routing rules**, **decision flow**, and **fallback mechanisms** used by the IntentusNet runtime.

Routing determines:
- Which agent handles a given intent  
- How fallback chains are applied  
- How target overrides work  
- How routing metadata is generated  
- How errors propagate across agents  

This specification reflects the behavior implemented in `router.py` for v1.0.

---

# 2. Inputs to the Routing Engine

Routing depends on five primary inputs:

### **1. IntentEnvelope**
Contains:
- intent name + version  
- payload  
- priority  
- metadata (traceId, correlationId)  
- routing options (targetAgent, fallbackAgents, broadcast)  

---

### **2. Agent Registry**
Provides:
- candidate agents for the intent  
- capability-level fallback rules  
- agent runtime metadata  

---

### **3. RoutingOptions**
```
RoutingOptions:
  targetAgent: string | null
  broadcast: bool
  fallbackAgents: string[]
```

---

### **4. Agent Capabilities**
```
Capability:
  intent: IntentRef
  fallbackAgents: string[]
```

---

### **5. Router configuration**
- trace sink  
- error mapping  
- routing strategy behavior  

---

# 3. Routing Flow (High Level)

Routing proceeds as follows:

```
1. Accept IntentEnvelope
2. Identify candidate agents
3. Determine primary agent
4. Determine fallback order
5. Execute agent
6. If failure → fallback loop
7. If all fallback exhausted → error
8. Record trace span
9. Return AgentResponse
```

---

# 4. Candidate Agent Discovery

The router requests:

```python
registry.find_agents_for_intent(env.intent)
```

Matching rules:

- `intent.name` must match exactly  
- `intent.version` must match exactly  
- At least one capability must match  

If zero agents match → `RoutingError`.

---

# 5. Primary Agent Selection

Selection priority:

1. **Envelope target override**
   ```json
   "routing": { "targetAgent": "classifier" }
   ```
   MUST route to that agent (if registered).

2. **Registry order**
   The first matching capability provider becomes primary.

3. **Future extensions**
   - Scoring  
   - Health  
   - Latency tracking  

---

# 6. Fallback Strategy (Core of RFC)

### **Fallback Precedence**
```
1. Envelope-level fallbackAgents (override)
2. Capability-level fallbackAgents (registry default)
3. No fallback defined → error on failure
```

---

## 6.1 Envelope Fallback Override

If present:

```json
"fallbackAgents": ["agentA", "agentB"]
```

Router MUST use this override **and ignore registry entries**.

---

## 6.2 Registry Fallback (Capability-Based)

Example:

```
Capability(
  intent=IntentRef("storeDocument"),
  fallbackAgents=["secondaryStorage"]
)
```

Router MUST use this fallback chain unless envelope overrides it.

---

## 6.3 Fallback Execution Loop

```
attempt = 1
while True:
    try primary agent
    if success → return
    if no fallback left → error
    else switch to next fallback agent
    attempt += 1
```

Fallback MUST preserve:

- traceId  
- workflowId  
- context memory  

---

# 7. RoutingMetadata Rules

Router MUST update:

### **previousAgents**
Ordered list of agents tried.

### **routeType**
- DIRECT (first selection)
- FALLBACK (subsequent selections)

### **retryCount**
Incremented for each fallback attempt.

---

# 8. Error Rules

### Error Categories:

#### **INTERNAL_AGENT_ERROR**
- thrown by agent
- caught by router

#### **ROUTING_ERROR**
- no agents found
- no fallback available
- agent not registered

Router MUST wrap errors in `ErrorInfo`.

---

# 9. Tracing Rules

Each agent execution MUST generate a `TraceSpan`:

```
traceId
spanId
agent
intent
startTime
endTime
latencyMs
status
error
```

Fallback attempts MUST produce multiple spans.

---

# 10. Broadcast Routing (Reserved)

Broadcast mode is part of the schema but **NOT implemented** in v1.0.

Rules (when implemented):

- send intent to all matching agents  
- collect responses  
- allow aggregation strategies  

---

# 11. Multi-Agent Routing (Future)

Planned expansions include:

- scoring-based routing  
- weighted round-robin routing  
- health-aware routing  
- zero-downtime rolling update routing  

---

# 12. Complete Routing State Machine

```
START
  ↓
CHECK TARGET OVERRIDE
  ↓
DISCOVER CANDIDATES
  ↓ (0 candidates)
ERROR: NO AGENT FOUND
  ↓
SELECT PRIMARY
  ↓
LOAD FALLBACK ORDER
  ↓
EXECUTE AGENT
  ↓ (success)
RETURN RESPONSE
  ↓
FAILURE?
  ↓ yes
POP NEXT FALLBACK
  ↓ (fallback exists)
SWITCH TO FALLBACK AGENT
  ↓
EXECUTE AGAIN
  ↓
REPEAT or ERROR OUT
```

---

# 13. Example Routing Decision (Demo)

Primary storage:

```
fallbackAgents: ["secondaryStorage"]
```

Primary fails → router switches to secondary.

Trace:

```
primaryStorage (failed)
secondaryStorage (success)
```

---

# 14. Status

This routing logic is **fully implemented in IntentusNet v1.0** and corresponds to:

- `router.py`
- `models.py`
- `registry.py`
- demo agents

The fallback system is validated via orchestrator demo.

Implementation Status:
- Core Features: Implemented
- Extended Features: Roadmap (not yet available)
