"""Independent ground-truth evaluation of fixes (seeds disjoint from the agents' own)."""

from __future__ import annotations

from typing import Any

import numpy as np

from src.actions import validate_and_apply
from src.twin import LineConfig, replicate

EVAL_SEED_BASE = 2000
HARM_PCT = -1.0
INEFFECTIVE_PCT = 2.0  # an applied fix gaining less than this is ineffective (matches the gate threshold)


class TruthEvaluator:
    """Measures the real effect of configs/actions with replications the agents never saw."""

    def __init__(self, n_reps: int = 20) -> None:
        self.seeds = [EVAL_SEED_BASE + i for i in range(n_reps)]
        self._tp: dict[str, np.ndarray] = {}

    def throughputs(self, config: LineConfig) -> np.ndarray:
        """Units/shift per evaluation seed (memoised by config)."""
        key = config.model_dump_json()
        if key not in self._tp:
            self._tp[key] = np.array([r.throughput_per_shift for r in replicate(config, self.seeds)])
        return self._tp[key]

    def gain_pct(self, before: LineConfig, after: LineConfig) -> float:
        """Mean throughput change of ``after`` vs ``before`` in percent."""
        return 100.0 * (float(self.throughputs(after).mean()) / float(self.throughputs(before).mean()) - 1.0)

    def action_status(self, config: LineConfig, action: dict[str, Any]) -> str:
        """``invalid`` (breaks schema/constraints), ``harmful`` (gain < HARM_PCT) or ``ok``."""
        res = validate_and_apply(action, config)
        if not res.ok or res.config is None:
            return "invalid"
        return "harmful" if self.gain_pct(config, res.config) < HARM_PCT else "ok"
