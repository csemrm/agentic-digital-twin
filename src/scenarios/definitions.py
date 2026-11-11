"""Seeded fault scenarios, each with a known ground-truth bottleneck label.

The healthy line is a mildly unbalanced 5-station serial line (illustrative
parameters in the spirit of textbook line-balancing examples; see
docs/ASSUMPTIONS.md). Each fault scenario perturbs it in one documented way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.twin.config import LineConfig, StationConfig

FAULT_TYPES = ("none", "slow_station", "breakdowns", "buffer", "mixed")

BASE_CYCLE_TIMES = (60.0, 62.0, 63.0, 61.0, 60.0)
BASE_MTBF = 7200.0
BASE_MTTR = 180.0
BASE_BUFFER = 5
BASE_CV = 0.25


@dataclass(frozen=True)
class GroundTruth:
    """Ground-truth label of a scenario.

    ``station`` is the station that owns the fault (for ``buffer`` faults, the
    station whose downstream buffer is undersized); ``None`` for a healthy line.
    """

    station: int | None
    fault_type: str
    secondary_station: int | None = None


@dataclass(frozen=True)
class Scenario:
    """A named line configuration plus its ground truth."""

    name: str
    description: str
    config: LineConfig
    truth: GroundTruth
    tags: tuple[str, ...] = field(default_factory=tuple)


def healthy_config() -> LineConfig:
    """Return the healthy baseline line."""
    stations = [
        StationConfig(
            cycle_time_mean=ct,
            cycle_time_cv=BASE_CV,
            mtbf=BASE_MTBF,
            mttr=BASE_MTTR,
            buffer_after=BASE_BUFFER if i < len(BASE_CYCLE_TIMES) - 1 else None,
        )
        for i, ct in enumerate(BASE_CYCLE_TIMES)
    ]
    return LineConfig(stations=stations)


def _modified(**per_station: dict) -> LineConfig:
    cfg = healthy_config()
    for key, changes in per_station.items():
        sid = int(key.removeprefix("s"))
        cfg.stations[sid - 1] = cfg.stations[sid - 1].model_copy(update=changes)
    return cfg


def build_scenarios() -> dict[str, Scenario]:
    """Return all scenarios keyed by name."""
    scenarios = [
        Scenario("healthy", "Balanced line, no fault.", healthy_config(), GroundTruth(None, "none")),
        Scenario(
            "slow_station",
            "Station 2 runs at a degraded cycle time (95 s vs 62 s).",
            _modified(s2={"cycle_time_mean": 95.0}),
            GroundTruth(2, "slow_station"),
        ),
        Scenario(
            "breakdowns",
            "Station 4 breaks down often (MTBF 900 s, MTTR 300 s).",
            _modified(s4={"mtbf": 900.0, "mttr": 300.0}),
            GroundTruth(4, "breakdowns"),
        ),
        Scenario(
            "buffer",
            "Buffer after station 2 has capacity 1 while station 2 fails often and station 3 is variable.",
            _modified(
                s2={"buffer_after": 1, "mtbf": 1500.0, "mttr": 360.0},
                s3={"cycle_time_cv": 0.5},
            ),
            GroundTruth(2, "buffer"),
        ),
        Scenario(
            "mixed",
            "Station 4 breaks down severely (MTBF 800 s, MTTR 400 s) and station 2 is slow (75 s).",
            _modified(s2={"cycle_time_mean": 75.0}, s4={"mtbf": 800.0, "mttr": 400.0}),
            GroundTruth(4, "mixed", secondary_station=2),
        ),
    ]
    return {s.name: s for s in scenarios}


SCENARIOS = build_scenarios()
SCENARIO_NAMES = tuple(SCENARIOS)
