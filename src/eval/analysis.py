"""Aggregation: means with 95% confidence intervals, paired differences, gate catch rates."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

BINARY_METRICS = ["station_correct", "type_correct", "invalid_fix", "ineffective_fix", "bad_applied", "false_alarm_action"]
CONTINUOUS_METRICS = ["gain_pct", "steps", "total_tokens", "expl_quality", "iterations", "validator_rejections"]
FAULT_SCENARIOS = ["slow_station", "breakdowns", "buffer", "mixed"]


def wilson_ci(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion."""
    if n == 0:
        return math.nan, math.nan
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mean_ci(values: pd.Series, binary: bool) -> tuple[int, float, float, float]:
    """Return (n, mean, ci_low, ci_high) ignoring NaNs; Wilson CI for 0/1 data, t-interval otherwise."""
    x = values.dropna().astype(float)
    n = len(x)
    if n == 0:
        return 0, math.nan, math.nan, math.nan
    m = float(x.mean())
    if binary:
        lo, hi = wilson_ci(float(x.sum()), n)
        return n, m, lo, hi
    if n < 2:
        return n, m, math.nan, math.nan
    half = float(stats.t.ppf(0.975, n - 1)) * float(x.std(ddof=1)) / math.sqrt(n)
    return n, m, m - half, m + half


def summarize(runs: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Long-form table (one row per group and metric) of n, mean and 95% CI."""
    rows = []
    for key, grp in runs.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        for metric in BINARY_METRICS + CONTINUOUS_METRICS:
            n, m, lo, hi = mean_ci(grp[metric], metric in BINARY_METRICS)
            rows.append({**dict(zip(by, key)), "metric": metric, "n": n, "mean": m, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows)


def gate_catch_table(reviews: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Catch rate = rejected / bad (invalid or harmful) recommendations reaching the gate."""
    bad = reviews[reviews["bad"]] if len(reviews) else reviews
    rows = []
    if bad.empty:
        return pd.DataFrame(columns=[*by, "bad_reviews", "catch_rate", "ci_low", "ci_high"])
    for key, grp in bad.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        n, m, lo, hi = mean_ci(grp["caught"].astype(float), True)
        rows.append({**dict(zip(by, key)), "bad_reviews": n, "catch_rate": m, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows)


def gate_catch_by_status(reviews: pd.DataFrame) -> pd.DataFrame:
    """Catch rate split by why the recommendation was bad (``invalid`` vs ``harmful``)."""
    columns = ["system", "status", "bad_reviews", "catch_rate", "ci_low", "ci_high"]
    bad = reviews[reviews["bad"]] if len(reviews) else reviews
    if bad.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for (system, status), grp in bad.groupby(["system", "status"]):
        n, m, lo, hi = mean_ci(grp["caught"].astype(float), True)
        rows.append({"system": system, "status": status, "bad_reviews": n, "catch_rate": m, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows, columns=columns)


def paired_diff_ci(
    runs: pd.DataFrame, metric: str, a: str, b: str, scenarios: list[str] | None = None, n_boot: int = 2000
) -> tuple[int, float, float, float]:
    """Mean of (a - b) per (scenario, seed) pair with a bootstrap 95% CI; returns (n, diff, lo, hi)."""
    scenarios = scenarios or FAULT_SCENARIOS
    sub = runs[runs["scenario"].isin(scenarios)]
    wide = sub.pivot_table(index=["scenario", "seed"], columns="system", values=metric, aggfunc="mean")
    if a not in wide or b not in wide:
        return 0, math.nan, math.nan, math.nan
    diff = (wide[a] - wide[b]).dropna().to_numpy()
    if len(diff) == 0:
        return 0, math.nan, math.nan, math.nan
    rng = np.random.default_rng(0)
    boots = rng.choice(diff, size=(n_boot, len(diff)), replace=True).mean(axis=1)
    return len(diff), float(diff.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
