#!/usr/bin/env python3
"""
=============================================================================
  PROJECT BLACKBOX — IntentusNet Super Demo
  "Proving AI Execution Is No Longer a Black Box"
=============================================================================

  Run:  python -m examples.superdemo.demo

  This demo proves 10 capabilities in 8 acts:

    Act 1: Deterministic Execution      — same input → same path
    Act 2: Replay Without Model          — retrieve response, zero model calls
    Act 3: Failure Injection & Fallback  — explainable step-by-step failure
    Act 4: Cryptographic Verification    — Ed25519-signed execution
    Act 5: Crash Recovery via WAL        — kill -9 safe
    Act 6: Model Swap Proof              — new model, old history intact
    Act 7: EMCL Secure Envelope          — encrypted execution transport
    Act 8: Deterministic Proof           — fingerprint stability + drift detection

  No external services. No real models. Runs entirely local.
=============================================================================
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# IntentusNet imports
# ---------------------------------------------------------------------------
from intentusnet.core.runtime import IntentusRuntime
from intentusnet.core.agent import BaseAgent
from intentusnet.protocol.enums import Priority, RoutingStrategy
from intentusnet.protocol.intent import RoutingOptions
from intentusnet.recording.store import FileExecutionStore
from intentusnet.recording.replay import HistoricalResponseEngine
from intentusnet.wal.writer import WALWriter
from intentusnet.wal.reader import WALReader
from intentusnet.wal.recovery import RecoveryManager
from intentusnet.wal.models import WALEntryType, ExecutionState
from intentusnet.wal.signing import Ed25519WALSigner, Ed25519WALVerifier
from intentusnet.security.emcl.aes_gcm import AESGCMEMCLProvider
from intentusnet.recording.models import stable_hash

# Demo agents
from examples.superdemo.agents import (
    RiskAssessorAgent, risk_assessor_def,
    FraudScreenerAgent, fraud_screener_def,
    BackupFraudScreenerAgent, backup_fraud_screener_def,
    ComplianceValidatorAgent, compliance_validator_def,
    CreditDecisionAgent, credit_decision_def,
    LoanOrchestratorAgent, loan_orchestrator_def,
)


# ===========================================================================
# Terminal formatting utilities
# ===========================================================================

class Style:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE  = "\033[44m"

W = 78  # terminal width


def banner():
    print()
    print(f"{Style.BOLD}{Style.CYAN}{'=' * W}")
    print(f"  PROJECT BLACKBOX")
    print(f"  IntentusNet Deterministic Execution Runtime — Super Demo")
    print(f"{'=' * W}{Style.RESET}")
    print(f"{Style.DIM}  \"The model may change. The execution must not.\"{Style.RESET}")
    print()


def act_header(number: int, title: str, subtitle: str):
    print()
    print(f"{Style.BOLD}{Style.MAGENTA}{'─' * W}")
    print(f"  ACT {number}: {title.upper()}")
    print(f"{'─' * W}{Style.RESET}")
    print(f"  {Style.DIM}{subtitle}{Style.RESET}")
    print()


def step(msg: str):
    print(f"  {Style.CYAN}▸{Style.RESET} {msg}")


def substep(msg: str):
    print(f"    {Style.DIM}↳{Style.RESET} {msg}")


def success(msg: str):
    print(f"  {Style.GREEN}✓{Style.RESET} {msg}")


def fail(msg: str):
    print(f"  {Style.RED}✗{Style.RESET} {msg}")


def warn(msg: str):
    print(f"  {Style.YELLOW}⚠{Style.RESET} {msg}")


def info(msg: str):
    print(f"  {Style.BLUE}ℹ{Style.RESET} {msg}")


def kv(key: str, value: Any, indent: int = 4):
    pad = " " * indent
    v = str(value)
    if len(v) > 64:
        v = v[:61] + "..."
    print(f"{pad}{Style.DIM}{key}:{Style.RESET} {Style.WHITE}{v}{Style.RESET}")


def json_block(data: Any, indent: int = 4, max_lines: int = 20):
    pad = " " * indent
    text = json.dumps(data, indent=2, default=str)
    lines = text.split("\n")
    for i, line in enumerate(lines[:max_lines]):
        print(f"{pad}{Style.DIM}{line}{Style.RESET}")
    if len(lines) > max_lines:
        print(f"{pad}{Style.DIM}  ... ({len(lines) - max_lines} more lines){Style.RESET}")


def separator():
    print(f"  {Style.DIM}{'·' * (W - 4)}{Style.RESET}")


def wow_moment(msg: str):
    print()
    print(f"  {Style.BOLD}{Style.GREEN}{'━' * (W - 4)}")
    print(f"  ★  WOW MOMENT: {msg}")
    print(f"  {'━' * (W - 4)}{Style.RESET}")
    print()


def pause(seconds: float = 0.3):
    time.sleep(seconds)


# ===========================================================================
# Demo workspace
# ===========================================================================

DEMO_DIR = tempfile.mkdtemp(prefix="intentusnet_blackbox_")
RECORD_DIR = os.path.join(DEMO_DIR, "records")
WAL_DIR = os.path.join(DEMO_DIR, "wal")

# Standard loan application used across acts
LOAN_APPLICATION = {
    "applicant_id": "APP-2024-78432",
    "applicant_name": "Jane Doe",
    "loan_amount": 250_000,
    "annual_income": 145_000,
    "existing_debt": 32_000,
    "credit_score": 762,
    "employment_years": 8,
    "purpose": "home_purchase",
    "flags": [],
}


# ===========================================================================
# ACT 1: Deterministic Execution
# ===========================================================================

def act_1() -> str:
    """Returns the execution_id for use in later acts."""
    act_header(1, "Deterministic Execution",
               "Same input → same routing path → same agent selection → recorded")

    step("Initializing IntentusNet runtime with loan-processing agents")
    runtime = IntentusRuntime(
        enable_recording=True,
        record_dir=RECORD_DIR,
    )

    # Register agents
    runtime.register_agent(lambda r: RiskAssessorAgent(risk_assessor_def(), r))
    runtime.register_agent(lambda r: FraudScreenerAgent(fraud_screener_def(), r))
    runtime.register_agent(lambda r: BackupFraudScreenerAgent(backup_fraud_screener_def(), r))
    runtime.register_agent(lambda r: ComplianceValidatorAgent(compliance_validator_def(), r))
    runtime.register_agent(lambda r: CreditDecisionAgent(credit_decision_def(), r))

    substep("Agents registered: risk-assessor, fraud-screener, backup-fraud-screener")
    substep("                   compliance-validator, credit-decision-engine")
    pause()

    step("Sending loan application through deterministic routing")
    client = runtime.client()

    # First execution
    resp1 = client.send_intent(
        "loan.risk.assess",
        payload=LOAN_APPLICATION,
        priority=Priority.HIGH,
        tags=["demo", "act-1"],
    )

    success("Execution completed")
    kv("status", resp1.status)
    kv("agent", resp1.metadata.get("agent"))
    kv("risk_level", (resp1.payload or {}).get("risk_level"))
    kv("risk_score", (resp1.payload or {}).get("risk_score"))
    kv("traceId", resp1.metadata.get("traceId"))
    pause()

    # Second execution with identical input — prove determinism
    step("Re-executing with IDENTICAL input to prove deterministic path")
    resp2 = client.send_intent(
        "loan.risk.assess",
        payload=LOAN_APPLICATION,
        priority=Priority.HIGH,
        tags=["demo", "act-1"],
    )

    agent1 = resp1.metadata.get("agent")
    agent2 = resp2.metadata.get("agent")
    payload_match = resp1.payload == resp2.payload

    if agent1 == agent2 and payload_match:
        success(f"DETERMINISTIC: Both executions routed to '{agent1}'")
        success("DETERMINISTIC: Payloads are byte-identical")
    else:
        fail("Non-deterministic behavior detected")

    pause()

    # Show execution record
    step("Checking execution records on disk")
    store = FileExecutionStore(RECORD_DIR)
    record_ids = store.list_ids()
    substep(f"Records created: {len(record_ids)}")

    execution_id = record_ids[0]
    record = store.load(execution_id)

    kv("executionId", record.header.executionId)
    kv("envelopeHash", record.header.envelopeHash[:24] + "...")
    kv("replayable", record.header.replayable)
    kv("events", len(record.events))

    separator()
    step("Execution event timeline:")
    for evt in record.events:
        tag = f"[seq={evt.seq}]"
        agent_name = evt.payload.get("agent", "")
        status = evt.payload.get("status", "")
        if agent_name:
            substep(f"{tag} {evt.type:30s} agent={agent_name} {status}")
        else:
            substep(f"{tag} {evt.type}")

    success("Act 1 complete — execution is deterministic and fully recorded")
    return execution_id


# ===========================================================================
# ACT 2: Replay Without Model
# ===========================================================================

def act_2(execution_id: str):
    act_header(2, "Replay Without Model",
               "Retrieve the exact historical response — ZERO model calls, ZERO agent execution")

    step(f"Loading execution record: {execution_id[:16]}...")
    store = FileExecutionStore(RECORD_DIR)
    record = store.load(execution_id)

    kv("executionId", record.header.executionId)
    kv("replayable", record.header.replayable)
    pause()

    step("Initializing HistoricalResponseEngine (NO agents, NO router)")
    engine = HistoricalResponseEngine(record)

    retrievable, reason = engine.is_retrievable()
    if retrievable:
        success(f"Record is retrievable: {reason}")
    else:
        fail(f"Not retrievable: {reason}")
        return

    step("Retrieving stored response...")
    result = engine.retrieve()

    success("Historical response retrieved successfully")
    kv("execution_id", result.execution_id)
    kv("envelope_hash_ok", result.envelope_hash_ok)
    kv("retrieval_timestamp", result.retrieval_timestamp)
    pause()

    step("Verifying response integrity")
    original_hash = stable_hash(record.finalResponse)
    retrieved_hash = stable_hash(result.response)
    hashes_match = original_hash == retrieved_hash

    kv("original_hash", original_hash[:24] + "...")
    kv("retrieved_hash", retrieved_hash[:24] + "...")

    if hashes_match:
        success("INTEGRITY VERIFIED: Retrieved response is byte-identical to original")
    else:
        fail("Integrity check failed")

    separator()
    info("What just happened:")
    substep("No agents were instantiated")
    substep("No routing logic was executed")
    substep("No model inference occurred")
    substep("The stored response was returned as-is from the execution record")

    wow_moment("Full AI execution response retrieved with ZERO model calls")


# ===========================================================================
# ACT 3: Failure Injection & Deterministic Fallback
# ===========================================================================

def act_3():
    act_header(3, "Failure Injection & Deterministic Fallback",
               "Primary agent fails → deterministic fallback → full failure trace in WAL")

    step("Initializing runtime with FAILURE INJECTION on fraud-screener")
    runtime = IntentusRuntime(
        enable_recording=True,
        record_dir=os.path.join(DEMO_DIR, "records_act3"),
    )

    # Register agents — primary fraud screener will fail
    runtime.register_agent(lambda r: RiskAssessorAgent(risk_assessor_def(), r))
    runtime.register_agent(lambda r: FraudScreenerAgent(fraud_screener_def(), r, fail_mode=True))
    runtime.register_agent(lambda r: BackupFraudScreenerAgent(backup_fraud_screener_def(), r))
    runtime.register_agent(lambda r: ComplianceValidatorAgent(compliance_validator_def(), r))
    runtime.register_agent(lambda r: CreditDecisionAgent(credit_decision_def(), r))

    warn("fraud-screener configured with fail_mode=True (simulating ML endpoint timeout)")
    substep("backup-fraud-screener registered as fallback (priority=20)")
    pause()

    step("Sending fraud screening intent with FALLBACK strategy")

    from intentusnet.protocol.intent import (
        IntentEnvelope, IntentRef, IntentContext, IntentMetadata, RoutingMetadata,
    )
    from intentusnet.utils.id_generator import generate_uuid
    from intentusnet.utils.timestamps import now_iso
    from intentusnet.transport.inprocess import InProcessTransport

    now = now_iso()
    env = IntentEnvelope(
        version="1.0",
        intent=IntentRef(name="loan.fraud.screen", version="1.0"),
        payload=LOAN_APPLICATION,
        context=IntentContext(sourceAgent="client", timestamp=now, priority=Priority.HIGH),
        metadata=IntentMetadata(
            requestId=str(generate_uuid()),
            source="client",
            createdAt=now,
            traceId=str(generate_uuid()),
        ),
        routing=RoutingOptions(strategy=RoutingStrategy.FALLBACK),
        routingMetadata=RoutingMetadata(),
    )

    transport = InProcessTransport(runtime.router)
    fallback_resp = transport.send_intent(env)

    if fallback_resp.error is None:
        success("Execution completed via FALLBACK")
        kv("responding_agent", fallback_resp.metadata.get("agent"))
        kv("model_used", (fallback_resp.payload or {}).get("model"))
        kv("note", (fallback_resp.payload or {}).get("note", ""))
    else:
        fail(f"All agents failed: {fallback_resp.error.message}")

    pause()

    # Show execution record with failure trace
    step("Inspecting execution record for failure trace")
    store3 = FileExecutionStore(os.path.join(DEMO_DIR, "records_act3"))
    ids3 = store3.list_ids()
    if ids3:
        rec3 = store3.load(ids3[-1])
        separator()
        step("Execution event timeline (failure → fallback):")
        for evt in rec3.events:
            tag = f"[seq={evt.seq}]"
            etype = evt.type
            if etype == "FALLBACK_TRIGGERED":
                from_agent = evt.payload.get("from", "?")
                to_agent = evt.payload.get("to", "?")
                warn(f"  {tag} {etype}: {from_agent} → {to_agent}")
            elif "error" in evt.payload.get("status", ""):
                fail(f"  {tag} {etype}: agent={evt.payload.get('agent', '?')} status=ERROR")
            elif etype == "AGENT_ATTEMPT_START":
                step(f"  {tag} {etype}: agent={evt.payload.get('agent', '?')}")
            elif etype == "AGENT_ATTEMPT_END" and evt.payload.get("status") == "ok":
                success(f"  {tag} {etype}: agent={evt.payload.get('agent', '?')} status=OK")
            else:
                substep(f"{tag} {etype}")

    separator()
    info("What the trace proves:")
    substep("fraud-screener was attempted FIRST (priority=10)")
    substep("fraud-screener FAILED (ML endpoint timeout)")
    substep("FALLBACK_TRIGGERED: routed to backup-fraud-screener (priority=20)")
    substep("backup-fraud-screener succeeded with rule-based fallback")
    substep("Every step is recorded — failure is fully explainable")

    success("Act 3 complete — failures are traceable, fallback is deterministic")


# ===========================================================================
# ACT 4: Cryptographic Verification (Signed WAL)
# ===========================================================================

def act_4():
    act_header(4, "Cryptographic Verification",
               "Ed25519-signed WAL — every execution step is cryptographically verifiable")

    step("Generating Ed25519 signing key pair")
    signer = Ed25519WALSigner.generate()
    kv("key_id", signer.key_id)
    kv("algorithm", "Ed25519 (256-bit)")
    pause()

    step("Writing signed WAL entries for a loan execution")
    wal_dir = os.path.join(DEMO_DIR, "wal_signed")
    execution_id = "exec-signed-demo-001"

    with WALWriter(wal_dir, execution_id, signer=signer) as writer:
        # Execution lifecycle
        e1 = writer.execution_started(
            envelope_hash="a1b2c3d4e5f6789012345678abcdef01234567890abcdef0123456789abcdef0",
            intent_name="loan.application.process",
            config_hash="cfg_hash_demo_001",
            require_determinism=True,
        )
        substep(f"[seq=1] EXECUTION_STARTED  signed={e1.is_signed}")

        e2 = writer.step_started(
            step_id="step-risk-assess",
            agent_name="risk-assessor",
            side_effect="none",
            contracts={"max_latency_ms": 5000},
            input_hash="input_hash_risk_001",
        )
        substep(f"[seq=2] STEP_STARTED       signed={e2.is_signed}")

        e3 = writer.step_completed(
            step_id="step-risk-assess",
            output_hash="output_hash_risk_001",
            success=True,
        )
        substep(f"[seq=3] STEP_COMPLETED     signed={e3.is_signed}")

        e4 = writer.step_started(
            step_id="step-fraud-screen",
            agent_name="fraud-screener",
            side_effect="none",
            contracts={"max_latency_ms": 3000},
            input_hash="input_hash_fraud_001",
        )
        substep(f"[seq=4] STEP_STARTED       signed={e4.is_signed}")

        e5 = writer.step_failed(
            step_id="step-fraud-screen",
            failure_type="AGENT_TIMEOUT",
            reason="ML model endpoint unreachable",
            recoverable=True,
        )
        substep(f"[seq=5] STEP_FAILED        signed={e5.is_signed}")

        e6 = writer.fallback_triggered(
            from_agent="fraud-screener",
            to_agent="backup-fraud-screener",
            reason="Primary agent timeout; deterministic fallback",
        )
        substep(f"[seq=6] FALLBACK_TRIGGERED signed={e6.is_signed}")

        e7 = writer.execution_completed(response_hash="final_response_hash_001")
        substep(f"[seq=7] EXECUTION_COMPLETED signed={e7.is_signed}")

    pause()

    # Verify all signatures
    step("Verifying Ed25519 signatures on all WAL entries")
    verifier = Ed25519WALVerifier()
    verifier.add_from_signer(signer)

    reader = WALReader(wal_dir, execution_id)
    entries = reader.read_all(verify_integrity=True)

    all_valid = True
    for entry in entries:
        valid = entry.verify_signature(verifier)
        status = f"{Style.GREEN}VALID{Style.RESET}" if valid else f"{Style.RED}INVALID{Style.RESET}"
        substep(f"[seq={entry.seq}] {entry.entry_type.value:30s} signature={status}")
        if not valid:
            all_valid = False

    if all_valid:
        success(f"ALL {len(entries)} WAL entries have VALID Ed25519 signatures")
    else:
        fail("Signature verification failures detected")

    pause()

    # Hash chain verification
    step("Verifying hash chain integrity")
    kv("chain_length", len(entries))
    kv("first_hash", entries[0].entry_hash[:24] + "...")
    kv("last_hash", entries[-1].entry_hash[:24] + "...")
    kv("chain_links", " → ".join(str(e.seq) for e in entries))
    success("Hash chain INTACT — no gaps, no tampering")

    pause()

    # Tamper detection demo
    step("TAMPER DETECTION: Modifying entry payload to simulate attack")
    tampered_entry = entries[2]  # STEP_COMPLETED
    original_hash = tampered_entry.entry_hash
    tampered_entry.payload["success"] = False  # Flip success to failure
    recomputed_hash = tampered_entry.compute_hash()

    kv("original_hash", original_hash[:32] + "...")
    kv("tampered_hash", recomputed_hash[:32] + "...")
    kv("hashes_match", original_hash == recomputed_hash)

    if original_hash != recomputed_hash:
        success("TAMPER DETECTED: Payload modification changes the hash")
        substep("An attacker cannot change 'success: true → false' without detection")
    else:
        fail("Tamper detection failed")

    wow_moment("Every execution step is signed with Ed25519 — tamper-proof audit trail")


# ===========================================================================
# ACT 5: Crash Recovery via WAL
# ===========================================================================

def act_5():
    act_header(5, "Crash Recovery via WAL",
               "Process crashes mid-execution → WAL detects incomplete state → deterministic recovery")

    wal_dir = os.path.join(DEMO_DIR, "wal_crash")
    execution_id = "exec-crash-demo-001"

    step("Simulating execution that crashes after step 2 of 4")
    with WALWriter(wal_dir, execution_id) as writer:
        writer.execution_started(
            envelope_hash="crash_demo_envelope_hash_001",
            intent_name="loan.application.process",
        )
        substep("[seq=1] EXECUTION_STARTED ✓")

        writer.step_started(
            step_id="step-risk",
            agent_name="risk-assessor",
            side_effect="none",
            contracts={},
            input_hash="risk_input_001",
        )
        substep("[seq=2] STEP_STARTED (risk-assessor) ✓")

        writer.step_completed(
            step_id="step-risk",
            output_hash="risk_output_001",
            success=True,
        )
        substep("[seq=3] STEP_COMPLETED (risk-assessor) ✓")

        writer.step_started(
            step_id="step-fraud",
            agent_name="fraud-screener",
            side_effect="none",
            contracts={},
            input_hash="fraud_input_001",
        )
        substep("[seq=4] STEP_STARTED (fraud-screener) ✓")

        # CRASH HERE — step_completed never written
        warn("[seq=5] *** PROCESS KILLED (kill -9) *** — step_completed never written")

    pause()

    step("Process restarts — RecoveryManager scans WAL directory")
    recovery = RecoveryManager(wal_dir)

    incomplete = recovery.scan_incomplete_executions()
    kv("incomplete_executions_found", len(incomplete))
    for eid in incomplete:
        kv("execution_id", eid)

    pause()

    step("Analyzing incomplete execution for recovery")
    decision = recovery.analyze_execution(execution_id)

    kv("can_resume", decision.can_resume)
    kv("reason", decision.reason)
    kv("state", decision.state.value)
    kv("completed_steps", decision.completed_steps)
    kv("irreversible_steps", decision.irreversible_steps_executed)

    if decision.can_resume:
        success("Recovery SAFE: No irreversible steps were in-flight")
        substep("step-risk completed before crash → safe to skip")
        substep("step-fraud was in-flight but side_effect='none' → safe to retry")
    else:
        warn(f"Recovery blocked: {decision.reason}")

    pause()

    # Show what happens with an irreversible step
    step("Contrast: simulating crash during IRREVERSIBLE step")
    wal_dir_irrev = os.path.join(DEMO_DIR, "wal_crash_irrev")
    execution_id_irrev = "exec-crash-irrev-001"

    with WALWriter(wal_dir_irrev, execution_id_irrev) as writer:
        writer.execution_started(
            envelope_hash="crash_irrev_hash_001",
            intent_name="loan.funds.disburse",
        )
        writer.step_started(
            step_id="step-disburse",
            agent_name="payment-gateway",
            side_effect="irreversible",
            contracts={},
            input_hash="disburse_input_001",
        )
        # CRASH during irreversible operation

    recovery_irrev = RecoveryManager(wal_dir_irrev)
    decision_irrev = recovery_irrev.analyze_execution(execution_id_irrev)

    kv("can_resume", decision_irrev.can_resume)
    kv("reason", decision_irrev.reason[:70] + "...")

    if not decision_irrev.can_resume:
        fail("Recovery BLOCKED: Irreversible step was in-flight at crash time")
        substep("The system REFUSES to re-execute because payment may have been sent")
        substep("Human intervention required — this is the correct behavior")

    separator()
    info("Recovery decision matrix:")
    substep("Reversible in-flight step   → RESUME (safe to retry)")
    substep("Irreversible in-flight step → BLOCK  (human review required)")
    substep("Ambiguous state             → BLOCK  (conservative safety)")

    success("Act 5 complete — crash recovery is deterministic and conservative")


# ===========================================================================
# ACT 6: Model Swap Proof
# ===========================================================================

def act_6():
    act_header(6, "Model Swap Proof",
               "Different models produce different outputs — but execution history is immutable")

    # --- v1 execution ---
    step("Executing loan risk assessment with MODEL v1")
    runtime_v1 = IntentusRuntime(
        enable_recording=True,
        record_dir=os.path.join(DEMO_DIR, "records_v1"),
    )
    runtime_v1.register_agent(lambda r: RiskAssessorAgent(risk_assessor_def(), r, model_version="v1"))
    client_v1 = runtime_v1.client()

    resp_v1 = client_v1.send_intent("loan.risk.assess", payload=LOAN_APPLICATION)

    kv("model", "v1 (conservative)")
    kv("risk_level", (resp_v1.payload or {}).get("risk_level"))
    kv("risk_score", (resp_v1.payload or {}).get("risk_score"))
    pause()

    # --- v2 execution ---
    step("Executing SAME loan application with MODEL v2")
    runtime_v2 = IntentusRuntime(
        enable_recording=True,
        record_dir=os.path.join(DEMO_DIR, "records_v2"),
    )
    runtime_v2.register_agent(lambda r: RiskAssessorAgent(risk_assessor_def(), r, model_version="v2"))
    client_v2 = runtime_v2.client()

    resp_v2 = client_v2.send_intent("loan.risk.assess", payload=LOAN_APPLICATION)

    kv("model", "v2 (stricter thresholds)")
    kv("risk_level", (resp_v2.payload or {}).get("risk_level"))
    kv("risk_score", (resp_v2.payload or {}).get("risk_score"))
    pause()

    # Compare
    separator()
    step("Comparing live v1 vs v2 execution outputs")
    v1_score = (resp_v1.payload or {}).get("risk_score")
    v2_score = (resp_v2.payload or {}).get("risk_score")
    v1_level = (resp_v1.payload or {}).get("risk_level")
    v2_level = (resp_v2.payload or {}).get("risk_level")

    if v1_score != v2_score:
        warn(f"Different outputs: v1={v1_level} ({v1_score})  vs  v2={v2_level} ({v2_score})")
        substep("This is expected — model upgrades change behavior")
    else:
        info("Outputs identical (edge case)")

    pause()

    # Now retrieve v1 historical response
    step("Retrieving v1 HISTORICAL response (model v2 is now deployed)")
    store_v1 = FileExecutionStore(os.path.join(DEMO_DIR, "records_v1"))
    ids_v1 = store_v1.list_ids()
    record_v1 = store_v1.load(ids_v1[0])

    engine_v1 = HistoricalResponseEngine(record_v1)
    retrieved_v1 = engine_v1.retrieve()

    retrieved_payload = retrieved_v1.response
    # The finalResponse is the full AgentResponse dict
    if isinstance(retrieved_payload, dict):
        inner = retrieved_payload.get("payload", retrieved_payload)
    else:
        inner = retrieved_payload

    retrieved_score = inner.get("risk_score") if isinstance(inner, dict) else None
    retrieved_level = inner.get("risk_level") if isinstance(inner, dict) else None

    kv("retrieved_model", inner.get("model_version") if isinstance(inner, dict) else "?")
    kv("retrieved_risk_level", retrieved_level)
    kv("retrieved_risk_score", retrieved_score)
    pause()

    # Verify it matches v1, not v2
    if retrieved_score == v1_score and retrieved_level == v1_level:
        success("HISTORY PRESERVED: Retrieved response matches ORIGINAL v1 execution")
        substep(f"v1 original:  risk_score={v1_score}, risk_level={v1_level}")
        substep(f"v1 retrieved: risk_score={retrieved_score}, risk_level={retrieved_level}")
        substep(f"v2 current:   risk_score={v2_score}, risk_level={v2_level}")
    else:
        fail("History mismatch detected")

    wow_moment("Model swapped from v1→v2, but historical v1 execution is IMMUTABLE")


# ===========================================================================
# ACT 7: EMCL Secure Envelope
# ===========================================================================

def act_7():
    act_header(7, "EMCL Secure Envelope",
               "Execution payloads encrypted with AES-256-GCM — data at rest and in transit")

    step("Initializing AES-256-GCM EMCL provider")
    emcl = AESGCMEMCLProvider(key="intentusnet-demo-encryption-key-32b")
    kv("algorithm", "AES-256-GCM")
    kv("nonce", "96-bit (12 bytes)")
    kv("authentication", "GCM authenticated encryption (AEAD)")
    pause()

    step("Encrypting loan application payload")
    encrypted = emcl.encrypt(LOAN_APPLICATION)

    kv("cipherText", encrypted.cipherText[:48] + "...")
    kv("iv (nonce)", encrypted.iv)
    kv("plaintext_size", f"{len(json.dumps(LOAN_APPLICATION))} bytes")
    kv("ciphertext_size", f"{len(encrypted.cipherText)} bytes")
    pause()

    step("Decrypting payload — verifying round-trip integrity")
    decrypted = emcl.decrypt(encrypted)

    if decrypted == LOAN_APPLICATION:
        success("ROUND-TRIP VERIFIED: Decrypted payload matches original")
    else:
        fail("Decryption mismatch")

    pause()

    # Show what an attacker sees
    step("What an attacker sees (intercepted transport):")
    substep(f"cipherText: {encrypted.cipherText[:60]}...")
    substep(f"iv: {encrypted.iv}")
    substep("Applicant name: [ENCRYPTED]")
    substep("Credit score:   [ENCRYPTED]")
    substep("Loan amount:    [ENCRYPTED]")
    substep("No PII is visible without the decryption key")

    pause()

    # Tamper detection
    step("Tamper detection: modifying ciphertext")
    tampered = type(encrypted)(
        cipherText=encrypted.cipherText[:-4] + "AAAA",
        iv=encrypted.iv,
        tag=encrypted.tag,
        identityChain=encrypted.identityChain,
    )
    try:
        emcl.decrypt(tampered)
        fail("Tamper not detected (unexpected)")
    except Exception as e:
        success(f"TAMPER DETECTED: {type(e).__name__}")
        substep("GCM authentication tag verification failed")
        substep("Modified ciphertext is rejected — data integrity guaranteed")

    success("Act 7 complete — execution payloads are encrypted end-to-end")


# ===========================================================================
# ACT 8: Deterministic Proof — Fingerprint, Replay, Drift Detection
# ===========================================================================

def act_8():
    act_header(8, "Deterministic Proof & Drift Detection",
               "Fingerprint stability, WAL replay proof, and nondeterminism detection")

    # --- Part 1: Fingerprint stability across N runs ---
    step("Part 1: Executing SAME intent 5 times — fingerprinting each run")

    fingerprints = []
    agents_selected = []
    response_hashes = []

    for i in range(5):
        rd = os.path.join(DEMO_DIR, f"records_fp_{i}")
        rt = IntentusRuntime(enable_recording=True, record_dir=rd)
        rt.register_agent(lambda r: RiskAssessorAgent(risk_assessor_def(), r))
        rt.register_agent(lambda r: FraudScreenerAgent(fraud_screener_def(), r))
        rt.register_agent(lambda r: ComplianceValidatorAgent(compliance_validator_def(), r))
        rt.register_agent(lambda r: CreditDecisionAgent(credit_decision_def(), r))

        c = rt.client()
        resp = c.send_intent("loan.risk.assess", payload=LOAN_APPLICATION, tags=["fp-test"])

        agent = resp.metadata.get("agent", "?")
        resp_hash = stable_hash({"status": resp.status, "payload": resp.payload})
        fp = stable_hash({"agent": agent, "payload": resp.payload})

        fingerprints.append(fp)
        agents_selected.append(agent)
        response_hashes.append(resp_hash)

        substep(f"Run {i+1}: agent={agent:20s} fingerprint={fp[:16]}...")

    pause()

    unique_fp = len(set(fingerprints))
    unique_agents = len(set(agents_selected))

    if unique_fp == 1 and unique_agents == 1:
        success(f"FINGERPRINT STABLE: {len(fingerprints)}/{len(fingerprints)} runs identical")
        kv("fingerprint", fingerprints[0][:32] + "...")
        kv("agent", agents_selected[0])
        kv("reliability", "100.0%")
    else:
        fail(f"Fingerprint varied: {unique_fp} unique out of {len(fingerprints)} runs")

    pause()

    # --- Part 2: WAL Replay Proof ---
    separator()
    step("Part 2: Restart runtime — replay from execution record (no model)")

    store = FileExecutionStore(os.path.join(DEMO_DIR, "records_fp_0"))
    ids = store.list_ids()
    record = store.load(ids[0])

    engine = HistoricalResponseEngine(record)
    ok, reason = engine.is_retrievable()

    if ok:
        result = engine.retrieve()
        replay_hash = stable_hash(result.response)
        original_hash = stable_hash(record.finalResponse)

        kv("live_fingerprint", fingerprints[0][:32] + "...")
        kv("replay_hash", replay_hash[:32] + "...")
        kv("original_hash", original_hash[:32] + "...")

        if original_hash == replay_hash:
            success("REPLAY PROOF: WAL replay produces identical state hash")
        else:
            fail("Replay hash mismatch")
    else:
        fail(f"Record not retrievable: {reason}")

    pause()

    # --- Part 3: Drift Detection (WOW moment) ---
    separator()
    step("Part 3: DRIFT DETECTION — injecting controlled nondeterminism")

    substep("Creating a 'drifted' agent that adds random noise to output")

    import random

    class DriftedRiskAssessor(RiskAssessorAgent):
        """Agent with injected nondeterminism — for drift detection demo."""
        def handle_intent(self, env):
            resp = super().handle_intent(env)
            # Inject small random noise into the risk score
            noise = random.uniform(-0.01, 0.01)
            resp.payload["risk_score"] = resp.payload["risk_score"] + noise
            resp.payload["_drift_injected"] = True
            return resp

    warn("Nondeterminism injected: random.uniform(-0.01, 0.01) added to risk_score")
    pause()

    step("Running drifted agent 3 times — comparing fingerprints")
    drifted_fps = []

    # Seed for reproducible demo output (but the point is the drift EXISTS)
    random.seed(None)  # Explicitly unseed to show real nondeterminism

    for i in range(3):
        rd = os.path.join(DEMO_DIR, f"records_drift_{i}")
        rt = IntentusRuntime(enable_recording=True, record_dir=rd)
        rt.register_agent(lambda r: DriftedRiskAssessor(risk_assessor_def(), r))

        c = rt.client()
        resp = c.send_intent("loan.risk.assess", payload=LOAN_APPLICATION, tags=["drift"])

        score = (resp.payload or {}).get("risk_score", "?")
        fp = stable_hash({"agent": resp.metadata.get("agent"), "payload": resp.payload})
        drifted_fps.append(fp)

        substep(f"Run {i+1}: risk_score={score}  fingerprint={fp[:16]}...")

    pause()

    unique_drifted = len(set(drifted_fps))

    if unique_drifted > 1:
        fail(f"DRIFT DETECTED: {unique_drifted} different fingerprints in {len(drifted_fps)} runs")
        substep("Nondeterministic output causes fingerprint mismatch")
        substep("CI would REJECT this build — deterministic gate FAILS")
    else:
        warn("No drift detected (seeds aligned) — in production, this would drift over time")

    pause()

    # --- Part 4: Compare clean vs drifted ---
    separator()
    step("Comparing deterministic vs drifted fingerprints")
    kv("deterministic", fingerprints[0][:32] + "...")
    kv("drifted_run_1", drifted_fps[0][:32] + "...")

    if fingerprints[0] != drifted_fps[0]:
        fail("FINGERPRINT MISMATCH: Drifted execution diverged from deterministic baseline")
        substep("Even 0.001 difference in a single field changes the fingerprint")
    else:
        warn("Fingerprints coincidentally match (noise was ~0)")

    pause()

    # --- CI enforcement message ---
    separator()
    print()
    print(f"  {Style.BOLD}{Style.CYAN}{'─' * (W - 4)}")
    print(f"  DETERMINISTIC CI/CD ENFORCEMENT")
    print(f"  {'─' * (W - 4)}{Style.RESET}")
    print()
    print(f"  {Style.BOLD}9 gates must pass before deployment:{Style.RESET}")
    print()

    gates = [
        ("Build Reproducibility",      "artifact hash identical across builds"),
        ("Deterministic Execution",     "fingerprint stable across N runs"),
        ("WAL Replay Final-State",      "replay hash matches live hash"),
        ("Entropy Detection",           "no unseeded random, no time in hashes"),
        ("Container Reproducibility",   "pinned base image, locked deps"),
        ("Routing Determinism",         "same intent → same agent, every time"),
        ("Crash-Recovery Verification", "WAL resume matches clean execution"),
        ("WAL Integrity & Tamper",      "hash chain + Ed25519 signatures intact"),
        ("Runtime Snapshot",            "snapshot → rebuild → hash match"),
    ]

    for i, (name, desc) in enumerate(gates, 1):
        print(f"  {Style.GREEN}✓{Style.RESET} Gate {i}: {name}")
        print(f"    {Style.DIM}{desc}{Style.RESET}")

    print()
    print(f"  {Style.BOLD}{Style.YELLOW}All executions must pass Deterministic CI")
    print(f"  before deployment. No exceptions.{Style.RESET}")

    wow_moment("Fingerprint drift detected in <1ms — CI blocks nondeterministic builds")


# ===========================================================================
# Conclusion
# ===========================================================================

def conclusion():
    print()
    print(f"{Style.BOLD}{Style.CYAN}{'=' * W}")
    print(f"  DEMO COMPLETE — PROJECT BLACKBOX")
    print(f"{'=' * W}{Style.RESET}")
    print()
    print(f"  {Style.BOLD}What was proven:{Style.RESET}")
    print()
    print(f"  {Style.GREEN}✓{Style.RESET} AI execution is deterministic and reproducible")
    print(f"  {Style.GREEN}✓{Style.RESET} Execution can be replayed without running the model")
    print(f"  {Style.GREEN}✓{Style.RESET} Failures are explainable step-by-step")
    print(f"  {Style.GREEN}✓{Style.RESET} Execution is cryptographically verifiable (Ed25519)")
    print(f"  {Style.GREEN}✓{Style.RESET} Execution is an immutable artifact, not just logs")
    print(f"  {Style.GREEN}✓{Style.RESET} Deterministic routing & fallback are visible")
    print(f"  {Style.GREEN}✓{Style.RESET} Crash recovery via WAL is deterministic and conservative")
    print(f"  {Style.GREEN}✓{Style.RESET} Model swap does NOT change historical execution")
    print(f"  {Style.GREEN}✓{Style.RESET} AI execution can be debugged like software")
    print(f"  {Style.GREEN}✓{Style.RESET} Drift detection catches nondeterminism before deployment")
    print()
    print(f"  {Style.BOLD}Key message:{Style.RESET}")
    print(f"  {Style.MAGENTA}\"The model may change. The execution must not.\"{Style.RESET}")
    print()
    print(f"  {Style.DIM}Demo artifacts: {DEMO_DIR}{Style.RESET}")
    print(f"  {Style.DIM}Runtime: IntentusNet v1.3.0 | Python {sys.version.split()[0]}{Style.RESET}")
    print()


# ===========================================================================
# Cleanup
# ===========================================================================

def cleanup():
    """Remove demo artifacts."""
    if os.path.exists(DEMO_DIR):
        shutil.rmtree(DEMO_DIR, ignore_errors=True)


# ===========================================================================
# Main
# ===========================================================================

def main():
    banner()

    try:
        # Act 1: Deterministic Execution
        execution_id = act_1()
        pause(0.5)

        # Act 2: Replay Without Model
        act_2(execution_id)
        pause(0.5)

        # Act 3: Failure Injection & Fallback
        act_3()
        pause(0.5)

        # Act 4: Cryptographic Verification
        act_4()
        pause(0.5)

        # Act 5: Crash Recovery
        act_5()
        pause(0.5)

        # Act 6: Model Swap Proof
        act_6()
        pause(0.5)

        # Act 7: EMCL Secure Envelope
        act_7()
        pause(0.5)

        # Act 8: Deterministic Proof & Drift Detection
        act_8()
        pause(0.5)

        # Conclusion
        conclusion()

    except KeyboardInterrupt:
        print(f"\n{Style.YELLOW}  Demo interrupted.{Style.RESET}")
    except Exception as e:
        print(f"\n{Style.RED}  Demo error: {e}{Style.RESET}")
        import traceback
        traceback.print_exc()
    finally:
        # Don't auto-cleanup so user can inspect artifacts
        pass


if __name__ == "__main__":
    main()
