from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional
import re


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class PolicyRule:
    """
    A single authorization rule.

    Matching logic is AND across non-empty filters:
      - intents: if non-empty, env.intent must be one of them
      - agents: if non-empty, env.routing.targetAgent must be one of them
      - roles: if non-empty, intersection(roles, ctx.roles) must be non-empty
      - tenants: if non-empty, ctx.tenant must match

    Advanced options:
      - payload_regex: dict[field_name -> regex] to be matched against
        str(payload[field_name])
      - rate_limit_per_minute: max number of requests per minute for this
        rule; if set, rate limiting is applied by the gateway.
      - rate_limit_key_template: format string for key, e.g.
            "{tenant}:{intent}" or "{subject}:{intent}"
      - max_timeout_ms: max duration (ms) allowed for routing/agent execution
        for requests matching this rule.
    """
    id: str
    action: PolicyAction

    intents: List[str] = field(default_factory=list)
    agents: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    tenants: List[str] = field(default_factory=list)

    description: str = ""
    priority: int = 0

    payload_regex: Dict[str, str] = field(default_factory=dict)

    rate_limit_per_minute: Optional[int] = None
    rate_limit_key_template: Optional[str] = None

    max_timeout_ms: Optional[int] = None


@dataclass
class EvaluationContext:
    """
    Context for a single policy evaluation.
    """
    subject: Optional[str]
    roles: List[str]
    tenant: Optional[str]

    intent: str
    agent: Optional[str]

    payload: Dict[str, Any]
    metadata: Dict[str, Any]
    tags: List[str]


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    matched_rule: Optional[PolicyRule] = None
    source: str = "intentusnet.policy"

    # Optional control metadata populated for ALLOW rules
    rate_limit_key: Optional[str] = None
    rate_limit_per_minute: Optional[int] = None
    max_timeout_ms: Optional[int] = None


class PolicyEngine:
    """
    Simple, deterministic, rule-based policy engine.

    - Rules evaluated in given order (first match wins)
    - If no rule matches, default_action is applied
    """

    def __init__(
        self,
        rules: Iterable[PolicyRule],
        default_action: PolicyAction = PolicyAction.ALLOW,
    ) -> None:
        self._rules: List[PolicyRule] = list(rules)
        self._default_action = default_action

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def empty_allow_all(cls) -> PolicyEngine:
        return cls([], default_action=PolicyAction.ALLOW)

    @classmethod
    def empty_deny_all(cls) -> PolicyEngine:
        return cls([], default_action=PolicyAction.DENY)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PolicyEngine:
        """
        Build from a dict (e.g. JSON or YAML loaded) of the shape:

            {
              "default": "allow" | "deny",
              "rules": [
                {
                  "id": "rule-1",
                  "action": "allow",
                  "intents": ["ResearchIntent"],
                  "roles": ["researcher"],
                  "tenants": ["premium"],
                  "agents": ["research-orchestrator"],
                  "description": "...",
                  "priority": 10,
                  "payload_regex": {
                    "query": ".*sensitive.*"
                  },
                  "rate_limit_per_minute": 30,
                  "rate_limit_key_template": "{tenant}:{intent}",
                  "max_timeout_ms": 5000
                }
              ]
            }
        """
        default_raw = (data.get("default") or "allow").lower()
        default_action = PolicyAction.ALLOW if default_raw == "allow" else PolicyAction.DENY

        rules_cfg = data.get("rules") or []
        rules: List[PolicyRule] = []

        for idx, r in enumerate(rules_cfg):
            rid = r.get("id") or f"rule-{idx+1}"
            act_raw = (r.get("action") or "deny").lower()
            try:
                action = PolicyAction(act_raw)
            except Exception:
                action = PolicyAction.DENY

            rules.append(
                PolicyRule(
                    id=rid,
                    action=action,
                    intents=list(r.get("intents") or []),
                    agents=list(r.get("agents") or []),
                    roles=list(r.get("roles") or []),
                    tenants=list(r.get("tenants") or []),
                    description=r.get("description", ""),
                    priority=int(r.get("priority") or 0),
                    payload_regex=dict(r.get("payload_regex") or {}),
                    rate_limit_per_minute=r.get("rate_limit_per_minute"),
                    rate_limit_key_template=r.get("rate_limit_key_template"),
                    max_timeout_ms=r.get("max_timeout_ms"),
                )
            )

        # Rules evaluated in given order (could sort by priority if needed)
        return cls(rules, default_action=default_action)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate(self, ctx: EvaluationContext) -> PolicyDecision:
        for rule in self._rules:
            if self._matches(rule, ctx):
                if rule.action == PolicyAction.ALLOW:
                    key = self._make_rate_limit_key(rule, ctx)
                    return PolicyDecision(
                        allowed=True,
                        reason=f"Allowed by rule '{rule.id}'",
                        matched_rule=rule,
                        rate_limit_key=key,
                        rate_limit_per_minute=rule.rate_limit_per_minute,
                        max_timeout_ms=rule.max_timeout_ms,
                    )
                else:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Denied by rule '{rule.id}'",
                        matched_rule=rule,
                    )

        # No rule matched
        if self._default_action == PolicyAction.ALLOW:
            return PolicyDecision(
                allowed=True,
                reason="Allowed by default policy (no matching rule)",
            )
        else:
            return PolicyDecision(
                allowed=False,
                reason="Denied by default policy (no matching rule)",
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _matches(self, rule: PolicyRule, ctx: EvaluationContext) -> bool:
        # intents
        if rule.intents and ctx.intent not in rule.intents:
            return False

        # agents
        if rule.agents and ctx.agent not in rule.agents:
            return False

        # roles
        if rule.roles:
            if not set(rule.roles).intersection(set(ctx.roles)):
                return False

        # tenants
        if rule.tenants and ctx.tenant not in rule.tenants:
            return False

        # payload_regex
        if rule.payload_regex:
            for field, pattern in rule.payload_regex.items():
                value = ctx.payload.get(field)
                value_str = "" if value is None else str(value)
                if not re.search(pattern, value_str, flags=re.IGNORECASE):
                    return False

        return True

    def _make_rate_limit_key(self, rule: PolicyRule, ctx: EvaluationContext) -> Optional[str]:
        tmpl = rule.rate_limit_key_template
        if not tmpl:
            return None

        return tmpl.format(
            subject=ctx.subject or "",
            tenant=ctx.tenant or "",
            intent=ctx.intent,
            agent=ctx.agent or "",
        )
