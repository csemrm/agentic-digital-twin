"""Twin validity: Little's law, capacity bound, reproducibility, fault impact."""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.scenarios import SCENARIOS, healthy_config
from src.twin import LineConfig, ProductionLine, StationConfig, replicate, simulate

SEEDS = list(range(8))


def _mean_throughput(config: LineConfig) -> float:
    return float(np.mean([r.throughput_per_shift for r in replicate(config, SEEDS)]))


def test_little_law_holds_on_long_run() -> None:
    line = ProductionLine(healthy_config(), seed=3).run(until=40 * 8 * 3600)
    s = line.little_stats()
    assert s["avg_wip"] == pytest.approx(s["throughput_rate"] * s["mean_sojourn"], rel=0.05)


def test_deterministic_line_hits_slowest_station_rate() -> None:
    stations = [
        StationConfig(cycle_time_mean=ct, cycle_time_cv=0.0, buffer_after=3 if i < 4 else None)
        for i, ct in enumerate([50, 60, 80, 55, 50])
    ]
    cfg = LineConfig(stations=stations)
    units = simulate(cfg, 0).throughput_per_shift
    bound = cfg.shift_seconds / 80
    assert units <= bound
    assert units >= bound - 6  # ramp-up loss of a few parts only


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_throughput_bounded_by_slowest_effective_station(name: str) -> None:
    cfg = SCENARIOS[name].config
    # The bound is an expected-rate bound; allow 3% sampling noise over 8 replications.
    assert _mean_throughput(cfg) <= 1.03 * cfg.capacity_bound_per_shift()


def test_same_seed_reproduces_exactly() -> None:
    cfg = SCENARIOS["mixed"].config
    a, b = simulate(cfg, 11), simulate(cfg, 11)
    assert a.throughput_per_shift == b.throughput_per_shift
    assert a.events == b.events
    assert a.kpis == b.kpis


def test_different_seeds_differ() -> None:
    cfg = SCENARIOS["breakdowns"].config
    assert simulate(cfg, 1).events != simulate(cfg, 2).events


@pytest.mark.parametrize("name", [n for n in SCENARIOS if n != "healthy"])
def test_each_fault_lowers_throughput_versus_healthy(name: str) -> None:
    healthy = _mean_throughput(SCENARIOS["healthy"].config)
    faulty = _mean_throughput(SCENARIOS[name].config)
    assert faulty < 0.95 * healthy


@pytest.mark.parametrize("name", ["slow_station", "breakdowns", "mixed"])
def test_ground_truth_matches_analytic_bottleneck(name: str) -> None:
    sc = SCENARIOS[name]
    assert sc.config.analytic_bottleneck() == sc.truth.station


def test_buffer_scenario_improves_with_bigger_buffer() -> None:
    sc = SCENARIOS["buffer"]
    bigger = sc.config.model_copy(deep=True)
    bigger.stations[1] = bigger.stations[1].model_copy(update={"buffer_after": 8})
    assert _mean_throughput(bigger) > _mean_throughput(sc.config)


def test_kpi_state_fractions_sum_to_one() -> None:
    res = simulate(SCENARIOS["mixed"].config, 5)
    for sid, st in res.kpis["stations"].items():
        total = st["utilization"] + st["blocked"] + st["starved"] + st["down"]
        assert total == pytest.approx(1.0, abs=1e-6), sid


def test_rolling_windows_partition_the_shift() -> None:
    res = simulate(SCENARIOS["healthy"].config, 2)
    assert sum(w["throughput_units"] for w in res.rolling) == res.kpis["throughput_units"]
    assert len(res.rolling) == 16


def test_event_log_is_json_serialisable_and_has_breakdowns() -> None:
    res = simulate(SCENARIOS["breakdowns"].config, 0)
    decoded = json.loads(json.dumps(res.events))
    kinds = {e["event"] for e in decoded}
    assert {"breakdown_start", "breakdown_end"} <= kinds
    assert all(e["station"] in range(1, 6) for e in decoded)


def test_config_rejects_missing_or_extra_buffers() -> None:
    with pytest.raises(ValueError):
        LineConfig(stations=[StationConfig(cycle_time_mean=10), StationConfig(cycle_time_mean=10)])
    with pytest.raises(ValueError):
        LineConfig(
            stations=[StationConfig(cycle_time_mean=10, buffer_after=2), StationConfig(cycle_time_mean=10, buffer_after=2)]
        )
