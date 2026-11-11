# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Research prototype: a multi-agent LLM system monitors a simulated 5-station production line (SimPy twin), diagnoses throughput loss, tests candidate fixes in the twin, and only then recommends one to a human. Principle: **verify before act**. `claude_code_prompt.txt` is the original build spec; `docs/ARCHITECTURE.md` and `docs/ASSUMPTIONS.md` are the design record (update ASSUMPTIONS.md when changing any parameter or metric definition).

## Commands

```bash
make setup                                   # .venv + editable install (PYTHON=python3.12 to override interpreter)
make test                                    # whole suite, ~40 s, offline
.venv/bin/python -m pytest tests/test_graph.py -k rejection   # single file / test
make run-experiments                         # ~2 min, rewrites results/ and docs/RESULTS.md
.venv/bin/python -m src.eval.runner --seeds 3 --out /tmp/res --docs /tmp/docs   # quick throwaway run
make dashboard                               # Streamlit supervisor UI
```

No linter is configured. `ruff check src tests --select F,W` is clean.

## Mock vs real LLM

`from_env` returns a mock client unless `ANTHROPIC_API_KEY` is set (or `LLM_MODE=real`). Mock role handlers live in `src/agents/mock_roles.py` and are rule-based. Tests must never need a key; use `mock_client()` from `src.agents`. Everything produced in mock mode must stay labelled MOCK (the report generator does this). Real responses are cached under `results/llm_cache/` (git-ignored).

## Architecture (the parts that span files)

- **Twin** (`src/twin`): `LineConfig`/`StationConfig` (pydantic, 1-based station ids; `buffer_after` on station i is the buffer between i and i+1). `ProductionLine` uses independent seeded RNG streams per station and purpose, so two configs run with the same seed share common random numbers. KPIs are computed from 60 s cumulative snapshots.
- **Scenarios** (`src/scenarios`): each carries `GroundTruth(station, fault_type)`. For `buffer` faults the truth station *owns* the undersized buffer. Tests assert the label matches analytic effective capacity for slow/breakdown/mixed.
- **Typed actions** (`src/actions`): the only way anything changes a config. `validate_and_apply` parses, checks constraints against the current config, logs rejections, returns a deep copy. All systems, baselines and the human gate go through it.
- **Agents** (`src/agents/graph.py`): LangGraph state is plain dicts (so it checkpoints), with reducer-merged `trace`, `gate_log`, `diagnoses`, `action_rejections`. `Pipeline(approver=SimulatedApprover)` runs to completion. `Pipeline(approver=None)` compiles with `interrupt_before=["gate"]` and resumes through `submit_human_decision` (used by the dashboard). `use_simulation=False` is the ablation. The iteration cap counts diagnosis rounds, and a round with no verified fix also counts.
- **Gate** (`src/agents/gate.py`): `SimulatedApprover` sees only the evidence presented. With twin evidence it approves iff gain >= threshold; without it, it can only check constraint validity. Bad-recommendation injection lives here. Baselines call the same `review()`.
- **Eval** (`src/eval`): scores every run against *independent* replications (seeds 2000+, disjoint from the Simulation agent's 1000+ and observation seeds 1..N). Two experiments: `clean` (RQ1, RQ2) and `stress` (injected bad recs, RQ3). `report.py` writes prose from the data; if you change a metric, update the report text and ASSUMPTIONS.md.
- **Dashboard** (`src/dashboard`): `app.py` is thin, `views.py` holds testable helpers. Button callbacks must read `st.session_state`, not bound `args`, because `args` are captured when the button is drawn (stale after a widget change). Dashboard tests use `streamlit.testing.v1.AppTest`.

## Gotchas

- Seeds with `seed % 4 == 0` make the mock candidate generator emit an over-aggressive first proposal on purpose, to exercise the validator.
- Do not read ground truth or scenario labels in anything agents see; `observe()` deliberately exposes only standards and measured KPIs.
- Test tolerances (capacity bound +3%, Little's law 5%) are documented in ASSUMPTIONS.md.
