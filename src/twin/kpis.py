"""KPI computation over rolling windows from cumulative twin snapshots."""

from __future__ import annotations

from typing import Any

import numpy as np

from src.twin.config import LineConfig


def _nearest(snapshots: list[dict[str, Any]], t: float) -> int:
    return int(np.argmin([abs(s["t"] - t) for s in snapshots]))


def window_kpis(snapshots: list[dict[str, Any]], config: LineConfig, t_start: float, t_end: float) -> dict[str, Any]:
    """Compute KPIs between the snapshots nearest ``t_start`` and ``t_end``.

    Returns throughput (units in window and normalised to units/shift),
    per-station utilization / blocked / starved / down fractions, breakdown
    counts, mean buffer levels, and mean WIP.
    """
    i0, i1 = _nearest(snapshots, t_start), _nearest(snapshots, t_end)
    a, b = snapshots[i0], snapshots[i1]
    span = b["t"] - a["t"]
    if span <= 0:
        raise ValueError("empty KPI window")
    units = b["exited"] - a["exited"]
    window = snapshots[i0 : i1 + 1]
    stations: dict[int, dict[str, float]] = {}
    for k in range(config.n_stations):
        sa, sb = a["stations"][k], b["stations"][k]
        stations[k + 1] = {
            "utilization": (sb["busy"] - sa["busy"]) / span,
            "blocked": (sb["blocked"] - sa["blocked"]) / span,
            "starved": (sb["starved"] - sa["starved"]) / span,
            "down": (sb["down"] - sa["down"]) / span,
            "breakdowns": sb["breakdowns"] - sa["breakdowns"],
            "completed": sb["completed"] - sa["completed"],
        }
    buffers = {
        k + 1: {
            "avg_level": float(np.mean([s["levels"][k] for s in window])),
            "capacity": config.stations[k].buffer_after,
        }
        for k in range(config.n_stations - 1)
    }
    return {
        "t_start": a["t"],
        "t_end": b["t"],
        "throughput_units": units,
        "throughput_per_shift": units / span * config.shift_seconds,
        "wip_avg": (b["wip_area"] - a["wip_area"]) / span,
        "stations": stations,
        "buffers": buffers,
    }
