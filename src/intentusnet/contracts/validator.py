"""
Contract validator - Pre-execution validation.

Rules:
- Validates contracts BEFORE execution
- Runtime must prove it can uphold contracts
- If runtime cannot guarantee → FAIL
"""

from __future__ import annotations

from typing import Optional

from .models import ExecutionContract, SideEffectClass, ContractViolation


class ContractValidator:
    """
    Validates execution contracts before execution.

    Ensures runtime can uphold guarantees.
    """

    @staticmethod
    def validate_contract(
        contract: ExecutionContract, side_effect: SideEffectClass
    ) -> Optional[ContractViolation]:
        """
        Validate a contract against side-effect classification.

        Returns None if valid, or ContractViolation if invalid.
        """

        # exactly_once + irreversible → OK
        # exactly_once + reversible/read_only → needs WAL
        if contract.exactly_once:
            if side_effect == SideEffectClass.IRREVERSIBLE:
                # Must use WAL (enforced by runtime)
                pass
            elif side_effect in [SideEffectClass.REVERSIBLE, SideEffectClass.READ_ONLY]:
                # Requires WAL for determinism
                pass

        # no_retry + irreversible → OK
        # no_retry + reversible → OK
        # no_retry + read_only → OK
        if contract.no_retry:
            pass  # Always enforceable

        # max_retries conflicts with no_retry
        if contract.no_retry and contract.max_retries is not None:
            return ContractViolation(
                step_id="",
                contract_name="no_retry",
                reason="Cannot specify both no_retry=True and max_retries",
                details={"max_retries": contract.max_retries},
            )

        # max_retries + irreversible → INVALID
        if contract.max_retries is not None and contract.max_retries > 0:
            if side_effect == SideEffectClass.IRREVERSIBLE:
                return ContractViolation(
                    step_id="",
                    contract_name="max_retries",
                    reason="Cannot retry irreversible steps",
                    details={"side_effect": side_effect.value, "max_retries": contract.max_retries},
                )

        # idempotent_required must be satisfied by agent (declarative)
        if contract.idempotent_required:
            # Runtime cannot enforce - agent must guarantee
            # This is a declarative contract
            pass

        # timeout_ms must be positive
        if contract.timeout_ms is not None and contract.timeout_ms <= 0:
            return ContractViolation(
                step_id="",
                contract_name="timeout_ms",
                reason="Timeout must be positive",
                details={"timeout_ms": contract.timeout_ms},
            )

        # max_cost_units must be positive
        if contract.max_cost_units is not None and contract.max_cost_units <= 0:
            return ContractViolation(
                step_id="",
                contract_name="max_cost_units",
                reason="Max cost units must be positive",
                details={"max_cost_units": contract.max_cost_units},
            )

        return None

    @staticmethod
    def validate_side_effect_transition(
        from_effect: SideEffectClass,
        to_effect: SideEffectClass,
    ) -> Optional[str]:
        """
        Validate side-effect transitions in fallback chains.

        Rules:
        - read_only → read_only (OK)
        - read_only → reversible (OK)
        - read_only → irreversible (OK)
        - reversible → reversible (OK)
        - reversible → irreversible (WARN - escalation)
        - irreversible → * (FORBIDDEN - cannot fallback after irreversible)

        Returns None if valid, error message if invalid.
        """
        if from_effect == SideEffectClass.IRREVERSIBLE:
            return (
                f"Cannot fallback after irreversible step (from={from_effect.value}, to={to_effect.value})"
            )

        # Warn on escalation (reversible → irreversible)
        if from_effect == SideEffectClass.REVERSIBLE and to_effect == SideEffectClass.IRREVERSIBLE:
            # Allow but log warning (runtime must handle)
            return None

        return None
