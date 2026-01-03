"""
Tests for execution contracts.
"""

import pytest

from intentusnet.contracts import (
    ExecutionContract,
    SideEffectClass,
    StepMetadata,
    ContractValidator,
    ContractEnforcer,
    ContractViolation,
)
from intentusnet.contracts.enforcement import ContractEnforcementError


class TestContractValidation:
    """
    Test contract validation.
    """

    def test_valid_contract_read_only(self):
        """
        Test valid contract with read_only side effect.
        """
        contract = ExecutionContract(exactly_once=True, timeout_ms=1000)
        violation = ContractValidator.validate_contract(contract, SideEffectClass.READ_ONLY)
        assert violation is None

    def test_invalid_contract_retry_irreversible(self):
        """
        Test invalid contract: retry + irreversible.
        """
        contract = ExecutionContract(max_retries=3)
        violation = ContractValidator.validate_contract(contract, SideEffectClass.IRREVERSIBLE)
        assert violation is not None
        assert violation.contract_name == "max_retries"
        assert "irreversible" in violation.reason.lower()

    def test_invalid_contract_no_retry_and_max_retries(self):
        """
        Test invalid contract: no_retry + max_retries.
        """
        contract = ExecutionContract(no_retry=True, max_retries=3)
        violation = ContractValidator.validate_contract(contract, SideEffectClass.READ_ONLY)
        assert violation is not None
        assert violation.contract_name == "no_retry"

    def test_invalid_timeout(self):
        """
        Test invalid timeout (negative).
        """
        contract = ExecutionContract(timeout_ms=-100)
        violation = ContractValidator.validate_contract(contract, SideEffectClass.READ_ONLY)
        assert violation is not None
        assert violation.contract_name == "timeout_ms"

    def test_side_effect_transition_irreversible(self):
        """
        Test side-effect transition: cannot fallback after irreversible.
        """
        error = ContractValidator.validate_side_effect_transition(
            SideEffectClass.IRREVERSIBLE, SideEffectClass.READ_ONLY
        )
        assert error is not None
        assert "cannot fallback" in error.lower()

    def test_side_effect_transition_safe(self):
        """
        Test safe side-effect transitions.
        """
        # read_only -> reversible (OK)
        error = ContractValidator.validate_side_effect_transition(
            SideEffectClass.READ_ONLY, SideEffectClass.REVERSIBLE
        )
        assert error is None

        # reversible -> reversible (OK)
        error = ContractValidator.validate_side_effect_transition(
            SideEffectClass.REVERSIBLE, SideEffectClass.REVERSIBLE
        )
        assert error is None


class TestContractEnforcement:
    """
    Test contract enforcement.
    """

    def test_exactly_once_enforcement(self):
        """
        Test exactly-once enforcement.
        """
        completed_steps = {"step1"}

        # Should raise for duplicate step
        with pytest.raises(ContractEnforcementError) as exc_info:
            ContractEnforcer.enforce_exactly_once("step1", completed_steps)

        assert "exactly_once" in str(exc_info.value).lower()

    def test_can_retry_irreversible(self):
        """
        Test retry check for irreversible step.
        """
        contract = ExecutionContract()
        can_retry, reason = ContractEnforcer.can_retry(
            contract, SideEffectClass.IRREVERSIBLE, attempt_number=1
        )

        assert can_retry is False
        assert "irreversible" in reason.lower()

    def test_can_retry_no_retry_contract(self):
        """
        Test retry check with no_retry contract.
        """
        contract = ExecutionContract(no_retry=True)
        can_retry, reason = ContractEnforcer.can_retry(
            contract, SideEffectClass.REVERSIBLE, attempt_number=1
        )

        assert can_retry is False
        assert "no_retry" in reason.lower()

    def test_can_retry_max_retries_exceeded(self):
        """
        Test retry check with max_retries exceeded.
        """
        contract = ExecutionContract(max_retries=2)
        can_retry, reason = ContractEnforcer.can_retry(
            contract, SideEffectClass.REVERSIBLE, attempt_number=3
        )

        assert can_retry is False
        assert "max retries exceeded" in reason.lower()

    def test_can_retry_allowed(self):
        """
        Test retry allowed for reversible step.
        """
        contract = ExecutionContract(max_retries=3)
        can_retry, reason = ContractEnforcer.can_retry(
            contract, SideEffectClass.REVERSIBLE, attempt_number=2
        )

        assert can_retry is True
        assert reason is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
