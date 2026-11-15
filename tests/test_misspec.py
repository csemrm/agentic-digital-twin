"""Mis-specified twin plumbing: structure preserved, observation and application stay on the real line."""

from __future__ import annotations

from src.agents import Pipeline, SimulatedApprover, mock_client
from src.baselines import run_twin_search
from src.scenarios import SCENARIOS, misspecify

REAL = SCENARIOS["slow_station"].config


def test_misspecify_zero_is_an_exact_copy_and_nonzero_changes_only_continuous_parameters() -> None:
    assert misspecify(REAL, 0.0, 1) == REAL and misspecify(REAL, 0.0, 1) is not REAL
    twin = misspecify(REAL, 0.3, 1)
    assert twin != REAL and twin.n_stations == REAL.n_stations
    for a, b in zip(REAL.stations, twin.stations):
        assert a.buffer_after == b.buffer_after and a.cycle_time_cv == b.cycle_time_cv
        assert (a.mtbf is None) == (b.mtbf is None)
        assert b.cycle_time_mean != a.cycle_time_mean


def test_misspecify_is_deterministic_per_seed_and_differs_across_seeds() -> None:
    assert misspecify(REAL, 0.3, 5) == misspecify(REAL, 0.3, 5)
    assert misspecify(REAL, 0.3, 5) != misspecify(REAL, 0.3, 6)


def test_pipeline_applies_fix_to_real_line_not_to_the_twin() -> None:
    twin = misspecify(REAL, 0.05, 1)  # mild: a badly wrong twin can veto every proposal (outcome no_recommendation)
    rec = Pipeline(SCENARIOS["slow_station"], 1, mock_client(), SimulatedApprover(), twin=twin).run()
    assert rec.outcome == "applied"
    from src.actions import validate_and_apply

    assert rec.final_config == validate_and_apply(rec.applied_action, REAL).config.model_dump()
    assert rec.gate_log[0]["verified"] is True


def test_twin_search_default_twin_is_the_real_line_and_a_wrong_twin_changes_the_evidence() -> None:
    same = run_twin_search(SCENARIOS["slow_station"], 1, SimulatedApprover())
    wrong = run_twin_search(SCENARIOS["slow_station"], 1, SimulatedApprover(), twin=misspecify(REAL, 0.5, 2))
    assert same.gate_log[0]["gain_pct"] != wrong.gate_log[0]["gain_pct"]
    assert wrong.final_config != REAL.model_dump()  # a fix was applied to the real line
