"""
Project Blackbox — Demo Agents

Simulates a regulated financial loan-approval pipeline:

  LoanApplication → RiskAssessor → FraudScreener → ComplianceValidator → CreditDecision

Each agent is a deterministic function (no real model call) that produces
realistic output. The demo proves that IntentusNet's execution infrastructure
works identically whether the "model" is GPT-4, Claude, Llama, or a stub.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.intent import IntentEnvelope
from intentusnet.protocol.response import AgentResponse
from intentusnet.protocol.agent import AgentDefinition, Capability
from intentusnet.protocol.intent import IntentRef


# ---------------------------------------------------------------------------
# Agent Definitions (reusable across scenarios)
# ---------------------------------------------------------------------------

def risk_assessor_def(priority: int = 10) -> AgentDefinition:
    return AgentDefinition(
        name="risk-assessor",
        version="1.0",
        nodePriority=priority,
        capabilities=[
            Capability(intent=IntentRef(name="loan.risk.assess", version="1.0")),
        ],
    )


def fraud_screener_def(priority: int = 10) -> AgentDefinition:
    return AgentDefinition(
        name="fraud-screener",
        version="1.0",
        nodePriority=priority,
        capabilities=[
            Capability(intent=IntentRef(name="loan.fraud.screen", version="1.0")),
        ],
    )


def backup_fraud_screener_def(priority: int = 20) -> AgentDefinition:
    return AgentDefinition(
        name="backup-fraud-screener",
        version="1.0",
        nodePriority=priority,
        capabilities=[
            Capability(intent=IntentRef(name="loan.fraud.screen", version="1.0")),
        ],
    )


def compliance_validator_def(priority: int = 10) -> AgentDefinition:
    return AgentDefinition(
        name="compliance-validator",
        version="1.0",
        nodePriority=priority,
        capabilities=[
            Capability(intent=IntentRef(name="loan.compliance.check", version="1.0")),
        ],
    )


def credit_decision_def(priority: int = 10) -> AgentDefinition:
    return AgentDefinition(
        name="credit-decision-engine",
        version="1.0",
        nodePriority=priority,
        capabilities=[
            Capability(intent=IntentRef(name="loan.credit.decide", version="1.0")),
        ],
    )


def loan_orchestrator_def(priority: int = 10) -> AgentDefinition:
    return AgentDefinition(
        name="loan-orchestrator",
        version="1.0",
        nodePriority=priority,
        capabilities=[
            Capability(intent=IntentRef(name="loan.application.process", version="1.0")),
        ],
    )


# ---------------------------------------------------------------------------
# Agent Implementations
# ---------------------------------------------------------------------------

class RiskAssessorAgent(BaseAgent):
    """
    Evaluates applicant risk profile.
    Deterministic: same applicant data → same risk score.
    """

    def __init__(self, definition: AgentDefinition, router, model_version: str = "v1"):
        super().__init__(definition, router)
        self.model_version = model_version

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        income = env.payload.get("annual_income", 0)
        debt = env.payload.get("existing_debt", 0)
        credit_score = env.payload.get("credit_score", 0)

        # Deterministic risk calculation
        dti_ratio = debt / max(income, 1)

        if self.model_version == "v1":
            if credit_score >= 750 and dti_ratio < 0.3:
                risk_level = "LOW"
                risk_score = 0.15
            elif credit_score >= 650:
                risk_level = "MEDIUM"
                risk_score = 0.45
            else:
                risk_level = "HIGH"
                risk_score = 0.82
        else:
            # v2 model: stricter thresholds
            if credit_score >= 780 and dti_ratio < 0.25:
                risk_level = "LOW"
                risk_score = 0.12
            elif credit_score >= 700:
                risk_level = "MEDIUM"
                risk_score = 0.52
            else:
                risk_level = "HIGH"
                risk_score = 0.88

        return AgentResponse.success(
            payload={
                "risk_level": risk_level,
                "risk_score": risk_score,
                "dti_ratio": round(dti_ratio, 4),
                "model_version": self.model_version,
                "factors": [
                    f"credit_score={credit_score}",
                    f"dti_ratio={round(dti_ratio, 4)}",
                    f"income_verified=true",
                ],
            },
            agent=self.definition.name,
        )


class FraudScreenerAgent(BaseAgent):
    """
    Primary fraud detection agent.
    Can be configured to fail (for failure-injection demo).
    """

    def __init__(self, definition: AgentDefinition, router, *, fail_mode: bool = False):
        super().__init__(definition, router)
        self.fail_mode = fail_mode

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        if self.fail_mode:
            raise RuntimeError(
                "FraudScreener: ML model endpoint unreachable "
                "(connection timeout after 5000ms to fraud-model.internal:8443)"
            )

        applicant_id = env.payload.get("applicant_id", "unknown")
        amount = env.payload.get("loan_amount", 0)

        # Deterministic fraud rules
        fraud_indicators = []
        fraud_score = 0.05

        if amount > 500_000:
            fraud_indicators.append("high_value_application")
            fraud_score += 0.15

        if "rush" in env.payload.get("flags", []):
            fraud_indicators.append("expedited_processing_requested")
            fraud_score += 0.10

        return AgentResponse.success(
            payload={
                "fraud_score": round(fraud_score, 4),
                "fraud_indicators": fraud_indicators,
                "screening_result": "PASS" if fraud_score < 0.5 else "FLAG",
                "model": "fraud-detector-v3.2",
                "applicant_id": applicant_id,
            },
            agent=self.definition.name,
        )


class BackupFraudScreenerAgent(BaseAgent):
    """
    Fallback fraud detector (rule-based, no ML model dependency).
    Used when primary FraudScreener is unavailable.
    """

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        amount = env.payload.get("loan_amount", 0)

        # Simple rule-based screening (no ML model)
        fraud_score = 0.10 if amount > 500_000 else 0.03

        return AgentResponse.success(
            payload={
                "fraud_score": fraud_score,
                "fraud_indicators": ["rule_based_only"],
                "screening_result": "PASS" if fraud_score < 0.5 else "FLAG",
                "model": "rule-based-fallback-v1",
                "note": "Primary fraud model unavailable; rule-based fallback used",
            },
            agent=self.definition.name,
        )


class ComplianceValidatorAgent(BaseAgent):
    """
    Regulatory compliance check agent.
    Validates against KYC/AML and lending regulations.
    """

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        applicant_id = env.payload.get("applicant_id", "unknown")
        amount = env.payload.get("loan_amount", 0)

        checks = {
            "kyc_verified": True,
            "aml_screening": "CLEAR",
            "ofac_check": "CLEAR",
            "regulation_z_compliant": True,
            "fair_lending_check": "PASS",
        }

        if amount > 1_000_000:
            checks["enhanced_due_diligence"] = "REQUIRED"

        return AgentResponse.success(
            payload={
                "compliance_status": "APPROVED",
                "checks": checks,
                "regulatory_framework": "US-FCRA-TILA-ECOA",
                "applicant_id": applicant_id,
            },
            agent=self.definition.name,
        )


class CreditDecisionAgent(BaseAgent):
    """
    Final credit decision engine.
    Model version determines decision thresholds.
    """

    def __init__(self, definition: AgentDefinition, router, model_version: str = "v1"):
        super().__init__(definition, router)
        self.model_version = model_version

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        risk_score = env.payload.get("risk_score", 0.5)
        fraud_score = env.payload.get("fraud_score", 0.5)
        amount = env.payload.get("loan_amount", 0)

        if self.model_version == "v1":
            # v1: Conservative model
            approved = risk_score < 0.5 and fraud_score < 0.3
            rate = 4.5 if risk_score < 0.2 else 6.8
            reasoning = "Conservative underwriting model (v1): weighted risk + fraud composite"
        else:
            # v2: More aggressive model
            approved = risk_score < 0.6 and fraud_score < 0.4
            rate = 3.9 if risk_score < 0.2 else 5.5
            reasoning = "Updated underwriting model (v2): ML-enhanced risk assessment with expanded approval criteria"

        return AgentResponse.success(
            payload={
                "decision": "APPROVED" if approved else "DENIED",
                "interest_rate": rate if approved else None,
                "loan_amount": amount,
                "model_version": self.model_version,
                "reasoning": reasoning,
                "risk_score_used": risk_score,
                "fraud_score_used": fraud_score,
            },
            agent=self.definition.name,
        )


class LoanOrchestratorAgent(BaseAgent):
    """
    Orchestrates the full loan-approval pipeline.

    Pipeline:
      1. Risk Assessment
      2. Fraud Screening (with fallback)
      3. Compliance Validation
      4. Credit Decision
    """

    def __init__(self, definition: AgentDefinition, router, model_version: str = "v1"):
        super().__init__(definition, router)
        self.model_version = model_version

    def handle_intent(self, env: IntentEnvelope) -> AgentResponse:
        from intentusnet.protocol.enums import RoutingStrategy

        applicant = env.payload

        # Step 1: Risk Assessment
        risk_resp = self.emit_intent(
            "loan.risk.assess",
            payload=applicant,
            routing=RoutingOptions(strategy=RoutingStrategy.DIRECT, targetAgent="risk-assessor"),
        )
        if risk_resp.error:
            return risk_resp

        risk_data = risk_resp.payload or {}

        # Step 2: Fraud Screening (FALLBACK strategy — key demo point)
        fraud_resp = self.emit_intent(
            "loan.fraud.screen",
            payload=applicant,
            routing=RoutingOptions(strategy=RoutingStrategy.FALLBACK),
        )
        if fraud_resp.error:
            return fraud_resp

        fraud_data = fraud_resp.payload or {}

        # Step 3: Compliance Validation
        compliance_resp = self.emit_intent(
            "loan.compliance.check",
            payload=applicant,
            routing=RoutingOptions(strategy=RoutingStrategy.DIRECT, targetAgent="compliance-validator"),
        )
        if compliance_resp.error:
            return compliance_resp

        compliance_data = compliance_resp.payload or {}

        # Step 4: Credit Decision
        decision_payload = {
            **applicant,
            "risk_score": risk_data.get("risk_score", 0),
            "fraud_score": fraud_data.get("fraud_score", 0),
        }
        decision_resp = self.emit_intent(
            "loan.credit.decide",
            payload=decision_payload,
            routing=RoutingOptions(strategy=RoutingStrategy.DIRECT, targetAgent="credit-decision-engine"),
        )
        if decision_resp.error:
            return decision_resp

        decision_data = decision_resp.payload or {}

        return AgentResponse.success(
            payload={
                "pipeline": "loan.application.process",
                "applicant_id": applicant.get("applicant_id"),
                "steps_completed": 4,
                "risk_assessment": risk_data,
                "fraud_screening": fraud_data,
                "compliance": compliance_data,
                "credit_decision": decision_data,
                "final_decision": decision_data.get("decision", "UNKNOWN"),
            },
            agent=self.definition.name,
        )


# Need to import RoutingOptions for the orchestrator
from intentusnet.protocol.intent import RoutingOptions
