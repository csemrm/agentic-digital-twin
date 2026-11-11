"""Grouped bar charts: one metric, scenarios on the x axis, one bar per system with 95% CI."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SYSTEM_ORDER = ["rule_based", "single_agent", "multi_agent_no_sim", "multi_agent"]
LABELS = {
    "station_correct": ("Bottleneck accuracy", "fraction correct"),
    "gain_pct": ("Throughput gain after fix", "% vs before"),
    "invalid_fix": ("Invalid-fix rate", "fraction of runs"),
    "steps": ("LLM steps per run", "steps"),
    "total_tokens": ("Tokens per run", "tokens"),
    "expl_quality": ("Explanation quality (judge)", "score 1-5"),
    "catch_rate": ("Human-gate catch rate (stress test)", "fraction of bad recs rejected"),
}


def grouped_bars(table: pd.DataFrame, value: str, title: str, ylabel: str, out: Path, tag: str) -> None:
    """Draw ``value`` by scenario and system from a table with ``mean``/``ci_low``/``ci_high`` (or ``catch_rate``)."""
    systems = [s for s in SYSTEM_ORDER if s in set(table["system"])]
    scenarios = list(dict.fromkeys(table["scenario"]))
    lo_col, hi_col = ("ci_low", "ci_high")
    width = 0.8 / max(len(systems), 1)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, system in enumerate(systems):
        sub = table[table["system"] == system].set_index("scenario").reindex(scenarios)
        y = sub[value].to_numpy(dtype=float)
        err = np.vstack([y - sub[lo_col].to_numpy(dtype=float), sub[hi_col].to_numpy(dtype=float) - y])
        err = np.nan_to_num(np.clip(err, 0, None))
        ax.bar(np.arange(len(scenarios)) + i * width, np.nan_to_num(y), width, yerr=err, capsize=2, label=system)
    ax.set_xticks(np.arange(len(scenarios)) + width * (len(systems) - 1) / 2)
    ax.set_xticklabels(scenarios)
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title} [{tag}]")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    plt.close(fig)


def plot_all(summary: pd.DataFrame, catch: pd.DataFrame, out_dir: Path, tag: str) -> list[Path]:
    """Write one PNG per headline metric; returns the written paths."""
    paths = []
    for metric, (title, ylabel) in LABELS.items():
        if metric == "catch_rate":
            if catch.empty:
                continue
            table, value = catch, "catch_rate"
        else:
            table, value = summary[summary["metric"] == metric], "mean"
        path = out_dir / f"{metric}.png"
        grouped_bars(table, value, title, ylabel, path, tag)
        paths.append(path)
    return paths
