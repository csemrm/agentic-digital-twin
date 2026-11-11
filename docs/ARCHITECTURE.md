# Architecture and build plan

Multi-agent LLM system that monitors a simulated 5-station line (SimPy twin), diagnoses throughput loss, tests candidate fixes inside the twin, and only then recommends the best one to a human supervisor. Principle: **verify before act**. Nothing reaches the operator until the twin shows a throughput gain, and nothing is applied without human approval.

## Build phases

| # | Phase | Status |
|---|---|---|
| 0 | Skeleton, packaging, Makefile | done |
| 1 | Twin, KPI collector, event log, seeded scenarios, validity tests | done |
| 2 | Typed actions (pydantic), validator, applier | planned |
| 3 | LLM wrapper: disk cache, token counts, retry, JSON validation, mock mode | planned |
| 4 | LangGraph agents: Monitor, Diagnosis, Simulation, Supervisor gate | planned |
| 5 | Baselines: rule-based, single-agent, multi-agent without Simulation | planned |
| 6 | Evaluation harness, tables, plots, `results/summary.md` | planned |
| 7 | Streamlit dashboard | planned |
| 8 | README, ASSUMPTIONS, DEMO polish | planned |

## Twin (Phase 1)

- `src/twin/config.py`: `StationConfig` / `LineConfig` (pydantic). Stations are 1-based. `buffer_after` on station `i` is the buffer between `i` and `i+1`.
- `src/twin/line.py`: `ProductionLine` (SimPy). Each station is a process that pulls from the upstream buffer, processes, pushes downstream (blocking after service). Per-station independent seeded random streams (cycle time, failures) give common random numbers across configurations.
- `src/twin/kpis.py`: KPIs for any window from cumulative 60 s snapshots: throughput, per-station utilization / blocked / starved / down fractions, breakdown counts, mean buffer levels, WIP.
- Event log: structured JSON-serialisable events (`breakdown_start`, `breakdown_end`, `blocked_end`, `starved_end`).
- `src/scenarios/definitions.py`: healthy, slow_station, breakdowns, buffer, mixed, each with a `GroundTruth(station, fault_type)`.

Later sections (typed-action safety layer, LangGraph loop, roles) are added as each phase lands.
