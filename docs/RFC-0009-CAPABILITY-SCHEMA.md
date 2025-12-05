# RFC-0009 — Capability Schema Specification

## Status
Draft — v1.0

## Purpose
This RFC defines the **Capability Schema** used by IntentusNet to describe:

- What an agent can do
- The intents it supports
- The expected input/output schemas
- Optional fallback rules
- Examples for tooling & validation

The Capability Schema is a foundational part of the Agent Registry Model.

---

# 1. Goals
The schema must:
- Describe agent abilities clearly
- Support versioned intent definitions
- Enable fallback routing
- Enable input/output validation
- Support examples for SDK generation
- Remain lightweight & extensible

---

# 2. Capability Definition

```json
{
  "intent": { "name": "string", "version": "1.0" },
  "inputSchema": {},
  "outputSchema": {},
  "fallbackAgents": ["agentB"],
  "examples": [{ "input": {}, "output": {} }],
  "metadata": { "description": "string", "tags": [], "deprecated": false }
}
```

---

# 3. Fields

## 3.1 intent
Identifier for routing.

## 3.2 inputSchema
JSON schema for validation.

## 3.3 outputSchema
Expected output format.

## 3.4 fallbackAgents
Default fallback path.

## 3.5 examples
Used by SDKs, tests, documentation.

## 3.6 metadata
Optional descriptive metadata.

---

# 4. JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "title": "AgentCapability",
  "type": "object",
  "properties": {
    "intent": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "version": { "type": "string" }
      },
      "required": ["name", "version"]
    },
    "inputSchema": { "type": "object" },
    "outputSchema": { "type": "object" },
    "fallbackAgents": {
      "type": "array",
      "items": { "type": "string" },
      "default": []
    },
    "examples": {
      "type": "array",
      "items": { "type": "object" }
    },
    "metadata": {
      "type": "object",
      "properties": {
        "description": { "type": "string" },
        "tags": { "type": "array", "items": { "type": "string" } },
        "deprecated": { "type": "boolean" }
      }
    }
  },
  "required": ["intent", "inputSchema", "outputSchema"]
}
```

---

# 5. Router Integration
Capability drives:
- Agent matches
- Fallback
- Documentation
- SDK autogen

---

# 6. Future Enhancements
- Capability scoring
- Weighted fallback
- Dynamic routing policies
- Hot-reloadable capabilities

---

# 7. Conclusion
The Capability Schema defines IntentusNet’s declarative model for agent abilities, routing, and fallback behavior.

Implementation Status:
- Core Features: Implemented
- Extended Features: Roadmap (not yet available)
