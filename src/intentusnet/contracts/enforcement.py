"""
Contract enforcement - Runtime enforcement during execution.
"""

from __future__ import annotations

import time
from typing import Optional, Callable, Any

from .models import ExecutionContract, SideEffectClass, ContractViolation


class ContractEnforcementError(Exception):
    """
    Raised when contract is violated during execution.
    """

    def __init__(self, violation: ContractViolation) -> None:
        self.violation = violation
        super().__init__(f"Contract violated: {violation.reason}")


class ContractEnforcer:
    """
    Runtime contract enforcer.

    Wraps step execution with contract enforcement.
    """

    @staticmethod
    def enforce_timeout(
        fn: Callable[[], Any],
        timeout_ms: int,
        step_id: str,
    ) -> Any:
        """
        Enforce timeout on step execution.

        Note: Python doesn't have reliable thread-safe timeout for arbitrary code.
        This is a best-effort implementation using time tracking.
        For production, use process-level timeouts or async with asyncio.timeout().
        """
        start = time.time()
        result = fn()
        elapsed_ms = (time.time() - start) * 1000

        if elapsed_ms > timeout_ms:
            raise ContractEnforcementError(
                ContractViolation(
                    step_id=step_id,
                    contract_name="timeout_ms",
                    reason=f"Execution exceeded timeout ({elapsed_ms:.0f}ms > {timeout_ms}ms)",
                    details={"elapsed_ms": elapsed_ms, "timeout_ms": timeout_ms},
                )
            )

        return result

    @staticmethod
    def enforce_exactly_once(
        step_id: str,
        completed_steps: set[str],
    ) -> None:
        """
        Enforce exactly-once semantics.

        Raises if step has already been executed.
        """
        if step_id in completed_steps:
            raise ContractEnforcementError(
                ContractViolation(
                    step_id=step_id,
                    contract_name="exactly_once",
                    reason=f"Step '{step_id}' already executed (exactly_once violated)",
                    details={"completed_steps": list(completed_steps)},
                )
            )

    @staticmethod
    def can_retry(
        contract: ExecutionContract,
        side_effect: SideEffectClass,
        attempt_number: int,
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if step can be retried.

        Returns (can_retry, reason).
        """
        # Irreversible steps cannot be retried
        if side_effect == SideEffectClass.IRREVERSIBLE:
            return False, "Irreversible steps cannot be retried"

        # no_retry contract
        if contract.no_retry:
            return False, "Contract specifies no_retry=True"

        # exactly_once contract
        if contract.exactly_once and attempt_number > 1:
            return False, "Contract specifies exactly_once=True"

        # max_retries contract
        if contract.max_retries is not None:
            if attempt_number > contract.max_retries:
                return False, f"Max retries exceeded ({attempt_number} > {contract.max_retries})"

        return True, None
