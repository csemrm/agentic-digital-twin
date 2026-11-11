"""Human supervisor gate: a configurable simulated approver for batch mode.

The simulated approver only uses the evidence the supervisor would see. If the
twin verified the recommendation it approves iff the measured gain clears the
threshold; if there is no twin evidence it can only check that the action is
valid under the typed-action constraints. It can also inject occasional bad
recommendations so the gate catch rate (RQ3) can be measured. In the dashboard
a real person replaces this class.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from src.actions import validate_and_apply
from src.agents.simulation import evaluate_candidate
from src.agents.types import GateDecision, PipelineSettings, Recommendation
from src.twin import LineConfig


@dataclass
class SimulatedApprover:
    """Rule-based stand-in for the human supervisor."""

    min_gain_pct: float = 2.0
    bad_rate: float = 0.0
    seed: int = 0
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def maybe_inject(
        self, rec: Recommendation, config: LineConfig, diagnosis: dict[str, Any], settings: PipelineSettings
    ) -> tuple[Recommendation, bool]:
        """With probability ``bad_rate`` replace ``rec`` by a harmful or invalid fix; returns (rec, injected)."""
        if self.bad_rate <= 0 or self.rng.random() >= self.bad_rate:
            return rec, False
        action = self._bad_action(config, diagnosis)
        evidence = evaluate_candidate(config, action, settings) if rec.verified else None
        return Recommendation(action=action, rationale="(injected test recommendation)", verified=rec.verified, evidence=evidence), True

    def _bad_action(self, config: LineConfig, diagnosis: dict[str, Any]) -> dict[str, Any]:
        """Either an invalid action, or a valid one that pushes work onto the bottleneck."""
        s = diagnosis.get("bottleneck_station") or 3
        if self.rng.random() < 0.5:
            return {"type": "add_buffer", "station": config.n_stations, "size": 2}
        neighbour = s - 1 if s > 1 else s + 1
        return {"type": "rebalance_task", "from_station": neighbour, "to_station": s, "fraction": 0.3}

    def decide(self, rec: Recommendation, config: LineConfig) -> GateDecision:
        """Approve or reject using only the evidence presented with ``rec``."""
        check = validate_and_apply(rec.action, config)
        if not check.ok:
            return GateDecision(approved=False, reason=f"invalid action: {check.reason}")
        if rec.verified and rec.evidence is not None:
            gain = rec.evidence.gain_pct or 0.0
            if gain >= self.min_gain_pct:
                return GateDecision(approved=True, reason=f"twin shows {gain:+.1f}% throughput")
            return GateDecision(approved=False, reason=f"twin shows only {gain:+.1f}% throughput (< {self.min_gain_pct}%)")
        return GateDecision(approved=True, reason="valid action; no twin evidence available")
