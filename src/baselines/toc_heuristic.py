"""Classical baseline: Theory-of-Constraints decision rules over the observed KPIs.

Identify the constraint (the station that is busiest, so least blocked/starved), then
exploit it with the fix that matches the observed symptom. No LLM, no twin, one gate
round. It is the strongest non-learning, non-simulating comparator: a competent
engineer's rule of thumb, unlike the naive ``rule_based`` buffer-after-busiest baseline.

The thresholds below were fixed a priori from the standards the agents already see
(cycle time vs standard, downtime share); they were not tuned on the scenarios.
"""

from __future__ import annotations

from typing import Any

from src.actions import RejectionLog, validate_and_apply
from src.agents.gate import SimulatedApprover
from src.agents.mock_roles import DROP_THRESHOLD_PCT
from src.agents.observe import observe
from src.agents.types import PipelineSettings, Recommendation, RunRecord
from src.llm import UsageMeter
from src.scenarios import Scenario

SLOW_CYCLE_RATIO = 1.15  # measured cycle time this far above standard => the station itself is slow
DOWNTIME_SHARE = 0.08  # share of the shift spent down that marks a breakdown-limited station
REBALANCE_FRACTION = 0.2
BUFFER_SIZE = 3
MTBF_MULTIPLIER = 1.5
MTTR_MULTIPLIER = 0.75


def _active(s: dict[str, Any]) -> float:
    """Share of the shift the station is working or being repaired (never blocked or starved)."""
    return s["utilization"] + s["down"]


def classify_and_act(obs: dict[str, Any], n_stations: int, failure_stations: set[int]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (diagnosis, action) from one observation using the TOC rules."""
    stations = {s["id"]: s for s in obs["stations"]}
    b = max(stations, key=lambda i: (_active(stations[i]), -i))
    s = stations[b]
    cycle, std = s["measured_cycle_time_s"], s["standard_cycle_time_s"]
    if cycle is not None and cycle > SLOW_CYCLE_RATIO * std:
        neighbours = [n for n in (b - 1, b + 1) if 1 <= n <= n_stations]
        to = min(neighbours, key=lambda n: _active(stations[n]))
        diag = ("slow_station", f"Station {b} is the constraint and runs {cycle / std:.2f}x its standard cycle time.")
        action = {"type": "rebalance_task", "from_station": b, "to_station": to, "fraction": REBALANCE_FRACTION}
    elif s["down"] > DOWNTIME_SHARE and b in failure_stations:
        diag = ("breakdowns", f"Station {b} is the constraint and is down {s['down']:.0%} of the shift.")
        action = {"type": "change_maintenance", "station": b, "mtbf_multiplier": MTBF_MULTIPLIER, "mttr_multiplier": MTTR_MULTIPLIER}
    else:
        diag = ("buffer", f"Station {b} is the constraint; neighbours are blocked/starved around it, so protect it with a buffer.")
        action = {"type": "add_buffer", "station": b - 1 if b > 1 else b, "size": BUFFER_SIZE}
    fault, why = diag
    return {"bottleneck_station": b, "fault_type": fault, "explanation": why, "confidence": 1.0}, action


def run_toc_heuristic(scenario: Scenario, seed: int, approver: SimulatedApprover, settings: PipelineSettings | None = None) -> RunRecord:
    """Act once on a throughput drop with the rule-selected fix; no verification, one gate round."""
    settings = settings or PipelineSettings()
    config = scenario.config
    obs = observe(config, seed).payload
    trace = [{"step": "observe", "detail": f"throughput {obs['throughput_vs_reference_pct']:+.1f}% vs reference"}]
    base = dict(system="toc_heuristic", scenario=scenario.name, seed=seed, usage=UsageMeter().as_dict())
    if obs["throughput_vs_reference_pct"] > DROP_THRESHOLD_PCT:
        diag = {"bottleneck_station": None, "fault_type": "none", "explanation": "Output normal.", "confidence": 1.0}
        return RunRecord(**base, outcome="no_fault", iterations=0, diagnoses=[diag], gate_log=[], applied_action=None,
                         final_config=config.model_dump(), trace=trace)
    failure_stations = {i for i, s in enumerate(config.stations, 1) if s.mtbf is not None}
    diag, action = classify_and_act(obs, config.n_stations, failure_stations)
    trace.append({"step": "rules", "detail": f"{diag['fault_type']} at station {diag['bottleneck_station']}: {action}"})
    rec = Recommendation(action=action, rationale="Theory-of-Constraints rule for the observed symptom.", verified=False)
    rec, decision, entry = approver.review(rec, config, diag, settings, 1)
    trace.append({"step": "gate", "detail": f"{'approved' if decision.approved else 'rejected'}: {decision.reason}"})
    log, applied, final, outcome = RejectionLog(), None, config, "rejected"
    if decision.approved:
        res = validate_and_apply(rec.action, config, log)
        if res.ok and res.config is not None and res.action is not None:
            final, applied, outcome = res.config, res.action.model_dump(), "applied"
        else:
            outcome = "blocked_invalid"
    return RunRecord(**base, outcome=outcome, iterations=1, diagnoses=[diag], gate_log=[entry], applied_action=applied,
                     final_config=final.model_dump(), trace=trace, action_rejections=log.entries)
