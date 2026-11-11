"""Rule-based and single-agent baselines."""

from __future__ import annotations

import pytest

from src.agents import PipelineSettings, SimulatedApprover, mock_client
from src.agents.types import GateDecision
from src.baselines import run_rule_based, run_single_agent
from src.scenarios import SCENARIOS


class RejectAll(SimulatedApprover):
    def decide(self, rec, config):  # type: ignore[no-untyped-def]
        return GateDecision(approved=False, reason="no")


def test_rule_based_adds_buffer_after_highest_utilization_station() -> None:
    rec = run_rule_based(SCENARIOS["slow_station"], 1, SimulatedApprover())
    assert rec.system == "rule_based" and rec.outcome == "applied"
    assert rec.usage["steps"] == 0 and rec.usage["total_tokens"] == 0
    assert rec.applied_action == {"type": "add_buffer", "station": 2, "size": 3}
    assert rec.gate_log[0]["verified"] is False


def test_rule_based_misses_breakdown_station_that_has_lower_utilization() -> None:
    rec = run_rule_based(SCENARIOS["breakdowns"], 1, SimulatedApprover())
    assert rec.diagnoses[0]["bottleneck_station"] != SCENARIOS["breakdowns"].truth.station


def test_rule_based_leaves_healthy_line_alone() -> None:
    rec = run_rule_based(SCENARIOS["healthy"], 1, SimulatedApprover())
    assert rec.outcome == "no_fault" and rec.applied_action is None


def test_rule_based_rejection_ends_after_one_round() -> None:
    rec = run_rule_based(SCENARIOS["slow_station"], 1, RejectAll())
    assert rec.outcome == "rejected" and rec.applied_action is None
    assert rec.final_config == SCENARIOS["slow_station"].config.model_dump()


def test_rule_based_on_last_station_buffers_before_it() -> None:
    from src.scenarios.definitions import Scenario, GroundTruth, healthy_config

    cfg = healthy_config()
    cfg.stations[4] = cfg.stations[4].model_copy(update={"cycle_time_mean": 120.0})
    rec = run_rule_based(Scenario("slow5", "d", cfg, GroundTruth(5, "slow_station")), 1, SimulatedApprover())
    assert rec.applied_action == {"type": "add_buffer", "station": 4, "size": 3}


@pytest.mark.parametrize("name", ["slow_station", "breakdowns", "buffer", "mixed"])
def test_single_agent_one_call_no_simulation(name: str) -> None:
    rec = run_single_agent(SCENARIOS[name], 1, mock_client(), SimulatedApprover())
    assert rec.system == "single_agent" and rec.outcome == "applied"
    assert rec.usage["steps"] == 1 and rec.usage["by_role"] == {"single_agent": 1}
    assert rec.gate_log[0]["verified"] is False and rec.gate_log[0]["gain_pct"] is None
    assert rec.final_diagnosis["bottleneck_station"] == SCENARIOS[name].truth.station


def test_single_agent_recovers_from_validator_rejection_with_extra_step() -> None:
    rec = run_single_agent(SCENARIOS["slow_station"], 4, mock_client(), SimulatedApprover())  # seed 4: unsafe first proposal
    assert rec.outcome == "applied" and rec.usage["steps"] == 2 and rec.iterations == 2
    assert len(rec.action_rejections) == 1 and rec.gate_log[0]["iteration"] == 2


def test_single_agent_healthy_ends_without_action() -> None:
    rec = run_single_agent(SCENARIOS["healthy"], 1, mock_client(), SimulatedApprover())
    assert rec.outcome == "no_fault" and rec.applied_action is None and rec.gate_log == []


def test_single_agent_respects_round_cap_when_gate_rejects() -> None:
    rec = run_single_agent(SCENARIOS["slow_station"], 1, mock_client(), RejectAll(), PipelineSettings(max_iterations=2))
    assert rec.outcome == "rejected_max_iterations" and rec.iterations == 2 and len(rec.gate_log) == 2
    assert rec.gate_log[0]["action"] != rec.gate_log[1]["action"]
    assert rec.applied_action is None


def test_single_agent_cannot_catch_harmful_injected_fix_without_twin_evidence() -> None:
    caught_none = 0
    for seed in range(6):
        rec = run_single_agent(SCENARIOS["slow_station"], seed, mock_client(), SimulatedApprover(bad_rate=1.0, seed=seed))
        caught_none += any(g["injected"] and g["approved"] for g in rec.gate_log)
    assert caught_none > 0
