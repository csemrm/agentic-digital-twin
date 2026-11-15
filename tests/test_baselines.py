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


# --- TOC heuristic ---------------------------------------------------------------


def test_toc_picks_fix_matching_observed_symptom() -> None:
    from src.baselines import run_toc_heuristic

    slow = run_toc_heuristic(SCENARIOS["slow_station"], 1, SimulatedApprover())
    assert slow.outcome == "applied" and slow.applied_action["type"] == "rebalance_task" and slow.applied_action["from_station"] == 2
    assert slow.diagnoses[0]["fault_type"] == "slow_station"
    brk = run_toc_heuristic(SCENARIOS["breakdowns"], 1, SimulatedApprover())
    assert brk.applied_action["type"] == "change_maintenance" and brk.applied_action["station"] == SCENARIOS["breakdowns"].truth.station


def test_toc_is_unverified_llm_free_and_leaves_healthy_line_alone() -> None:
    from src.baselines import run_toc_heuristic

    rec = run_toc_heuristic(SCENARIOS["slow_station"], 1, SimulatedApprover())
    assert rec.system == "toc_heuristic" and rec.usage["steps"] == 0 and rec.usage["total_tokens"] == 0
    assert rec.gate_log[0]["verified"] is False and rec.iterations == 1
    healthy = run_toc_heuristic(SCENARIOS["healthy"], 1, SimulatedApprover())
    assert healthy.outcome == "no_fault" and healthy.applied_action is None


def test_toc_rejection_ends_after_one_round() -> None:
    from src.baselines import run_toc_heuristic

    rec = run_toc_heuristic(SCENARIOS["slow_station"], 1, RejectAll())
    assert rec.outcome == "rejected" and rec.applied_action is None
    assert rec.final_config == SCENARIOS["slow_station"].config.model_dump()


def test_toc_buffer_goes_before_the_constraint_and_stays_in_bounds() -> None:
    from src.baselines.toc_heuristic import classify_and_act

    def obs(active_station: int) -> dict:
        return {"stations": [
            {"id": i, "utilization": 0.9 if i == active_station else 0.5, "down": 0.0, "measured_cycle_time_s": 60.0, "standard_cycle_time_s": 60.0}
            for i in range(1, 6)]}

    _, a1 = classify_and_act(obs(1), 5, set())
    _, a3 = classify_and_act(obs(3), 5, set())
    assert a1 == {"type": "add_buffer", "station": 1, "size": 3}  # first station: nothing upstream, buffer after it
    assert a3 == {"type": "add_buffer", "station": 2, "size": 3}


# --- twin search -----------------------------------------------------------------


def test_twin_search_grid_is_all_valid_and_covers_every_action_type() -> None:
    from src.actions import validate_and_apply
    from src.baselines.twin_search import action_grid

    cfg = SCENARIOS["mixed"].config
    grid = action_grid(cfg)
    assert {a["type"] for a in grid} == {"add_buffer", "rebalance_task", "change_maintenance"}
    assert all(validate_and_apply(a, cfg).ok for a in grid)
    assert len(grid) == len({repr(sorted(a.items())) for a in grid})


def test_twin_search_verifies_best_fix_without_llm_and_reports_cost() -> None:
    from src.baselines import run_twin_search

    s = PipelineSettings()
    rec = run_twin_search(SCENARIOS["slow_station"], 1, SimulatedApprover(), s)
    assert rec.system == "twin_search" and rec.outcome == "applied"
    assert rec.usage["steps"] == 0 and rec.usage["total_tokens"] == 0 and rec.usage["twin_sims"] > 8 * 40
    assert rec.gate_log[0]["verified"] is True and rec.gate_log[0]["gain_pct"] >= s.min_gain_pct
    assert rec.diagnoses[0]["fault_type"] == "unspecified"


def test_twin_search_healthy_line_costs_nothing() -> None:
    from src.baselines import run_twin_search

    rec = run_twin_search(SCENARIOS["healthy"], 1, SimulatedApprover())
    assert rec.outcome == "no_fault" and rec.applied_action is None and rec.usage["twin_sims"] == 0


def test_twin_search_offers_next_best_fix_after_gate_rejection_up_to_round_cap() -> None:
    from src.baselines import run_twin_search

    rec = run_twin_search(SCENARIOS["slow_station"], 1, RejectAll(), PipelineSettings(max_iterations=2))
    assert rec.outcome == "rejected_max_iterations" and rec.iterations == 2 and rec.applied_action is None
    assert rec.gate_log[0]["action"] != rec.gate_log[1]["action"]
    assert rec.gate_log[0]["gain_pct"] >= rec.gate_log[1]["gain_pct"]


def test_twin_search_gate_catches_injected_bad_fixes_using_its_evidence() -> None:
    from src.baselines import run_twin_search
    from src.eval.truth import TruthEvaluator

    truth, sc = TruthEvaluator(), SCENARIOS["slow_station"]
    seen = 0
    for seed in range(1, 7):
        rec = run_twin_search(sc, seed, SimulatedApprover(bad_rate=1.0, seed=seed))
        for g in rec.gate_log:
            if g["injected"]:
                seen += 1
                assert truth.action_status(sc.config, g["action"]) == "ok" or not g["approved"]
    assert seen > 0
