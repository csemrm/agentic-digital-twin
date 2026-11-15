"""Independent re-simulating gate vs the evidence-trusting gate."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.agents import PipelineSettings, SimulatedApprover, mock_client
from src.agents.gate import INDEPENDENT_SEED_BASE, IndependentApprover
from src.agents.simulation import eval_seeds, evaluate_candidate
from src.agents.types import Recommendation
from src.eval.runner import run_experiments
from src.eval.truth import EVAL_SEED_BASE, TruthEvaluator
from src.scenarios import SCENARIOS

SETTINGS = PipelineSettings()
CFG = SCENARIOS["slow_station"].config
GOOD = {"type": "rebalance_task", "from_station": 2, "to_station": 1, "fraction": 0.2}
HARMFUL = {"type": "rebalance_task", "from_station": 1, "to_station": 2, "fraction": 0.3}  # pushes work onto the bottleneck


def _forged() -> Recommendation:
    """A harmful but valid fix presented with the good fix's (real) evidence."""
    return Recommendation(action=HARMFUL, rationale="forged", verified=True, evidence=evaluate_candidate(CFG, GOOD, SETTINGS))


def test_harmful_fix_really_is_harmful_for_the_forgery_tests() -> None:
    assert TruthEvaluator().action_status(CFG, HARMFUL) == "harmful"
    assert TruthEvaluator().action_status(CFG, GOOD) == "ok"


def test_trusting_gate_is_fooled_by_forged_evidence_but_independent_gate_is_not() -> None:
    rec = _forged()
    assert SimulatedApprover().decide(rec, CFG).approved is True
    d = IndependentApprover().decide(rec, CFG)
    assert d.approved is False and d.independent_gain_pct is not None and d.independent_gain_pct < 0


def test_independent_gate_approves_a_genuinely_good_fix_with_or_without_evidence() -> None:
    with_ev = Recommendation(action=GOOD, rationale="", verified=True, evidence=evaluate_candidate(CFG, GOOD, SETTINGS))
    no_ev = Recommendation(action=GOOD, rationale="", verified=False)
    for rec in (with_ev, no_ev):
        d = IndependentApprover().decide(rec, CFG)
        assert d.approved and d.independent_gain_pct >= 2.0


def test_independent_gate_checks_unverified_fixes_unless_told_not_to() -> None:
    unverified_bad = Recommendation(action=HARMFUL, rationale="", verified=False)
    assert IndependentApprover().decide(unverified_bad, CFG).approved is False
    assert IndependentApprover(verify_unverified=False).decide(unverified_bad, CFG).approved is True  # falls back to validity-only


def test_independent_gate_still_rejects_invalid_actions_without_simulating() -> None:
    bad = Recommendation(action={"type": "add_buffer", "station": 5, "size": 2}, rationale="", verified=False)
    d = IndependentApprover().decide(bad, CFG)
    assert d.approved is False and d.reason.startswith("invalid action") and d.independent_gain_pct is None


def test_independent_gate_seeds_are_disjoint_from_agent_and_scoring_seeds() -> None:
    g = IndependentApprover()
    gate_seeds = {g.eval_seed_base + i for i in range(g.n_reps)}
    scoring = {EVAL_SEED_BASE + i for i in range(TruthEvaluator().seeds.__len__())}
    assert g.eval_seed_base == INDEPENDENT_SEED_BASE
    assert not gate_seeds & set(eval_seeds(SETTINGS)) and not gate_seeds & scoring
    assert not gate_seeds & set(range(1, 1000))  # observation (1..N) and reference (100..104) seeds


def test_forge_flag_reuses_presented_evidence_while_honest_injection_recomputes_it() -> None:
    good = Recommendation(action=GOOD, rationale="", verified=True, evidence=evaluate_candidate(CFG, GOOD, SETTINGS))
    diag = {"bottleneck_station": 2}
    forged, inj1 = SimulatedApprover(bad_rate=1.0, seed=3, forge_evidence=True).maybe_inject(good, CFG, diag, SETTINGS)
    honest, inj2 = SimulatedApprover(bad_rate=1.0, seed=3).maybe_inject(good, CFG, diag, SETTINGS)
    assert inj1 and inj2 and forged.action == honest.action != GOOD
    assert forged.evidence == good.evidence and honest.evidence != good.evidence


def test_gate_log_records_independent_gain_only_for_the_independent_gate() -> None:
    rec = Recommendation(action=GOOD, rationale="", verified=False)
    _, _, e_trust = SimulatedApprover().review(rec, CFG, {"bottleneck_station": 2}, SETTINGS, 1)
    _, _, e_ind = IndependentApprover().review(rec, CFG, {"bottleneck_station": 2}, SETTINGS, 1)
    assert e_trust["independent_gain_pct"] is None and e_ind["independent_gain_pct"] >= 2.0


def test_gate_arms_experiment_shows_forgery_escapes_trusting_gate_only(tmp_path: Path) -> None:
    run_experiments([1, 2, 3, 4], tmp_path, None, bad_rate=1.0, client=mock_client(), scenarios=["slow_station"], gate_arms=True)
    runs, rev = pd.read_csv(tmp_path / "runs.csv"), pd.read_csv(tmp_path / "gate_reviews.csv")
    assert set(runs["experiment"]) == {"clean", "stress", "clean_indep", "stress_indep", "stress_forged", "stress_forged_indep"}
    assert not rev[rev["experiment"].isin(["clean", "clean_indep"])]["injected"].any()

    def caught(exp: str, system: str) -> float:
        bad = rev[(rev["experiment"] == exp) & (rev["system"] == system) & rev["bad"]]
        assert len(bad) > 0
        return float(bad["caught"].mean())

    assert caught("stress_forged_indep", "multi_agent") == 1.0
    assert caught("stress_forged", "multi_agent") < 1.0  # harmful-but-valid fixes with good-looking numbers escape
    assert caught("stress", "multi_agent") == 1.0  # honest evidence: the trusting gate is enough
    clean = runs[runs["experiment"] == "clean"].set_index(["system", "seed"])["gain_pct"]
    clean_ind = runs[runs["experiment"] == "clean_indep"].set_index(["system", "seed"])["gain_pct"]
    assert (clean_ind.loc["multi_agent"] >= 0.9 * clean.loc["multi_agent"]).all()  # independence does not reject good fixes
