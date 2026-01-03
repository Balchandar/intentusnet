"""
Contract validation and inspection commands.
"""

import json
import sys
from pathlib import Path

from intentusnet.contracts.validator import ContractValidator
from intentusnet.contracts.models import ExecutionContract, SideEffectClass
from intentusnet.recording.store import FileExecutionStore
from .output import output_json, output_table, get_output_format


def contracts_validate(args) -> None:
    """Validate contract from intent file."""
    intent_path = Path(args.intent_file)

    if not intent_path.exists():
        print(f"Error: Intent file not found: {args.intent_file}", file=sys.stderr)
        sys.exit(1)

    with open(intent_path, "r", encoding="utf-8") as f:
        intent_data = json.load(f)

    # Extract contract and side-effect from intent
    contract_data = intent_data.get("contract", {})
    side_effect = intent_data.get("side_effect", "read_only")

    contract = ExecutionContract.from_dict(contract_data)
    side_effect_class = SideEffectClass(side_effect)

    # Validate
    violation = ContractValidator.validate_contract(contract, side_effect_class)

    if violation:
        result = {
            "valid": False,
            "violation": violation.to_dict(),
        }
        output_json(result)
        sys.exit(1)
    else:
        result = {
            "valid": True,
            "contract": contract.to_dict(),
            "side_effect": side_effect_class.value,
        }
        output_json(result)
        sys.exit(0)


def contracts_show(args) -> None:
    """Show contracts for an execution."""
    # TODO: Extract contracts from execution record/WAL
    contracts_data = {
        "execution_id": args.execution_id,
        "contracts": [],
        "note": "Contract extraction not yet implemented",
    }
    output_json(contracts_data)


def contracts_violations(args) -> None:
    """Show contract violations for an execution."""
    # TODO: Extract contract violations from WAL
    violations_data = {
        "execution_id": args.execution_id,
        "violations": [],
        "note": "Contract violation tracking not yet implemented",
    }
    output_json(violations_data)
