# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Greenfield. The only file is `claude_code_prompt.txt`, the full build spec for the "Agentic Digital Twin for Shop-Floor Performance" research prototype. No code, git repo, or tooling exists yet. The spec is the source of truth. Update this file with real commands and structure as the code lands, and drop anything below that proves wrong.

The spec sets these working rules:
- Build in 8 phases. After each phase, run tests, fix failures, and give a 3-line status.
- Don't ask the user questions unless truly blocked. Record choices in `docs/ASSUMPTIONS.md`.
- `git init` and commit after each phase.
- Every number in `docs/RESULTS.md` must come from an actual run. Label mock-mode results as mock.

## Planned stack and commands

Python 3.11+, SimPy, LangGraph, `anthropic` SDK, Streamlit, pandas, matplotlib, pytest, pydantic. Config: `.env.example` with `ANTHROPIC_API_KEY` and `LLM_MODEL` (default to a small/cheap model). Makefile targets to create: `setup`, `test`, `run-experiments`, `dashboard`.

Tests and experiments must run fully offline via the mock LLM mode. Tests must never need a real API key.

## Architecture (planned)

Multi-agent LLM system watches a simulated 5-station serial production line (SimPy), diagnoses throughput loss, tests fixes in the twin, and only then recommends one to a human. Core principle: **verify before act**. No recommendation reaches the operator until the twin shows it improves throughput, and nothing is applied without human approval.

Layout is `src/{twin,scenarios,actions,agents,baselines,llm,eval,dashboard}`, plus `tests/`, `docs/`, `results/`. The parts that span modules:

- **Twin + scenarios**: Deterministic per seed. Per-station cycle time, variability, MTBF, MTTR, buffer capacity. A KPI collector over rolling windows plus a structured JSON event log that agents read. Scenarios (slow station, frequent breakdowns, undersized buffer, mixed, healthy) each carry a ground-truth bottleneck label. Eval accuracy is scored against that label.
- **Typed actions (safety layer)**: Pydantic models `AddBuffer`, `RebalanceTask`, `ChangeMaintenance`. A validator enforces constraints and rejects anything outside the schema, logging the reason. An applier returns a modified twin config. Every agent path, including baselines, must go through this.
- **LangGraph loop** with shared typed state: Monitor → Diagnosis → Simulation → Supervisor gate. Simulation runs each candidate fix over several seeded replications versus the unmodified line and passes only statistically meaningful gains with no constraint violations. A gate rejection routes back to Diagnosis, with a capped iteration count. Batch mode uses a configurable simulated approver that can inject bad recommendations to measure RQ3. The dashboard uses real Approve/Reject buttons.
- **LLM wrapper**: On-disk cache keyed by (model, prompt hash), token and step counting per run, retry/backoff, JSON output validation, deterministic mock mode.
- **Baselines**: Rule-based (highest utilization = bottleneck, add buffer). Single-agent LLM (same tools and action set, no simulate step). Multi-agent without the Simulation agent (ablation). These isolate RQ1 (multi vs single agent) and RQ2 (simulate-before-recommend).
- **Eval harness**: Runs all four systems on the same seeded scenarios and seeds. Metrics: bottleneck accuracy, throughput gain, invalid-fix rate, steps and tokens, explanation quality (LLM-judge plus a human-reviewer CSV template), human-gate catch rate. Outputs go to `results/` with mean and CI tables, grouped bar plots, and `results/summary.md` answering RQ1–RQ3 with stated limitations.

Twin validity tests the spec requires: Little's law sanity, throughput bounded by the slowest station, seed reproducibility, and each fault scenario lowering throughput versus healthy.

Out of scope: real PLC/OPC UA, computer vision, multi-plant scheduling. Everything is simulated with no proprietary data.
