"""Per-run metrics computed from a RunRecord against scenario ground truth."""

from __future__ import annotations

import math
from typing import Any

from src.agents.observe import observe
from src.agents.types import RunRecord
from src.eval.judge import judge_explanation
from src.eval.truth import INEFFECTIVE_PCT, TruthEvaluator
from src.llm import LLMClient, UsageMeter
from src.scenarios import Scenario
from src.twin import LineConfig

ACCEPTED_TYPES_FOR_MIXED = {"mixed", "breakdowns", "slow_station"}


def station_correct(diag: dict[str, Any], sc: Scenario) -> bool:
    """Diagnosed station matches the seeded fault (healthy: correctly reports no fault)."""
    if sc.truth.station is None:
        return diag["fault_type"] == "none"
    return diag["bottleneck_station"] == sc.truth.station


def type_correct(diag: dict[str, Any], sc: Scenario) -> float:
    """1.0/0.0 if the fault type matches (mixed accepts either component); NaN if the system gives no type."""
    claimed = diag["fault_type"]
    if claimed == "unspecified":
        return math.nan
    if claimed == sc.truth.fault_type:
        return 1.0
    return float(sc.truth.fault_type == "mixed" and claimed in ACCEPTED_TYPES_FOR_MIXED)


def gate_reviews(rec: RunRecord, sc: Scenario, truth: TruthEvaluator, experiment: str) -> list[dict[str, Any]]:
    """One row per gate review with the independently measured status of the presented action."""
    rows = []
    for e in rec.gate_log:
        status = truth.action_status(sc.config, e["action"])
        rows.append(
            {
                "experiment": experiment, "system": rec.system, "scenario": rec.scenario, "seed": rec.seed,
                "iteration": e["iteration"], "injected": e["injected"], "verified": e["verified"], "approved": e["approved"],
                "status": status, "bad": status != "ok",
                "caught": (status != "ok") and not e["approved"],
                "escaped": (status != "ok") and e["approved"],
            }
        )
    return rows


def score_run(
    rec: RunRecord, sc: Scenario, truth: TruthEvaluator, client: LLMClient, experiment: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Compute the metric row for one run plus its gate-review rows."""
    first = rec.diagnoses[0]
    reviews = gate_reviews(rec, sc, truth, experiment)
    gain = truth.gain_pct(sc.config, LineConfig.model_validate(rec.final_config)) if rec.applied_action else 0.0
    reference = {"station": sc.truth.station, "fault_type": sc.truth.fault_type}
    judge = judge_explanation(client, first, reference, observe(sc.config, rec.seed).payload, UsageMeter())
    row = {
        "experiment": experiment, "system": rec.system, "scenario": rec.scenario, "seed": rec.seed, "outcome": rec.outcome,
        "iterations": rec.iterations, "steps": rec.usage["steps"], "input_tokens": rec.usage["input_tokens"],
        "output_tokens": rec.usage["output_tokens"], "total_tokens": rec.usage["total_tokens"], "twin_sims": rec.usage.get("twin_sims", 0),
        "station_correct": float(station_correct(first, sc)), "final_station_correct": float(station_correct(rec.diagnoses[-1], sc)),
        "type_correct": type_correct(first, sc), "applied": rec.applied_action is not None, "gain_pct": gain,
        "false_alarm_action": sc.truth.station is None and rec.applied_action is not None,
        "invalid_fix": any(r["bad"] and not r["injected"] for r in reviews),
        "ineffective_fix": rec.applied_action is not None and gain < INEFFECTIVE_PCT,
        "validator_rejections": len(rec.action_rejections), "gate_reviews": len(reviews),
        "bad_applied": any(r["escaped"] for r in reviews),
        "expl_correctness": judge.correctness, "expl_evidence": judge.evidence, "expl_clarity": judge.clarity,
        "expl_quality": judge.overall,
    }
    return row, reviews
