"""Mis-specified twins: a model of the line whose parameters are wrong by a known amount.

Real plants never have a perfectly calibrated twin. ``misspecify`` perturbs the
continuous parameters (cycle time, MTBF, MTTR) of a config by independent
log-normal factors, leaving structure (station count, buffers, which stations can
fail) intact so every typed action stays valid. The agents observe the real line but
simulate and gate on this twin; fixes are scored on the real line.
"""

from __future__ import annotations

import math
import random

from src.twin import LineConfig


def misspecify(config: LineConfig, sigma: float, seed: int) -> LineConfig:
    """Copy of ``config`` with each cycle time, MTBF and MTTR scaled by exp(N(0, sigma)); ``sigma=0`` is an exact copy."""
    if sigma < 0:
        raise ValueError("sigma must be >= 0")
    if sigma == 0:
        return config.model_copy(deep=True)
    rng = random.Random(seed)

    def jitter() -> float:
        return math.exp(rng.gauss(0.0, sigma))

    new = config.model_copy(deep=True)
    for i, st in enumerate(config.stations):
        update: dict[str, float] = {"cycle_time_mean": st.cycle_time_mean * jitter()}
        if st.mtbf is not None:
            update["mtbf"] = st.mtbf * jitter()
            update["mttr"] = st.mttr * jitter()
        new.stations[i] = st.model_copy(update=update)
    return new
