# Architecture and build plan

Multi-agent LLM system that monitors a simulated 5-station line (SimPy twin), diagnoses throughput loss, tests candidate fixes inside the twin, and only then recommends the best one to a human supervisor. Principle: **verify before act**. Nothing reaches the operator until the twin shows a throughput gain, and nothing is applied without human approval.

## Build phases

| # | Phase | Status |
|---|---|---|
| 0 | Skeleton, packaging, Makefile | done |
| 1 | Twin, KPI collector, event log, seeded scenarios, validity tests | done |
| 2 | Typed actions (pydantic), validator, applier | done |
| 3 | LLM wrapper: disk cache, token counts, retry, JSON validation, mock mode | done |
| 4 | LangGraph agents: Monitor, Diagnosis, Simulation, Supervisor gate | done |
| 5 | Baselines: rule-based, single-agent, multi-agent without Simulation | done |
| 6 | Evaluation harness, tables, plots, `results/summary.md` | done |
| 7 | Streamlit dashboard | done |
| 8 | README, ASSUMPTIONS, DEMO polish | done |

## Twin (Phase 1)

- `src/twin/config.py`: `StationConfig` / `LineConfig` (pydantic). Stations are 1-based. `buffer_after` on station `i` is the buffer between `i` and `i+1`.
- `src/twin/line.py`: `ProductionLine` (SimPy). Each station is a process that pulls from the upstream buffer, processes, pushes downstream (blocking after service). Per-station independent seeded random streams (cycle time, failures) give common random numbers across configurations.
- `src/twin/kpis.py`: KPIs for any window from cumulative 60 s snapshots: throughput, per-station utilization / blocked / starved / down fractions, breakdown counts, mean buffer levels, WIP.
- Event log: structured JSON-serialisable events (`breakdown_start`, `breakdown_end`, `blocked_end`, `starved_end`).
- `src/scenarios/definitions.py`: healthy, slow_station, breakdowns, buffer, mixed, each with a `GroundTruth(station, fault_type)`.

## Typed-action safety layer (Phase 2)

Agents may only propose `AddBuffer`, `RebalanceTask` or `ChangeMaintenance` (pydantic, `extra="forbid"`, discriminated on `type`). `validate_and_apply` parses, checks constraints against the *current* config, logs every rejection with its reason, and returns a modified deep copy of the config. Every path that can change the line, including the baselines and the human gate, goes through it.

## The verify-before-act loop (Phase 4)

```
START -> monitor -> diagnosis -+-> (fault none) ----------------------------> finalize
                     ^         +-> candidates (Simulation agent) -+-> gate -+-> apply -> finalize
                     |                                            |         |
                     +---- re-diagnose (no viable fix) -----------+         |
                     +---- re-diagnose (gate rejected) ----------------------+
                                  (cap: max_iterations diagnosis rounds -> finalize)
```

Roles (`src/agents/`):
1. **Monitor** reads one simulated shift (KPIs plus event-log summary, never the scenario label) and flags anomalies.
2. **Diagnosis** names the bottleneck station and fault type with an explanation and confidence. After a rejected round it receives feedback (rejected action, or "no viable fix" for a station) and must revise.
3. **Simulation** takes LLM-proposed candidates, validates each against the typed schema, runs every valid one over `n_reps` seeded replications paired with the unmodified line, and passes only fixes with mean gain >= `min_gain_pct` and a one-sided paired t-test below `alpha`. Returns ranked results with numbers. Only the top passing fix is recommended.
4. **Supervisor gate** approves or rejects. Batch mode uses `SimulatedApprover` (sees only the evidence presented; can inject bad recommendations at a configurable rate). The dashboard uses a real person: the graph is compiled with `interrupt_before=["gate"]` and resumed via `submit_human_decision`.

Only an approved fix is applied (`apply` re-validates). State is a typed dict with reducer-merged `trace`, `gate_log`, `diagnoses` and `action_rejections`. The ablation (`use_simulation=False`) swaps the Simulation node for "take the first constraint-valid proposal, unverified".

Dashboard (`src/dashboard/`): `app.py` is a thin Streamlit script; `views.py` holds pure data-shaping helpers. It builds a `Pipeline` with `approver=None`, calls `start()` (runs to the gate), shows KPIs, findings, the candidate table and the trace, and the Approve/Reject buttons call `submit_human_decision`. Rejection re-runs Diagnosis and pauses at the gate again. Widget callbacks read `st.session_state` rather than bound args so stale values are never used.

Mock mode: `src/agents/mock_roles.py` provides rule-based role handlers (active-period bottleneck detection). Everything runs offline; see ASSUMPTIONS.md for what mock results do and do not mean.
