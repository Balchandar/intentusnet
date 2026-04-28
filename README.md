# IntentusNet

### Deterministic runtime for AI systems — trace, replay, and verify every execution

**Deterministic • Observable • Enforceable • MCP-Compatible**

---

## Why does the same AI request give different answers?

You can’t replay it.
You can’t diff it.
You can’t prove what happened.

IntentusNet fixes that.

It adds determinism, observability, and enforcement to AI execution —
so every run can be traced, replayed, and verified.

---

[![Version](https://img.shields.io/badge/version-1.5.1-blue.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](#)
[![MCP](https://img.shields.io/badge/MCP-compatible-brightgreen)](#)

---

## What’s New in v1.5.1

* Execution fingerprinting (SHA-256)
* Drift detection
* Deterministic-safe CI/CD (9-gate validation)
* WAL replay verification

---

## What is IntentusNet?

IntentusNet is a runtime layer for AI execution.

It does **not** replace your models or agents.
It sits underneath them and ensures execution is:

* observable
* replayable
* enforceable

> **IntentusNet is NOT an LLM framework.**
> It does not handle prompting, reasoning, or planning.
> It focuses purely on execution — making what runs *traceable, replayable, and verifiable*.

---

## 🔥 Four-Act Demo

This is the difference between a black-box AI system and a verifiable one.

```bash id="4rsyfb"
PYTHONPATH=src python demo/run_demo.py
```

---

### Act 1 — Baseline

```id="q6r2j9"
[!] No trace  
[!] No replay  
[!] No explanation  
```

---

### Act 2 — IntentusNet

```id="v3b1xv"
Trace: intent → planner → tool  

Signals:  
latency / error / behavior / policy  

Enforcement:  
circuit_state: CLOSED  
```

---

### Act 3 — Replay

```id="ql2m4p"
Replay Status: MATCH ✅
```

---

### Act 4 — Divergence

```id="5g8z0u"
Field diff:  
total: 120 → 95  

Replay Status: DIVERGENCE DETECTED ❌
```

---

## What just happened?

* The same execution was replayed deterministically
* A real change was detected instantly
* The difference was surfaced at field level
* The execution remained verifiable via WAL integrity

This is what production-grade AI execution requires.

---

## CLI

Inspect and verify executions:

```bash id="j2a4pn"
python demo/cli.py show-trace <execution_id>  
python demo/cli.py replay     <execution_id>  
python demo/cli.py verify-log <execution_id>  
```

---

## Why IntentusNet

Modern AI systems:

* cannot replay execution
* cannot detect drift
* cannot explain failures

IntentusNet adds:

### Observability

Trace every execution with independent signals
(latency, error, behavior, policy)

### Determinism

Replay execution using stable hashing and detect differences

### Enforcement

Circuit breaker and capability governor contain failures automatically

---

## Guarantees

* Deterministic execution layer
* Replay with diff detection
* WAL-backed audit trail
* Signal-driven enforcement

---

## Architecture

```id="r0cmh2"
Intent → Kernel → Signals → Enforcement → WAL → Replay
```

---

## Scope

### Guarantees

* Deterministic execution
* Replay & diffing
* Enforcement
* Auditability

### Non-Goals

* No planning
* No reasoning
* No prompt optimization

---

## License

MIT
