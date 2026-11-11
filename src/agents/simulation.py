"""Simulation agent: test each candidate fix in the twin before anything is recommended."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats

from src.actions import RejectionLog, validate_and_apply
from src.agents.types import CandidateResult, PipelineSettings
from src.twin import LineConfig, replicate


def eval_seeds(settings: PipelineSettings) -> list[int]:
    """Seeds used for candidate replications (distinct from the observation seed)."""
    return [settings.eval_seed_base + i for i in range(settings.n_reps)]


def baseline_throughputs(config: LineConfig, settings: PipelineSettings) -> list[float]:
    """Units/shift of the unmodified line on the evaluation seeds."""
    return [r.throughput_per_shift for r in replicate(config, eval_seeds(settings))]


def evaluate_candidate(
    config: LineConfig,
    raw: dict[str, Any],
    settings: PipelineSettings,
    base: list[float] | None = None,
    log: RejectionLog | None = None,
) -> CandidateResult:
    """Validate ``raw``, run it over seeded replications and compare with the unmodified line.

    Replications are paired by seed (common random numbers). ``passed`` requires
    a mean gain of at least ``min_gain_pct`` and a one-sided paired t-test below ``alpha``.
    """
    res = validate_and_apply(raw, config, log)
    if not res.ok or res.config is None:
        return CandidateResult(action=raw if isinstance(raw, dict) else {"raw": repr(raw)}, valid=False, reason=res.reason)
    base = base if base is not None else baseline_throughputs(config, settings)
    new = [r.throughput_per_shift for r in replicate(res.config, eval_seeds(settings))]
    diff = np.array(new) - np.array(base)
    base_mean = float(np.mean(base))
    gain_pct = 100 * float(diff.mean()) / base_mean
    se = float(diff.std(ddof=1) / np.sqrt(len(diff))) if len(diff) > 1 else 0.0
    half = float(stats.t.ppf(0.975, max(len(diff) - 1, 1))) * se
    if se > 0:
        p = float(stats.ttest_rel(new, base, alternative="greater").pvalue)
    else:
        p = 0.0 if diff.mean() > 0 else 1.0
    return CandidateResult(
        action=res.action.model_dump() if res.action else raw,
        valid=True,
        baseline_mean=base_mean,
        new_mean=float(np.mean(new)),
        gain_pct=gain_pct,
        ci_low_pct=100 * (float(diff.mean()) - half) / base_mean,
        ci_high_pct=100 * (float(diff.mean()) + half) / base_mean,
        p_value=p,
        passed=gain_pct >= settings.min_gain_pct and p < settings.alpha,
    )


def run_simulation_agent(
    config: LineConfig, raw_candidates: list[dict[str, Any]], settings: PipelineSettings, log: RejectionLog | None = None
) -> list[CandidateResult]:
    """Evaluate every distinct candidate; passed fixes first, ranked by gain, then the rest by gain."""
    base = baseline_throughputs(config, settings)
    unique = [c for i, c in enumerate(raw_candidates) if c not in raw_candidates[:i]]
    results = [evaluate_candidate(config, c, settings, base, log) for c in unique]
    return sorted(results, key=lambda r: (not r.passed, -(r.gain_pct if r.gain_pct is not None else -1e9)))
