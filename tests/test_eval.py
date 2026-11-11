"""Metrics, statistics helpers, truth evaluation and the end-to-end experiment runner (mock mode)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.agents import PipelineSettings, mock_client
from src.eval import analysis
from src.eval.judge import judge_explanation
from src.eval.metrics import station_correct, type_correct
from src.eval.report import verdict
from src.eval.runner import SYSTEMS, run_experiments
from src.eval.truth import TruthEvaluator
from src.scenarios import SCENARIOS


def test_station_correct_handles_healthy_and_faulty() -> None:
    assert station_correct({"bottleneck_station": None, "fault_type": "none"}, SCENARIOS["healthy"])
    assert not station_correct({"bottleneck_station": 3, "fault_type": "slow_station"}, SCENARIOS["healthy"])
    assert station_correct({"bottleneck_station": 4, "fault_type": "breakdowns"}, SCENARIOS["breakdowns"])
    assert not station_correct({"bottleneck_station": None, "fault_type": "none"}, SCENARIOS["breakdowns"])


def test_type_correct_rules() -> None:
    sc = SCENARIOS["mixed"]
    assert type_correct({"fault_type": "mixed"}, sc) == 1.0
    assert type_correct({"fault_type": "breakdowns"}, sc) == 1.0  # component of a mixed fault
    assert type_correct({"fault_type": "buffer"}, sc) == 0.0
    assert math.isnan(type_correct({"fault_type": "unspecified"}, sc))
    assert type_correct({"fault_type": "slow_station"}, SCENARIOS["breakdowns"]) == 0.0


def test_truth_evaluator_classifies_actions_independently() -> None:
    truth, cfg = TruthEvaluator(n_reps=8), SCENARIOS["slow_station"].config
    assert truth.action_status(cfg, {"type": "rebalance_task", "from_station": 2, "to_station": 1, "fraction": 0.2}) == "ok"
    assert truth.action_status(cfg, {"type": "rebalance_task", "from_station": 1, "to_station": 2, "fraction": 0.3}) == "harmful"
    assert truth.action_status(cfg, {"type": "add_buffer", "station": 5, "size": 2}) == "invalid"
    assert truth.action_status(cfg, {"nonsense": 1}) == "invalid"


def test_truth_seeds_are_disjoint_from_agent_seeds() -> None:
    settings = PipelineSettings()
    agent_seeds = {settings.eval_seed_base + i for i in range(settings.n_reps)}
    assert not agent_seeds & set(TruthEvaluator().seeds)


def test_wilson_interval_known_values() -> None:
    lo, hi = analysis.wilson_ci(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    lo, hi = analysis.wilson_ci(10, 10)
    assert hi == 1.0 and lo < 1.0
    assert analysis.wilson_ci(0, 10)[0] == 0.0  # never negative
    assert all(math.isnan(v) for v in analysis.wilson_ci(0, 0))


def test_mean_ci_t_interval_and_nan_handling() -> None:
    n, m, lo, hi = analysis.mean_ci(pd.Series([1.0, 2.0, 3.0, np.nan]), binary=False)
    assert n == 3 and m == 2.0 and lo < 2.0 < hi
    n, m, lo, hi = analysis.mean_ci(pd.Series([5.0]), binary=False)
    assert n == 1 and math.isnan(lo)


def test_paired_diff_ci_detects_consistent_gap() -> None:
    rows = [{"system": s, "scenario": "slow_station", "seed": i, "gain_pct": 10.0 + (5.0 if s == "a" else 0.0) + 0.1 * i}
            for i in range(10) for s in ("a", "b")]
    n, diff, lo, hi = analysis.paired_diff_ci(pd.DataFrame(rows), "gain_pct", "a", "b")
    assert n == 10 and diff == pytest.approx(5.0) and lo > 4.9
    assert "higher" in verdict(n, diff, lo, hi, " pp")
    assert analysis.paired_diff_ci(pd.DataFrame(rows), "gain_pct", "a", "missing")[0] == 0


def test_verdict_reports_no_difference_when_ci_spans_zero() -> None:
    assert "no detectable difference" in verdict(10, 0.1, -0.5, 0.7, "")
    assert "lower" in verdict(10, -2.0, -3.0, -1.0, "")


def test_mock_judge_scores_correct_cited_explanation_higher_than_wrong_terse_one() -> None:
    ref = {"station": 2, "fault_type": "slow_station"}
    good = {"bottleneck_station": 2, "fault_type": "slow_station",
            "explanation": "Station 2 is active 99% of the time with blocked 0% and cycle 1.5x standard, so it limits flow."}
    bad = {"bottleneck_station": 4, "fault_type": "buffer", "explanation": "Busy."}
    c = mock_client()
    assert judge_explanation(c, good, ref, {}).overall > judge_explanation(c, bad, ref, {}).overall
    assert 1 <= judge_explanation(c, bad, ref, {}).overall <= 5


@pytest.fixture(scope="module")
def experiment(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, dict]:
    out, docs = tmp_path_factory.mktemp("results"), tmp_path_factory.mktemp("docs")
    meta = run_experiments([1, 2], out, docs, bad_rate=0.5, client=mock_client(), scenarios=["healthy", "slow_station", "breakdowns"])
    return out, docs, meta


def test_runner_writes_all_outputs(experiment: tuple[Path, Path, dict]) -> None:
    out, docs, meta = experiment
    for name in ["runs.csv", "gate_reviews.csv", "summary_by_system_scenario.csv", "summary_by_system.csv", "gate_catch_by_system.csv",
                 "human_review_template.csv", "human_review_key.csv", "run_meta.json", "summary.md"]:
        assert (out / name).exists(), name
    assert (docs / "RESULTS.md").read_text() == (out / "summary.md").read_text()
    assert len(list((out / "plots").glob("*.png"))) >= 6
    assert meta["mode"] == "mock" and json.loads((out / "run_meta.json").read_text())["n_seeds"] == 2


def test_runner_covers_every_system_scenario_seed_once_per_experiment(experiment: tuple[Path, Path, dict]) -> None:
    runs = pd.read_csv(experiment[0] / "runs.csv")
    assert len(runs) == 2 * len(SYSTEMS) * 3 * 2
    assert set(runs["system"]) == set(SYSTEMS) and set(runs["experiment"]) == {"clean", "stress"}
    assert runs.groupby(["experiment", "system", "scenario", "seed"]).size().eq(1).all()
    for col in ["station_correct", "gain_pct", "steps", "total_tokens", "expl_quality", "invalid_fix", "ineffective_fix"]:
        assert col in runs and runs[col].notna().all()


def test_report_is_labelled_mock_and_answers_all_rqs(experiment: tuple[Path, Path, dict]) -> None:
    text = (experiment[0] / "summary.md").read_text()
    assert text.startswith("# Results (MOCK MODE)")
    for needle in ["RQ1", "RQ2", "RQ3", "## Limitations", "Bottleneck accuracy", "Human-gate catch rate"]:
        assert needle in text


def test_clean_experiment_has_no_injected_reviews_and_stress_has_some(experiment: tuple[Path, Path, dict]) -> None:
    rev = pd.read_csv(experiment[0] / "gate_reviews.csv")
    assert not rev[rev["experiment"] == "clean"]["injected"].any()
    assert rev[rev["experiment"] == "stress"]["injected"].any()


def test_human_review_template_is_blind_with_blank_scores(experiment: tuple[Path, Path, dict]) -> None:
    tpl = pd.read_csv(experiment[0] / "human_review_template.csv", dtype=str).fillna("")
    key = pd.read_csv(experiment[0] / "human_review_key.csv")
    assert len(tpl) == len(key) > 0 and set(tpl["item_id"]) == set(key["item_id"])
    assert not any(tpl[c].any() for c in ["reviewer_1_score_1to5", "reviewer_2_score_1to5", "reviewer_3_score_1to5"])
    joined = " ".join(tpl.astype(str).to_numpy().ravel())
    assert not any(s in joined for s in ["rule_based", "single_agent", "multi_agent"])


def test_runs_are_reproducible_across_invocations(tmp_path: Path) -> None:
    kw = dict(bad_rate=0.5, client=mock_client(), scenarios=["slow_station"])
    run_experiments([1], tmp_path / "a", None, **kw)
    run_experiments([1], tmp_path / "b", None, **kw)
    a, b = pd.read_csv(tmp_path / "a" / "runs.csv"), pd.read_csv(tmp_path / "b" / "runs.csv")
    pd.testing.assert_frame_equal(a, b)
