"""LangGraph routing: happy path, rejection loop, iteration cap, ablation, human gate."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents import MOCK_HANDLERS, Pipeline, PipelineSettings, SimulatedApprover
from src.agents.types import GateDecision, Recommendation
from src.llm import LLMClient, MockBackend
from src.scenarios import SCENARIOS
from src.twin import LineConfig


def client(**overrides: Any) -> LLMClient:
    return LLMClient(MockBackend({**MOCK_HANDLERS, **overrides}))


class ScriptedApprover(SimulatedApprover):
    """Approver that rejects the first ``reject_n`` recommendations."""

    def __init__(self, reject_n: int) -> None:
        super().__init__()
        self.reject_n, self.seen = reject_n, 0

    def decide(self, rec: Recommendation, config: LineConfig) -> GateDecision:
        self.seen += 1
        if self.seen <= self.reject_n:
            return GateDecision(approved=False, reason="supervisor says no")
        return GateDecision(approved=True, reason="ok")


def test_healthy_line_ends_without_action_or_gate() -> None:
    rec = Pipeline(SCENARIOS["healthy"], 1, client(), SimulatedApprover()).run()
    assert rec.outcome == "no_fault" and rec.applied_action is None and rec.gate_log == []
    assert [t["step"] for t in rec.trace] == ["monitor", "diagnosis", "finalize"]


@pytest.mark.parametrize("name", ["slow_station", "breakdowns", "buffer", "mixed"])
def test_happy_path_applies_verified_fix_that_changes_config(name: str) -> None:
    sc = SCENARIOS[name]
    rec = Pipeline(sc, 1, client(), SimulatedApprover()).run()
    assert rec.outcome == "applied" and rec.iterations == 1
    assert [t["step"] for t in rec.trace] == ["monitor", "diagnosis", "simulation", "gate", "apply", "finalize"]
    assert rec.gate_log[0]["verified"] and rec.gate_log[0]["gain_pct"] > 2
    assert rec.final_config != sc.config.model_dump()


def test_rejection_routes_back_to_diagnosis_then_tries_a_different_fix() -> None:
    rec = Pipeline(SCENARIOS["breakdowns"], 1, client(), ScriptedApprover(reject_n=1)).run()
    assert rec.outcome == "applied" and rec.iterations == 2
    steps = [t["step"] for t in rec.trace]
    assert steps.count("diagnosis") == 2 and steps.index("gate") < len(steps) - steps[::-1].index("diagnosis") - 1
    assert len(rec.diagnoses) == 2
    assert rec.gate_log[0]["action"] != rec.gate_log[1]["action"]
    assert [g["approved"] for g in rec.gate_log] == [False, True]


def test_iteration_cap_stops_the_rejection_loop() -> None:
    settings = PipelineSettings(max_iterations=2)
    pipe = Pipeline(SCENARIOS["slow_station"], 1, client(), ScriptedApprover(reject_n=99), settings)
    rec = pipe.run()
    assert rec.outcome == "rejected_max_iterations"
    assert rec.iterations == 2 and len(rec.gate_log) == 2 and rec.applied_action is None
    assert rec.final_config == SCENARIOS["slow_station"].config.model_dump()


def test_rejection_loop_with_default_cap_never_exceeds_three_rounds() -> None:
    rec = Pipeline(SCENARIOS["slow_station"], 1, client(), ScriptedApprover(reject_n=99)).run()
    assert rec.iterations == 3 and rec.applied_action is None
    assert rec.outcome in {"rejected_max_iterations", "no_recommendation"}


def test_cap_of_one_means_single_round() -> None:
    rec = Pipeline(SCENARIOS["slow_station"], 1, client(), ScriptedApprover(99), PipelineSettings(max_iterations=1)).run()
    assert rec.iterations == 1 and len(rec.gate_log) == 1


def test_no_verified_fix_never_reaches_gate_and_loop_is_capped() -> None:
    useless = {"candidates": lambda p: {"candidates": [{"type": "add_buffer", "station": 5, "size": 1}], "rationale": "bad"}}
    rec = Pipeline(SCENARIOS["slow_station"], 1, client(**useless), SimulatedApprover()).run()
    assert rec.outcome == "no_recommendation"
    assert rec.gate_log == [] and rec.applied_action is None
    assert rec.iterations == 3
    assert len(rec.action_rejections) >= 1
    stations = [d["bottleneck_station"] for d in rec.diagnoses]
    assert len(set(stations)) == 3  # re-diagnosis moved on to different stations


def test_validator_rejections_are_recorded_and_unsafe_fix_never_applied() -> None:
    rec = Pipeline(SCENARIOS["slow_station"], 4, client(), SimulatedApprover()).run()  # seed % 4 == 0: over-aggressive first proposal
    assert rec.outcome == "applied"
    assert any("size must be in 1..5" in r["reason"] for r in rec.action_rejections)
    assert rec.applied_action is not None and rec.applied_action.get("size", 1) <= 5


def test_ablation_without_simulation_recommends_unverified_first_valid_fix() -> None:
    rec = Pipeline(SCENARIOS["slow_station"], 4, client(), SimulatedApprover(), use_simulation=False).run()
    assert rec.system == "multi_agent_no_sim" and rec.outcome == "applied"
    assert "simulation" not in [t["step"] for t in rec.trace]
    assert rec.gate_log[0]["verified"] is False and rec.gate_log[0]["gain_pct"] is None
    assert any(r["reason"] for r in rec.action_rejections)  # invalid first proposal skipped


def test_injected_bad_recommendations_are_all_caught_when_twin_verifies() -> None:
    for seed in range(4):
        rec = Pipeline(SCENARIOS["slow_station"], seed, client(), SimulatedApprover(bad_rate=1.0, seed=seed)).run()
        assert all(g["injected"] for g in rec.gate_log)
        assert not any(g["approved"] for g in rec.gate_log) and rec.applied_action is None


def test_injected_harmful_fix_slips_through_without_twin_evidence() -> None:
    applied_bad = 0
    for seed in range(6):
        rec = Pipeline(SCENARIOS["slow_station"], seed, client(), SimulatedApprover(bad_rate=1.0, seed=seed), use_simulation=False).run()
        applied_bad += any(g["injected"] and g["approved"] for g in rec.gate_log)
    assert applied_bad > 0


def test_usage_is_metered_per_run() -> None:
    rec = Pipeline(SCENARIOS["breakdowns"], 1, client(), SimulatedApprover()).run()
    assert rec.usage["steps"] == 3 and rec.usage["by_role"] == {"monitor": 1, "diagnosis": 1, "candidates": 1}
    assert rec.usage["total_tokens"] > 0


def test_human_gate_pauses_then_reject_reruns_diagnosis_then_approve_applies() -> None:
    pipe = Pipeline(SCENARIOS["breakdowns"], 1, client(), approver=None)
    pipe.start()
    assert pipe.paused_at_gate
    assert pipe.current_state()["recommendation"]["verified"] is True
    pipe.submit_human_decision(False, "not convinced")
    assert pipe.paused_at_gate and pipe.current_state()["iteration"] == 2
    final = pipe.submit_human_decision(True)
    rec = pipe.to_record(final)
    assert not pipe.paused_at_gate and rec.outcome == "applied" and rec.iterations == 2
    assert [g["approved"] for g in rec.gate_log] == [False, True]


def test_human_mode_run_requires_simulated_approver() -> None:
    with pytest.raises(RuntimeError):
        Pipeline(SCENARIOS["breakdowns"], 1, client(), approver=None).run()
