# RFC-0003: Agent Registry Schema

## Status
Draft

## Abstract
This RFC defines the **Agent Registry schema** used in IntentusNet.  
The registry standardizes how agents are described, discovered, and trusted within the ecosystem.  
It provides a common format for agent metadata, capabilities, routing preferences, and trust signals.

---

## Schema Overview

Each **Agent** is represented as a JSON document stored in a registry (local or distributed).  
The schema covers identification, metadata, routing parameters, and security fields.

---

## JSON Schema

```json
{
  "id": "string (UUID or EMCL-ID)",
  "name": "string",
  "version": "string",
  "description": "string",
  "capabilities": [
    {
      "intent_type": "string",
      "description": "string",
      "qualifiers": ["string"]
    }
  ],
  "routing": {
    "priority": "integer (1 = highest)",
    "fallback": "boolean",
    "availability": "enum[online, degraded, offline]"
  },
  "trust": {
    "score": "number (0.0 - 1.0)",
    "last_verified": "ISO8601 datetime",
    "signed_by": "string (authority id)"
  },
  "meta": {
    "tags": ["string"],
    "owner": "string",
    "contact": "string (email or URL)"
  }
}
