"""Twin-search baseline: exhaustively simulate the whole typed action grid, no LLM.

This is the control for "do the agents add anything beyond the twin?". It never
diagnoses. It enumerates every action the validator allows on a coarse grid, runs each
through the same Simulation-agent test the pipeline uses (paired replications, same
gain threshold and alpha), and sends the best verified fix to the gate. If it matches
the multi-agent system, the LLM roles add little over brute-force search; the price is
the number of twin simulations, reported as ``twin_sims``.

Candidates are ranked exactly like the Simulation agent ranks them. The search result
depends only on the line config, so it is memoised per config; the cost it reports is
what an uncached run would spend.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from src.actions import RejectionLog, validate_and_apply
from src.agents.gate import SimulatedApprover
from src.agents.mock_roles import DROP_THRESHOLD_PCT
from src.agents.observe import observe
from src.agents.simulation import run_simulation_agent
from src.agents.types import CandidateResult, PipelineSettings, Recommendation, RunRecord
from src.llm import UsageMeter
from src.scenarios import Scenario
from src.twin import LineConfig

BUFFER_SIZES = (1, 3, 5)
REBALANCE_FRACTIONS = (0.1, 0.2, 0.3)
MAINTENANCE_GRID = ((1.5, 1.0), (2.0, 1.0), (1.0, 0.5), (1.5, 0.75), (2.0, 0.5))  # (mtbf x, mttr x)


def action_grid(config: LineConfig) -> list[dict[str, Any]]:
    """Every grid action that passes the validator on ``config`` (deduplicated, stable order)."""
    n = config.n_stations
    raw: list[dict[str, Any]] = []
    for st in range(1, n):
        raw += [{"type": "add_buffer", "station": st, "size": sz} for sz in BUFFER_SIZES]
    for a in range(1, n):
        for src, dst in ((a, a + 1), (a + 1, a)):
            raw += [{"type": "rebalance_task", "from_station": src, "to_station": dst, "fraction": f} for f in REBALANCE_FRACTIONS]
    for st in range(1, n + 1):
        raw += [{"type": "change_maintenance", "station": st, "mtbf_multiplier": mt, "mttr_multiplier": mr} for mt, mr in MAINTENANCE_GRID]
    scratch = RejectionLog()  # grid construction is not a proposal, so keep it out of the run's rejection log
    return [a for a in raw if validate_and_apply(a, config, scratch).ok]


@lru_cache(maxsize=64)
def _search(config_json: str, settings: PipelineSettings) -> tuple[CandidateResult, ...]:
    config = LineConfig.model_validate_json(config_json)
    return tuple(run_simulation_agent(config, action_grid(config), settings))


def search(config: LineConfig, settings: PipelineSettings) -> list[CandidateResult]:
    """Rank the whole grid on ``config`` (passed fixes first, best gain first)."""
    return list(_search(config.model_dump_json(), settings))


def sims_per_search(config: LineConfig, settings: PipelineSettings) -> int:
    """Twin simulations an uncached search costs: baseline plus every candidate, ``n_reps`` each."""
    return settings.n_reps * (1 + len(action_grid(config)))


def _derived_diagnosis(action: dict[str, Any]) -> dict[str, Any]:
    """The search never diagnoses; the station its best fix targets is the only 'diagnosis' it implies."""
    station = action["from_station"] if action["type"] == "rebalance_task" else action["station"]
    return {"bottleneck_station": station, "fault_type": "unspecified", "confidence": 1.0,
            "explanation": f"No diagnosis performed. Best verified fix from the exhaustive twin search targets station {station}."}


def run_twin_search(scenario: Scenario, seed: int, approver: SimulatedApprover, settings: PipelineSettings | None = None) -> RunRecord:
    """Search the grid, offer verified fixes best-first to the gate, stop at the first approval or the round cap."""
    settings = settings or PipelineSettings()
    config = scenario.config
    obs = observe(config, seed).payload
    trace = [{"step": "observe", "detail": f"throughput {obs['throughput_vs_reference_pct']:+.1f}% vs reference"}]
    usage = {**UsageMeter().as_dict(), "twin_sims": 0}
    base = dict(system="twin_search", scenario=scenario.name, seed=seed, usage=usage)
    if obs["throughput_vs_reference_pct"] > DROP_THRESHOLD_PCT:
        diag = {"bottleneck_station": None, "fault_type": "none", "explanation": "Output normal.", "confidence": 1.0}
        return RunRecord(**base, outcome="no_fault", iterations=0, diagnoses=[diag], gate_log=[], applied_action=None,
                         final_config=config.model_dump(), trace=trace)
    ranked = search(config, settings)
    usage["twin_sims"] = sims_per_search(config, settings)
    passed = [c for c in ranked if c.passed]
    trace.append({"step": "twin_search", "detail": f"simulated {len(ranked)} grid actions ({usage['twin_sims']} runs); {len(passed)} passed"})
    if not passed:
        diag = {"bottleneck_station": None, "fault_type": "unspecified", "confidence": 1.0, "explanation": "No grid action passed twin verification."}
        return RunRecord(**base, outcome="no_recommendation", iterations=1, diagnoses=[diag], gate_log=[], applied_action=None,
                         final_config=config.model_dump(), trace=trace)
    diagnoses: list[dict[str, Any]] = []
    gate_log: list[dict[str, Any]] = []
    log, applied, final, outcome, rounds = RejectionLog(), None, config, "rejected_max_iterations", 0
    for rounds, cand in enumerate(passed[: settings.max_iterations], 1):
        diag = _derived_diagnosis(cand.action)
        diagnoses.append(diag)
        rec = Recommendation(action=cand.action, rationale="Best-ranked action from exhaustive twin search.", verified=True, evidence=cand)
        rec, decision, entry = approver.review(rec, config, diag, settings, rounds)
        gate_log.append(entry)
        trace.append({"step": "gate", "detail": f"{'approved' if decision.approved else 'rejected'}: {decision.reason}"})
        if decision.approved:
            res = validate_and_apply(rec.action, config, log)
            if res.ok and res.config is not None and res.action is not None:
                final, applied, outcome = res.config, res.action.model_dump(), "applied"
            else:
                outcome = "blocked_invalid"
            break
    return RunRecord(**base, outcome=outcome, iterations=rounds, diagnoses=diagnoses, gate_log=gate_log, applied_action=applied,
                     final_config=final.model_dump(), trace=trace, action_rejections=log.entries)
