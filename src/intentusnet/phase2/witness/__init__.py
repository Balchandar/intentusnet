"""
Witness Gateway Module (Phase II)

Witness gateways provide independent verification of executions
without the ability to create new executions.

Key concepts:
- Witness-only role (no execution creation)
- Deterministic verification only (no decryption)
- Witness attestation records
- Multi-witness quorum enforcement
- Gateway policy enforcement using witness attestations
"""

from intentusnet.phase2.witness.attestation import (
    WitnessGateway,
    WitnessAttestation,
    WitnessScope,
    WitnessQuorum,
    WitnessQuorumPolicy,
    QuorumState,
    WitnessRole,
)

__all__ = [
    "WitnessGateway",
    "WitnessAttestation",
    "WitnessScope",
    "WitnessQuorum",
    "WitnessQuorumPolicy",
    "QuorumState",
    "WitnessRole",
]
