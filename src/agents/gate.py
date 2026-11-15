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
from functools import lru_cache
from typing import Any

from src.actions import validate_and_apply
from src.agents.simulation import baseline_throughputs, evaluate_candidate
from src.agents.types import GateDecision, PipelineSettings, Recommendation
from src.twin import LineConfig


def gate_entry(iteration: int, rec: Recommendation, decision: GateDecision, injected: bool) -> dict[str, Any]:
    """Log record of one gate review (shared by the graph and the baselines)."""
    return {
        "iteration": iteration,
        "action": rec.action,
        "verified": rec.verified,
        "gain_pct": rec.evidence.gain_pct if rec.evidence else None,
        "approved": decision.approved,
        "independent_gain_pct": decision.independent_gain_pct,
        "reason": decision.reason,
        "injected": injected,
    }


@dataclass
class SimulatedApprover:
    """Rule-based stand-in for the human supervisor."""

    min_gain_pct: float = 2.0
    bad_rate: float = 0.0
    seed: int = 0
    forge_evidence: bool = False  # injected bad fixes carry the good fix's evidence (stale or fabricated numbers)
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
        if rec.verified and self.forge_evidence and rec.evidence is not None:
            evidence = rec.evidence
        else:
            evidence = evaluate_candidate(config, action, settings) if rec.verified else None
        return Recommendation(action=action, rationale="(injected test recommendation)", verified=rec.verified, evidence=evidence), True

    def _bad_action(self, config: LineConfig, diagnosis: dict[str, Any]) -> dict[str, Any]:
        """Either an invalid action, or a valid one that pushes work onto the bottleneck."""
        s = diagnosis.get("bottleneck_station") or 3
        if self.rng.random() < 0.5:
            return {"type": "add_buffer", "station": config.n_stations, "size": 2}
        neighbour = s - 1 if s > 1 else s + 1
        return {"type": "rebalance_task", "from_station": neighbour, "to_station": s, "fraction": 0.3}

    def review(
        self, rec: Recommendation, config: LineConfig, diagnosis: dict[str, Any], settings: PipelineSettings, iteration: int
    ) -> tuple[Recommendation, GateDecision, dict[str, Any]]:
        """Possibly inject a bad recommendation, decide, and return (presented rec, decision, log entry)."""
        rec, injected = self.maybe_inject(rec, config, diagnosis, settings)
        decision = self.decide(rec, config)
        return rec, decision, gate_entry(iteration, rec, decision, injected)

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


INDEPENDENT_SEED_BASE = 3000  # disjoint from observation (1..N), reference (100..104), Simulation agent (1000+) and scoring (2000+) seeds


@lru_cache(maxsize=256)
def _baseline(config_json: str, settings: PipelineSettings) -> tuple[float, ...]:
    return tuple(baseline_throughputs(LineConfig.model_validate_json(config_json), settings))


@dataclass
class IndependentApprover(SimulatedApprover):
    """Gate that does not trust presented evidence: it re-simulates the action on its own fresh seeds.

    Approves iff the action is valid and passes the same test the Simulation agent uses
    (mean gain >= ``min_gain_pct``, one-sided paired t-test below ``alpha``) on replications
    the proposing system never saw. That removes selection bias from picking the best of many
    candidates and makes stale or fabricated evidence irrelevant. It does *not* remove model
    mismatch: the re-simulation uses the same twin as the proposer. With
    ``verify_unverified`` it also checks fixes that arrive with no evidence at all.
    """

    n_reps: int = 8
    alpha: float = 0.05
    eval_seed_base: int = INDEPENDENT_SEED_BASE
    verify_unverified: bool = True

    def decide(self, rec: Recommendation, config: LineConfig) -> GateDecision:
        """Validate, then re-simulate on independent seeds and decide on that result alone."""
        check = validate_and_apply(rec.action, config)
        if not check.ok:
            return GateDecision(approved=False, reason=f"invalid action: {check.reason}")
        if not rec.verified and not self.verify_unverified:
            return super().decide(rec, config)
        s = PipelineSettings(n_reps=self.n_reps, min_gain_pct=self.min_gain_pct, alpha=self.alpha, eval_seed_base=self.eval_seed_base)
        res = evaluate_candidate(config, rec.action, s, list(_baseline(config.model_dump_json(), s)))
        gain = res.gain_pct or 0.0
        if res.passed:
            return GateDecision(approved=True, reason=f"independent re-simulation shows {gain:+.1f}% (p={res.p_value:.3f})", independent_gain_pct=gain)
        return GateDecision(approved=False, reason=f"independent re-simulation shows {gain:+.1f}% (p={res.p_value:.3f}); needs >= {self.min_gain_pct}% and p < {self.alpha}",
                            independent_gain_pct=gain)
