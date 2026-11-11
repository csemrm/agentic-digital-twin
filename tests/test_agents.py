"""Observation, Simulation agent, simulated approver and typed agent messages."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.actions import RejectionLog
from src.agents import MOCK_HANDLERS, PipelineSettings, SimulatedApprover
from src.agents.mock_roles import candidates_handler, diagnosis_handler, monitor_handler
from src.agents.observe import observe, reference_throughput
from src.agents.simulation import evaluate_candidate, run_simulation_agent
from src.agents.types import Diagnosis, Recommendation
from src.scenarios import SCENARIOS

SETTINGS = PipelineSettings()


def test_observation_never_leaks_labels_and_is_compact() -> None:
    obs = observe(SCENARIOS["breakdowns"].config, 1).payload
    text = str(obs)
    assert "fault" not in text and "breakdowns'" not in text.replace("'breakdowns': ", "")
    assert len(obs["stations"]) == 5 and len(str(obs)) < 3500


def test_reference_throughput_is_healthy_level() -> None:
    assert 380 < reference_throughput() < 440


@pytest.mark.parametrize("name", ["slow_station", "breakdowns", "buffer", "mixed"])
def test_mock_diagnosis_finds_seeded_bottleneck(name: str) -> None:
    sc = SCENARIOS[name]
    obs = observe(sc.config, 1).payload
    d = diagnosis_handler({"observation": obs, "monitor": monitor_handler({"observation": obs}), "feedback": []})
    assert d["bottleneck_station"] == sc.truth.station


def test_mock_diagnosis_reports_no_fault_on_healthy_line() -> None:
    obs = observe(SCENARIOS["healthy"].config, 1).payload
    assert diagnosis_handler({"observation": obs, "feedback": []})["fault_type"] == "none"


def test_diagnosis_skips_station_without_viable_fix() -> None:
    obs = observe(SCENARIOS["slow_station"].config, 1).payload
    first = diagnosis_handler({"observation": obs, "feedback": []})["bottleneck_station"]
    again = diagnosis_handler({"observation": obs, "feedback": [{"kind": "no_viable_fix", "station": first}]})
    assert again["bottleneck_station"] != first


def test_diagnosis_model_requires_station_iff_fault() -> None:
    with pytest.raises(ValidationError):
        Diagnosis(bottleneck_station=None, fault_type="slow_station", explanation="x", confidence=0.5)
    with pytest.raises(ValidationError):
        Diagnosis(bottleneck_station=2, fault_type="none", explanation="x", confidence=0.5)
    with pytest.raises(ValidationError):
        Diagnosis(bottleneck_station=9, fault_type="buffer", explanation="x", confidence=0.5)


def test_simulation_passes_good_fix_and_fails_harmful_and_invalid() -> None:
    cfg = SCENARIOS["slow_station"].config
    good = evaluate_candidate(cfg, {"type": "rebalance_task", "from_station": 2, "to_station": 1, "fraction": 0.2}, SETTINGS)
    harmful = evaluate_candidate(cfg, {"type": "rebalance_task", "from_station": 1, "to_station": 2, "fraction": 0.3}, SETTINGS)
    log = RejectionLog()
    invalid = evaluate_candidate(cfg, {"type": "add_buffer", "station": 5, "size": 1}, SETTINGS, log=log)
    assert good.valid and good.passed and good.gain_pct > 10 and good.ci_low_pct < good.gain_pct < good.ci_high_pct
    assert harmful.valid and not harmful.passed and harmful.gain_pct < 0
    assert not invalid.valid and not invalid.passed and len(log.entries) == 1


def test_noop_effect_fix_is_not_passed() -> None:
    cfg = SCENARIOS["slow_station"].config
    useless = evaluate_candidate(cfg, {"type": "add_buffer", "station": 4, "size": 1}, SETTINGS)
    assert useless.valid and not useless.passed


def test_simulation_agent_ranks_passed_first_by_gain_and_dedupes() -> None:
    cfg = SCENARIOS["breakdowns"].config
    cands = [
        {"type": "add_buffer", "station": 5 - 1, "size": 1},
        {"type": "change_maintenance", "station": 4, "mtbf_multiplier": 2.0, "mttr_multiplier": 0.5},
        {"type": "change_maintenance", "station": 4, "mtbf_multiplier": 1.5, "mttr_multiplier": 0.7},
        {"type": "change_maintenance", "station": 4, "mtbf_multiplier": 1.5, "mttr_multiplier": 0.7},
        {"type": "bogus"},
    ]
    results = run_simulation_agent(cfg, cands, SETTINGS)
    assert len(results) == 4
    passed = [r for r in results if r.passed]
    assert passed and results[: len(passed)] == passed
    assert [r.gain_pct for r in passed] == sorted((r.gain_pct for r in passed), reverse=True)
    assert not results[-1].valid


def test_simulation_is_deterministic() -> None:
    cfg = SCENARIOS["mixed"].config
    act = {"type": "change_maintenance", "station": 4, "mtbf_multiplier": 1.5, "mttr_multiplier": 0.7}
    assert evaluate_candidate(cfg, act, SETTINGS) == evaluate_candidate(cfg, act, SETTINGS)


def test_candidate_handler_excludes_tried_actions_and_respects_cap() -> None:
    stations = [{"id": i, "utilization": 0.8, "buffer_after_capacity": 5} for i in range(1, 6)]
    diag = {"bottleneck_station": 4, "fault_type": "breakdowns"}
    base = {"diagnosis": diag, "stations": stations, "seed": 1, "iteration": 1, "max_candidates": 2}
    first = candidates_handler(base)["candidates"]
    again = candidates_handler({**base, "tried_actions": first[:1]})["candidates"]
    assert len(first) == 2 and first[0] not in again


def test_candidate_handler_never_proposes_buffer_after_last_station() -> None:
    stations = [{"id": i, "utilization": 0.8, "buffer_after_capacity": 5} for i in range(1, 6)]
    diag = {"bottleneck_station": 5, "fault_type": "slow_station"}
    cands = candidates_handler({"diagnosis": diag, "stations": stations, "seed": 1, "iteration": 1})["candidates"]
    assert all(not (c["type"] == "add_buffer" and c["station"] == 5) for c in cands)


def test_all_roles_registered_for_mock_mode() -> None:
    assert {"monitor", "diagnosis", "candidates"} <= set(MOCK_HANDLERS)


def _rec(action: dict, gain: float | None, verified: bool) -> Recommendation:
    from src.agents.types import CandidateResult

    ev = CandidateResult(action=action, valid=True, gain_pct=gain, passed=True) if gain is not None else None
    return Recommendation(action=action, rationale="r", verified=verified, evidence=ev)


def test_approver_uses_only_presented_evidence() -> None:
    cfg = SCENARIOS["healthy"].config
    harmful = {"type": "rebalance_task", "from_station": 1, "to_station": 2, "fraction": 0.3}
    approver = SimulatedApprover(min_gain_pct=2.0)
    assert approver.decide(_rec(harmful, -5.0, True), cfg).approved is False
    assert approver.decide(_rec(harmful, 1.0, True), cfg).approved is False
    assert approver.decide(_rec(harmful, 6.0, True), cfg).approved is True
    # no twin evidence: a harmful but valid action cannot be caught
    assert approver.decide(_rec(harmful, None, False), cfg).approved is True
    invalid = {"type": "add_buffer", "station": 5, "size": 2}
    assert approver.decide(_rec(invalid, None, False), cfg).approved is False


def test_injection_off_by_default_and_always_on_at_rate_one() -> None:
    cfg = SCENARIOS["slow_station"].config
    good = _rec({"type": "add_buffer", "station": 2, "size": 2}, 5.0, True)
    diag = {"bottleneck_station": 2}
    assert SimulatedApprover().maybe_inject(good, cfg, diag, SETTINGS) == (good, False)
    rec, injected = SimulatedApprover(bad_rate=1.0, seed=3).maybe_inject(good, cfg, diag, SETTINGS)
    assert injected and rec.action != good.action
