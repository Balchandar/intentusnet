# RFC-0004: IntentusNet Routing Rules

## Status
Draft

## Abstract
This RFC defines the routing rules for IntentusNet. It describes how the Intent Router selects agents based on priority, trust, fallback, qualifiers, and availability, ensuring secure, resilient, and deterministic intent delivery.

## Routing Principles

1. **Priority First**: Agents with higher priority values are selected before lower-priority ones.

2. **Trust-Based Routing**: Use `trust.score` from the registry to break ties when multiple agents have equal priority. Thresholds may be configured to exclude low-trust agents.

3. **Availability Enforcement**: Only agents with `availability=online` are considered primary. `degraded` agents may be selected if no online agents exist and fallback rules permit.

4. **Fallback Handling**: Agents marked `routing.fallback=true` can be used if no primary agent succeeds. Fallback may be combined with priority and trust scoring.

5. **Qualifier Relaxation**: If intent qualifiers are not strictly matched, the router may relax them in order of importance. Example: `specialty` required → if no match, pick closest available agent.

6. **Deterministic Selection**: Routing must be deterministic given the same input. Random selection only used when tie-breaking among equally ranked agents.

## Routing Algorithm (Pseudo-Code)

```
function selectAgent(intent, candidateAgents):
    # Filter by availability
    primaryAgents = filter(candidateAgents, availability='online')
    if empty(primaryAgents):
        primaryAgents = filter(candidateAgents, fallback=true)

    # Rank by priority
    ranked = sort(primaryAgents, by='priority DESC')

    # Break ties using trust.score
    ranked = sort(ranked, by='trust.score DESC')

    # Apply qualifier relaxation if needed
    for agent in ranked:
        if agent.matches(intent.qualifiers):
            return agent

    # If none matched, use fallback if allowed
    for agent in ranked:
        if agent.routing.fallback:
            return agent

    return null
```

## Examples

**Example 1: Priority Selection**

- Agent A → priority=1, trust=0.9, availability=online  
- Agent B → priority=2, trust=0.8, availability=online  

**Selected:** Agent A (higher priority)

**Example 2: Fallback**

- Agent A → priority=1, availability=offline, fallback=false  
- Agent B → priority=2, availability=offline, fallback=true  

**Selected:** Agent B (fallback agent)

**Example 3: Trust Tie-Breaker**

- Agent A → priority=1, trust=0.95, availability=online  
- Agent B → priority=1, trust=0.85, availability=online  

**Selected:** Agent A (higher trust)

## Notes

- Routers MAY log routing decisions for observability and auditing.  
- Configuration parameters like max candidates, strict qualifier matching, and trust thresholds are environment-specific.  
- Adapters wrapping IntentusNet in MCP must maintain deterministic routing before serialization.

## Copyright
All text, diagrams, and specifications in this RFC are part of the IntentusNet project.  
Copyright © 2025 Balachandar Manikandan.  
Licensed under the MIT License.
