"""Typed messages passed between agents, plus run settings and the run record."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

FaultType = Literal["none", "slow_station", "breakdowns", "buffer", "mixed"]


class Anomaly(BaseModel):
    """One flagged pattern in the line KPIs."""

    kind: str
    station: int | None = None
    detail: str


class MonitorSummary(BaseModel):
    """Monitor agent output."""

    anomalies: list[Anomaly]
    throughput_drop_pct: float
    summary: str


class Diagnosis(BaseModel):
    """Diagnosis agent output."""

    bottleneck_station: int | None = Field(default=None, ge=1, le=5)
    fault_type: FaultType
    explanation: str
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _station_matches_fault(self) -> "Diagnosis":
        if (self.fault_type == "none") != (self.bottleneck_station is None):
            raise ValueError("bottleneck_station must be null exactly when fault_type is 'none'")
        return self


class CandidateProposal(BaseModel):
    """Raw candidate fixes proposed by the LLM (validated later against the typed schema)."""

    candidates: list[dict[str, Any]]
    rationale: str


class CandidateResult(BaseModel):
    """A candidate fix with its twin-measured effect."""

    action: dict[str, Any]
    valid: bool
    reason: str = ""
    baseline_mean: float | None = None
    new_mean: float | None = None
    gain_pct: float | None = None
    ci_low_pct: float | None = None
    ci_high_pct: float | None = None
    p_value: float | None = None
    passed: bool = False


class Recommendation(BaseModel):
    """A fix presented to the supervisor gate."""

    action: dict[str, Any]
    rationale: str
    verified: bool
    evidence: CandidateResult | None = None


class GateDecision(BaseModel):
    """Supervisor gate verdict."""

    approved: bool
    reason: str


@dataclass(frozen=True)
class PipelineSettings:
    """Tunable parameters of the verify-before-act loop."""

    n_reps: int = 8
    min_gain_pct: float = 2.0
    alpha: float = 0.05
    max_iterations: int = 3
    max_candidates: int = 5
    eval_seed_base: int = 1000


@dataclass
class RunRecord:
    """Everything an evaluation needs to know about one pipeline run."""

    system: str
    scenario: str
    seed: int
    outcome: str
    iterations: int
    diagnoses: list[dict[str, Any]]
    gate_log: list[dict[str, Any]]
    applied_action: dict[str, Any] | None
    final_config: dict[str, Any]
    usage: dict[str, Any]
    trace: list[dict[str, Any]] = field(repr=False)
    action_rejections: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @property
    def final_diagnosis(self) -> dict[str, Any] | None:
        """Last diagnosis produced, if any."""
        return self.diagnoses[-1] if self.diagnoses else None
