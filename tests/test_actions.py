"""Typed action validation and application."""

from __future__ import annotations

import pytest

from src.actions import AddBuffer, ChangeMaintenance, RebalanceTask, RejectionLog, validate_and_apply
from src.scenarios import healthy_config

CFG = healthy_config()


def test_valid_add_buffer_applies_without_mutating_original() -> None:
    res = validate_and_apply({"type": "add_buffer", "station": 2, "size": 3}, CFG)
    assert res.ok and res.config is not None
    assert res.config.station(2).buffer_after == 8
    assert CFG.station(2).buffer_after == 5


def test_valid_rebalance_conserves_total_work() -> None:
    res = validate_and_apply(RebalanceTask(from_station=3, to_station=4, fraction=0.1), CFG)
    assert res.ok and res.config is not None
    before = sum(s.cycle_time_mean for s in CFG.stations)
    after = sum(s.cycle_time_mean for s in res.config.stations)
    assert after == pytest.approx(before)
    assert res.config.station(3).cycle_time_mean < CFG.station(3).cycle_time_mean


def test_valid_maintenance_scales_mtbf_and_mttr() -> None:
    res = validate_and_apply(ChangeMaintenance(station=4, mtbf_multiplier=1.5, mttr_multiplier=0.8), CFG)
    assert res.ok and res.config is not None
    assert res.config.station(4).mtbf == pytest.approx(CFG.station(4).mtbf * 1.5)
    assert res.config.station(4).mttr == pytest.approx(CFG.station(4).mttr * 0.8)


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ({"type": "add_buffer", "station": 5, "size": 2}, "last station"),
        ({"type": "add_buffer", "station": 2, "size": 6}, "size"),
        ({"type": "add_buffer", "station": 2, "size": 0}, "size"),
        ({"type": "rebalance_task", "from_station": 2, "to_station": 4, "fraction": 0.1}, "adjacent"),
        ({"type": "rebalance_task", "from_station": 2, "to_station": 3, "fraction": 0.9}, "fraction"),
        ({"type": "rebalance_task", "from_station": 2, "to_station": 9, "fraction": 0.1}, "1..5"),
        ({"type": "change_maintenance", "station": 2, "mtbf_multiplier": 0.5}, "mtbf_multiplier"),
        ({"type": "change_maintenance", "station": 2, "mttr_multiplier": 0.1}, "mttr_multiplier"),
        ({"type": "change_maintenance", "station": 2}, "no-op"),
        ({"type": "change_maintenance", "station": 7, "mtbf_multiplier": 1.5}, "1..5"),
    ],
)
def test_constraint_violations_are_rejected_with_reason(raw: dict, fragment: str) -> None:
    log = RejectionLog()
    res = validate_and_apply(raw, CFG, log)
    assert not res.ok and res.config is None
    assert fragment in res.reason
    assert log.entries[-1]["reason"] == res.reason


def test_buffer_capacity_cap() -> None:
    cfg = validate_and_apply(AddBuffer(station=2, size=5), CFG).config
    assert cfg is not None
    res = validate_and_apply(AddBuffer(station=2, size=5), cfg)
    assert not res.ok and "exceeds" in res.reason


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "delete_station", "station": 2},
        {"type": "add_buffer", "station": 2},
        {"type": "add_buffer", "station": "two", "size": 2},
        {"type": "add_buffer", "station": 2, "size": 2, "extra": 1},
        "add a buffer please",
        None,
    ],
)
def test_out_of_schema_proposals_are_rejected(raw: object) -> None:
    log = RejectionLog()
    res = validate_and_apply(raw, CFG, log)
    assert not res.ok and res.reason.startswith("schema:")
    assert len(log.entries) == 1


def test_maintenance_on_station_without_failures_rejected() -> None:
    cfg = CFG.model_copy(deep=True)
    cfg.stations[0] = cfg.stations[0].model_copy(update={"mtbf": None})
    res = validate_and_apply(ChangeMaintenance(station=1, mtbf_multiplier=1.5), cfg)
    assert not res.ok and "no failure model" in res.reason
