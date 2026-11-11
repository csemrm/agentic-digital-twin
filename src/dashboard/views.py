"""Pure data-shaping helpers for the dashboard (kept out of the Streamlit script so they are testable)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.twin import LineConfig, RunResult, replicate

BEFORE_AFTER_SEEDS = list(range(3000, 3008))

ARCHITECTURE_DOT = """
digraph G {
  rankdir=LR; node [shape=box, style=rounded, fontsize=10];
  twin [label="Digital twin\\n(SimPy line)", shape=cylinder];
  mon [label="Monitor"]; dia [label="Diagnosis"]; sim [label="Simulation\\n(test each fix\\nin the twin)"];
  gate [label="Human gate\\nApprove / Reject", style="rounded,filled", fillcolor="#ffe9a8"];
  apply [label="Apply fix"];
  twin -> mon -> dia -> sim -> gate;
  gate -> apply [label="approve"]; apply -> twin;
  gate -> dia [label="reject", style=dashed];
  sim -> twin [dir=both, style=dotted, label="replications"];
}
"""


def station_frame(observation: dict[str, Any]) -> pd.DataFrame:
    """Per-station time fractions (busy / blocked / starved / down) for a stacked bar chart."""
    rows = {f"S{s['id']}": {"busy": s["utilization"], "blocked": s["blocked"], "starved": s["starved"], "down": s["down"]} for s in observation["stations"]}
    return pd.DataFrame.from_dict(rows, orient="index")


def throughput_frame(result: RunResult) -> pd.DataFrame:
    """Units finished per rolling window, indexed by window end (hours)."""
    return pd.DataFrame({"units per window": [w["throughput_units"] for w in result.rolling]}, index=[round(w["t_end"] / 3600, 2) for w in result.rolling])


def action_label(action: dict[str, Any]) -> str:
    """Compact human-readable form of a typed action, e.g. ``add_buffer(station=2, size=3)``."""
    params = ", ".join(f"{k}={v}" for k, v in action.items() if k != "type")
    return f"{action.get('type', '?')}({params})"


def candidates_frame(candidates: list[dict[str, Any]]) -> pd.DataFrame:
    """Table of simulated candidate fixes with before/after throughput."""
    rows = []
    for c in candidates:
        a = c["action"]
        rows.append(
            {
                "fix": action_label(a),
                "valid": c.get("valid", True),
                "before (units/shift)": None if c.get("baseline_mean") is None else round(c["baseline_mean"], 1),
                "after (units/shift)": None if c.get("new_mean") is None else round(c["new_mean"], 1),
                "gain %": None if c.get("gain_pct") is None else round(c["gain_pct"], 1),
                "95% CI %": None if c.get("ci_low_pct") is None else f"[{c['ci_low_pct']:.1f}, {c['ci_high_pct']:.1f}]",
                "p": None if c.get("p_value") is None else round(c["p_value"], 4),
                "passes": c.get("passed", False),
                "note": c.get("reason", ""),
            }
        )
    return pd.DataFrame(rows)


def trace_frame(trace: list[dict[str, Any]]) -> pd.DataFrame:
    """Agent trace as a table."""
    return pd.DataFrame([{"step": i + 1, "agent": t["step"], "detail": t["detail"]} for i, t in enumerate(trace)])


def before_after(before: LineConfig, after: LineConfig) -> dict[str, float]:
    """Mean units/shift before and after a fix on dashboard-only seeds."""
    b = float(np.mean([r.throughput_per_shift for r in replicate(before, BEFORE_AFTER_SEEDS)]))
    a = float(np.mean([r.throughput_per_shift for r in replicate(after, BEFORE_AFTER_SEEDS)]))
    return {"before": b, "after": a, "gain_pct": 100 * (a / b - 1)}
