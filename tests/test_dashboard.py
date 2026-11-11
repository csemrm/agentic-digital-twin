"""Dashboard view helpers and a headless Streamlit run of the app (mock mode)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.agents import Pipeline, SimulatedApprover, mock_client
from src.dashboard import views
from src.scenarios import SCENARIOS

APP = str(Path(__file__).resolve().parents[1] / "src" / "dashboard" / "app.py")


def test_action_label_is_compact() -> None:
    assert views.action_label({"type": "add_buffer", "station": 2, "size": 3}) == "add_buffer(station=2, size=3)"


def test_frames_have_expected_shape() -> None:
    rec = Pipeline(SCENARIOS["breakdowns"], 1, mock_client(), SimulatedApprover()).run()
    pipe = Pipeline(SCENARIOS["breakdowns"], 1, mock_client(), approver=None)
    state = pipe.start()
    stations = views.station_frame(state["observation"])
    assert list(stations.index) == ["S1", "S2", "S3", "S4", "S5"] and list(stations.columns) == ["busy", "blocked", "starved", "down"]
    assert (stations.sum(axis=1).round(2) == 1.0).all()
    cands = views.candidates_frame(state["candidates"])
    assert {"fix", "before (units/shift)", "after (units/shift)", "gain %", "passes"} <= set(cands.columns)
    assert cands["passes"].any() and len(views.trace_frame(rec.trace)) == len(rec.trace)


def test_candidates_frame_shows_invalid_candidates_with_reason() -> None:
    frame = views.candidates_frame([{"action": {"type": "add_buffer", "station": 5, "size": 1}, "valid": False, "reason": "no buffer", "passed": False}])
    assert frame.iloc[0]["note"] == "no buffer" and not frame.iloc[0]["valid"] and frame.iloc[0]["gain %"] is None


def test_before_after_reports_gain_for_a_good_fix() -> None:
    sc = SCENARIOS["slow_station"]
    rec = Pipeline(sc, 1, mock_client(), SimulatedApprover()).run()
    from src.twin import LineConfig

    res = views.before_after(sc.config, LineConfig.model_validate(rec.final_config))
    assert res["after"] > res["before"] and res["gain_pct"] > 5


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    return at


def test_app_loads_with_prompt_and_no_errors(app: AppTest) -> None:
    assert not app.exception
    assert any("Start run" in b.label for b in app.button)


def _start(app: AppTest, scenario: str, seed: int = 1) -> None:
    app.selectbox(key="scenario_pick").set_value(scenario)
    app.number_input(key="seed_pick").set_value(seed)
    app.button(key="start").click().run()


def test_app_approve_flow_applies_fix(app: AppTest) -> None:
    _start(app, "breakdowns")
    assert not app.exception
    assert {b.key for b in app.button} >= {"approve", "reject"}
    app.button(key="approve").click().run()
    assert not app.exception
    assert any("Outcome: applied" in s.value for s in app.subheader)
    assert not any(b.key == "approve" for b in app.button)


def test_app_reject_triggers_rediagnosis_then_approve(app: AppTest) -> None:
    _start(app, "breakdowns")
    app.button(key="reject").click().run()
    assert not app.exception
    assert any("round 2" in m.value for m in app.markdown)
    assert any(b.key == "approve" for b in app.button)  # paused at gate again
    app.button(key="approve").click().run()
    assert any("Outcome: applied" in s.value for s in app.subheader)


def test_app_healthy_scenario_needs_no_gate(app: AppTest) -> None:
    _start(app, "healthy")
    assert not app.exception
    assert not any(b.key == "approve" for b in app.button)
    assert any("Outcome: no_fault" in s.value for s in app.subheader)


def test_app_without_simulation_warns_unverified(app: AppTest) -> None:
    app.checkbox(key="use_sim").set_value(False)
    _start(app, "slow_station")
    assert not app.exception
    assert any("not simulated" in w.value for w in app.warning)
