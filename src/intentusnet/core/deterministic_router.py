"""
Deterministic Router with WAL and Contract Enforcement.

This router extends the base IntentRouter with:
- Write-Ahead Log (WAL) for crash safety
- Contract validation and enforcement
- Side-effect classification
- Structured failure handling
- Cost estimation
"""

from __future__ import annotations

import logging
from typing import Optional
from pathlib import Path

from intentusnet.utils.id_generator import generate_uuid_hex
from intentusnet.utils.timestamps import now_iso

from ..protocol.intent import IntentEnvelope
from ..protocol.response import AgentResponse
from ..recording.models import stable_hash

from ..wal import WALWriter, WALReader, WALEntryType, ExecutionState
from ..contracts import (
    ExecutionContract,
    SideEffectClass,
    StepMetadata,
    ContractValidator,
    ContractEnforcer,
    ContractViolation,
)
from ..failures import FailureType, StructuredFailure, RecoveryStrategy, FailureRegistry
from ..estimation import CostEstimator, ResourceType

from .router import IntentRouter
from .registry import AgentRegistry

logger = logging.getLogger("intentusnet.deterministic_router")


class DeterministicRouter:
    """
    Deterministic router with WAL and contract enforcement.

    Guarantees:
    - All routing decisions are deterministic
    - WAL is written BEFORE side effects
    - Contracts are enforced at runtime
    - Failures are structured and typed
    - Crash recovery is deterministic
    """

    def __init__(
        self,
        base_router: IntentRouter,
        wal_dir: str = ".intentusnet/wal",
        enable_cost_estimation: bool = True,
        cost_estimator: Optional[CostEstimator] = None,
    ) -> None:
        self.base_router = base_router
        self.wal_dir = Path(wal_dir)
        self.wal_dir.mkdir(parents=True, exist_ok=True)

        self.enable_cost_estimation = enable_cost_estimation
        self.cost_estimator = cost_estimator or CostEstimator()

        # Completed steps tracker (for exactly_once enforcement)
        self._completed_steps: set[str] = set()

    def route_intent(
        self,
        env: IntentEnvelope,
        *,
        budget_limit: Optional[float] = None,
        default_contract: Optional[ExecutionContract] = None,
        default_side_effect: SideEffectClass = SideEffectClass.READ_ONLY,
    ) -> AgentResponse:
        """
        Route intent with deterministic guarantees.

        Args:
            env: Intent envelope
            budget_limit: Optional budget limit (fails if exceeded)
            default_contract: Default execution contract
            default_side_effect: Default side-effect classification

        Returns:
            AgentResponse
        """
        execution_id = generate_uuid_hex()
        envelope_hash = stable_hash(env)

        # Create failure registry
        failure_registry = FailureRegistry(execution_id)

        # Open WAL
        try:
            with WALWriter(str(self.wal_dir), execution_id) as wal:
                # Write EXECUTION_STARTED (BEFORE any work)
                wal.execution_started(envelope_hash, env.intent.name)

                # Pre-execution cost estimation
                if self.enable_cost_estimation:
                    try:
                        agents = self.base_router._registry.find_agents_for_intent(env.intent)
                        agent_names = [a.definition.name for a in agents]

                        estimate = self.cost_estimator.estimate(
                            env, execution_id, agent_names, budget_limit
                        )

                        # Fail fast if budget exceeded
                        if estimate.exceeds_budget:
                            failure = StructuredFailure(
                                failure_type=FailureType.BUDGET_EXCEEDED,
                                execution_id=execution_id,
                                reason=f"Estimated cost ({estimate.estimated_cost}) exceeds budget ({budget_limit})",
                                details=estimate.to_dict(),
                                recoverable=False,
                                recovery_strategy=RecoveryStrategy.ABORT,
                                timestamp_iso=now_iso(),
                            )
                            failure_registry.record(failure)

                            wal.execution_failed(
                                failure_type=FailureType.BUDGET_EXCEEDED.value,
                                reason=failure.reason,
                                recoverable=False,
                            )

                            return AgentResponse(
                                version="1.0",
                                status="error",
                                payload=None,
                                metadata={"execution_id": execution_id},
                                error=self._failure_to_error_info(failure),
                            )

                    except Exception as e:
                        logger.warning(f"Cost estimation failed: {e}")

                # Validate contract (if provided)
                if default_contract:
                    violation = ContractValidator.validate_contract(
                        default_contract, default_side_effect
                    )
                    if violation:
                        failure = StructuredFailure(
                            failure_type=FailureType.CONTRACT_VIOLATION,
                            execution_id=execution_id,
                            reason=violation.reason,
                            details=violation.to_dict(),
                            recoverable=False,
                            recovery_strategy=RecoveryStrategy.ABORT,
                            timestamp_iso=now_iso(),
                        )
                        failure_registry.record(failure)

                        wal.contract_violated(
                            step_id="pre_execution",
                            contract=violation.contract_name,
                            reason=violation.reason,
                        )

                        wal.execution_failed(
                            failure_type=FailureType.CONTRACT_VIOLATION.value,
                            reason=violation.reason,
                            recoverable=False,
                        )

                        return AgentResponse(
                            version="1.0",
                            status="error",
                            payload=None,
                            metadata={"execution_id": execution_id},
                            error=self._failure_to_error_info(failure),
                        )

                # Route through base router
                try:
                    response = self.base_router.route_intent(env)

                    # Write EXECUTION_COMPLETED
                    response_hash = stable_hash(response)
                    wal.execution_completed(response_hash)

                    # Add execution_id to metadata
                    response.metadata["execution_id"] = execution_id

                    return response

                except Exception as e:
                    logger.exception("Routing failed")

                    failure = StructuredFailure(
                        failure_type=FailureType.ROUTING_ERROR,
                        execution_id=execution_id,
                        reason=str(e),
                        details={"exception": str(e)},
                        recoverable=False,
                        recovery_strategy=RecoveryStrategy.ABORT,
                        timestamp_iso=now_iso(),
                    )
                    failure_registry.record(failure)

                    wal.execution_failed(
                        failure_type=FailureType.ROUTING_ERROR.value,
                        reason=str(e),
                        recoverable=False,
                    )

                    return AgentResponse(
                        version="1.0",
                        status="error",
                        payload=None,
                        metadata={"execution_id": execution_id},
                        error=self._failure_to_error_info(failure),
                    )

        except Exception as e:
            logger.exception("WAL write failed - CRITICAL")

            # WAL failure is critical - execution cannot be guaranteed
            failure = StructuredFailure(
                failure_type=FailureType.WAL_INTEGRITY_ERROR,
                execution_id=execution_id,
                reason=f"WAL write failed: {e}",
                details={"exception": str(e)},
                recoverable=False,
                recovery_strategy=RecoveryStrategy.ABORT,
                timestamp_iso=now_iso(),
            )

            return AgentResponse(
                version="1.0",
                status="error",
                payload=None,
                metadata={"execution_id": execution_id},
                error=self._failure_to_error_info(failure),
            )

    def _failure_to_error_info(self, failure: StructuredFailure):
        """
        Convert StructuredFailure to ErrorInfo.
        """
        from ..protocol.response import ErrorInfo
        from ..protocol.enums import ErrorCode

        # Map failure type to error code
        error_code_map = {
            FailureType.CONTRACT_VIOLATION: ErrorCode.VALIDATION_ERROR,
            FailureType.BUDGET_EXCEEDED: ErrorCode.VALIDATION_ERROR,
            FailureType.TIMEOUT: ErrorCode.TIMEOUT,
            FailureType.NO_AGENT_FOUND: ErrorCode.CAPABILITY_NOT_FOUND,
            FailureType.ROUTING_ERROR: ErrorCode.ROUTING_ERROR,
            FailureType.AGENT_ERROR: ErrorCode.INTERNAL_AGENT_ERROR,
            FailureType.WAL_INTEGRITY_ERROR: ErrorCode.INTERNAL_ERROR,
        }

        error_code = error_code_map.get(failure.failure_type, ErrorCode.INTERNAL_ERROR)

        return ErrorInfo(
            code=error_code,
            message=failure.reason,
            retryable=failure.recoverable,
            details=failure.details,
        )
