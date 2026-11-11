"""Turn a twin run into the compact observation the agents reason over."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from src.scenarios import healthy_config
from src.twin import LineConfig, RunResult, simulate

REFERENCE_SEEDS = range(100, 105)


@lru_cache(maxsize=1)
def reference_throughput() -> float:
    """Normal output (units/shift): mean of the healthy line over a few fixed seeds."""
    return float(np.mean([simulate(healthy_config(), s).throughput_per_shift for s in REFERENCE_SEEDS]))


@dataclass
class Observation:
    """A simulated shift plus the compact JSON-able payload shown to agents."""

    result: RunResult
    payload: dict[str, Any]


def _event_summary(events: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = defaultdict(lambda: {"repairs": 0, "repair_s": 0.0, "blocked_s": 0.0, "starved_s": 0.0})
    for e in events:
        s = out[e["station"]]
        if e["event"] == "breakdown_end":
            s["repairs"] += 1
            s["repair_s"] += e["duration"]
        elif e["event"] == "blocked_end":
            s["blocked_s"] += e["duration"]
        elif e["event"] == "starved_end":
            s["starved_s"] += e["duration"]
    return out


def observe(config: LineConfig, seed: int) -> Observation:
    """Simulate one shift of ``config`` and summarise it for agents.

    Agents see engineered standards (standard cycle time per station) and the
    current buffer capacities, but never the scenario label or fault settings.
    """
    result = simulate(config, seed)
    k, std = result.kpis, healthy_config()
    ev = _event_summary(result.events)
    stations = []
    for sid, st in k["stations"].items():
        busy_s = st["utilization"] * result.duration
        measured = busy_s / st["completed"] if st["completed"] else None
        e = ev[sid]
        stations.append(
            {
                "id": sid,
                "utilization": round(st["utilization"], 3),
                "blocked": round(st["blocked"], 3),
                "starved": round(st["starved"], 3),
                "down": round(st["down"], 3),
                "breakdowns": st["breakdowns"],
                "mean_repair_s": round(e["repair_s"] / e["repairs"], 1) if e["repairs"] else 0.0,
                "measured_cycle_time_s": round(measured, 1) if measured else None,
                "standard_cycle_time_s": std.station(sid).cycle_time_mean,
                "buffer_after_capacity": config.station(sid).buffer_after,
                "buffer_after_avg_level": round(k["buffers"][sid]["avg_level"], 2) if sid in k["buffers"] else None,
            }
        )
    ref = reference_throughput()
    payload = {
        "throughput_per_shift": round(result.throughput_per_shift, 1),
        "reference_throughput": round(ref, 1),
        "throughput_vs_reference_pct": round(100 * (result.throughput_per_shift / ref - 1), 1),
        "stations": stations,
        "window_throughput_trend": [w["throughput_units"] for w in result.rolling],
    }
    return Observation(result, payload)
