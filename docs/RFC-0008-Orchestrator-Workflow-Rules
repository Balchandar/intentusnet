# RFC-0008 — Orchestrator Workflow Rules

## Status
Draft — v1.0

## Purpose
This RFC formally defines the **Orchestrator Layer (L5)** of IntentusNet.  
While the Router (L4) handles agent selection and fallback, the **Orchestrator** coordinates *multi-step, multi-agent workflows* including:

# 🧠 IntentusNet Workflows  
*(How workflows work today, and the future roadmap)*

IntentusNet already supports **automatic multi-step workflows** using agent-to-agent chaining.  
This workflow model is enabled by:

- Agents emitting new intents during execution  
- A re-entrant Router capable of handling chained calls  
- Shared `workflowId`, `sessionId`, and `context.memory`  
- Built-in fallback and tracing  

This allows you to build **complex, multi-step pipelines** without a dedicated workflow engine.

---

## ✅ How Workflows Work Today (SDK v1)

### ✔ Agent-Driven Workflow Chaining

Any agent can continue a workflow by calling:

```python
return self.emit_intent("next.intent", payload)
```

This immediately sends a new `IntentEnvelope` back into the router:

```
emit_intent()
  → router.route_intent()
      → next agent executes
```

This creates **sequential, multi-step workflows** automatically.

---

### ✔ Shared Workflow Context

All chained steps share:

- `workflowId`
- `sessionId`
- `context.memory`
- `context.history`

This provides continuity from the first step to the last.

---

### ✔ Automatic Fallback Across Steps

If an agent fails:

```
primary_agent → FAIL
fallback_agent → RUN
```

The router handles fallback seamlessly across chained workflow steps.

---

### ✔ Full Tracing for Every Workflow Hop

Each step generates a `TraceSpan` containing:

- agent name  
- intent name  
- start/end timestamps  
- latency  
- success/error information  

This creates a complete workflow timeline.

---

## 🔍 Example: Multi-Agent Workflow Using Current SDK

```python
class ClassifierAgent(BaseAgent):
    def handle_intent(self, env):
        label = classify(env.payload["text"])
        return self.emit_intent("summarize.doc", {
            "label": label,
            "text": env.payload["text"]
        })

class SummarizerAgent(BaseAgent):
    def handle_intent(self, env):
        summary = summarize(env.payload["text"])
        return self.emit_intent("store.doc", {
            "summary": summary
        })

class StorageAgent(BaseAgent):
    def handle_intent(self, env):
        save_to_db(env.payload)
        return AgentResponse(
            version="1.0",
            status="success",
            payload={"stored": True},
            metadata={"agent": self.definition.name},
        )
```

**This is a real multi-step workflow**—no extra workflow engine required.

---

## 📌 Summary of Current Workflow Capabilities (v1)

| Feature | Supported? | Notes |
|--------|------------|-------|
| Agent → Agent chaining | ✅ Yes | via `emit_intent()` |
| Multi-step workflows | ✅ Yes | implicit + automatic |
| Fallback routing across steps | ✅ Yes | handled by router |
| Shared workflow context | ✅ Yes | `workflowId`, memory |
| Per-step tracing | ✅ Yes | spans recorded |
| Declarative workflow definitions | ❌ No | future |
| Parallel execution | ❌ No | future |
| Branching logic | ❌ No | future |
| Wait/pause/long workflows | ❌ No | future |

---

# 🚀 Future Roadmap — Orchestrator Layer (L5)

*(These features are **planned**, not implemented in SDK v1.)*

The future orchestrator layer will add:

- Declarative workflow definitions (JSON/YAML)
- Parallel step execution
- Branching rules based on agent output
- Step-level policies (retry, skip, fallback)
- Long-running workflows with pause/resume
- Human-in-the-loop approval gates
- Visual workflow designer

These enhancements will sit **above** the current router, not replace it.

---

# 🧩 Why Workflows Already Work Today

IntentusNet v1 can already perform multi-step flows because:

- Agents emit new intents  
- Router handles chained routing  
- Context persists between steps  
- Tracing ties the workflow together  

This creates a natural workflow engine **without any extra components**.

---

This RFC defines the execution foundation for enterprise automation workflows powered by distributed AI agents.

Implementation Status:
- Core Features: Implemented
- Extended Features: Roadmap (not yet available)

