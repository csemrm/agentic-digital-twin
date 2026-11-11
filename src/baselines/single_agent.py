"""Single-agent LLM baseline: one agent, one prompt, same typed actions, NO simulate step.

It diagnoses and proposes a fix in a single call. It gets the same feedback
channels as the multi-agent loop (validator rejections, gate rejections) and the
same round cap, so differences isolate role separation and the Simulation step.
"""

from __future__ import annotations

from typing import Any

from src.actions import ACTION_SCHEMA_HINT, RejectionLog, validate_and_apply
from src.agents.gate import SimulatedApprover
from src.agents.observe import observe
from src.agents.types import Diagnosis, PipelineSettings, Recommendation, RunRecord
from src.llm import LLMClient, UsageMeter
from src.scenarios import Scenario

SYSTEM = (
    "You are the only agent supervising a 5-station serial production line. From the KPI observation, in ONE reply: "
    "identify the bottleneck station and fault type (slow_station, breakdowns, buffer, mixed, or none if output is normal) "
    "with an explanation and confidence, and propose ONE fix as a typed action. Use ONLY these actions: "
    f"{ACTION_SCHEMA_HINT}. Constraints: buffers add 1-5 slots (max capacity 12, not after the last station); rebalance only "
    "between adjacent stations, fraction in (0,0.3]; maintenance mtbf_multiplier in [1,2], mttr_multiplier in [0.5,1]. "
    "The bottleneck is the station least often blocked or starved. Use feedback to avoid rejected actions. Set action to null if fault is none."
)


class SingleAgentOutput(Diagnosis):
    """Diagnosis plus a single proposed action."""

    action: dict[str, Any] | None = None
    rationale: str = ""


def run_single_agent(
    scenario: Scenario,
    seed: int,
    client: LLMClient,
    approver: SimulatedApprover,
    settings: PipelineSettings | None = None,
) -> RunRecord:
    """Run the single agent for up to ``max_iterations`` rounds."""
    settings = settings or PipelineSettings()
    meter, log = UsageMeter(), RejectionLog()
    config = scenario.config
    obs = observe(config, seed).payload
    feedback: list[dict[str, Any]] = []
    diagnoses: list[dict[str, Any]] = []
    gate_log: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    applied, final, outcome, rounds = None, config, "no_recommendation", 0
    for rounds in range(1, settings.max_iterations + 1):
        out = client.complete_json(
            "single_agent", SYSTEM, "Diagnose and propose one fix.",
            {"observation": obs, "feedback": feedback, "seed": seed, "iteration": rounds},
            SingleAgentOutput, meter, max_tokens=900,
        )
        diag = out.model_dump(exclude={"action", "rationale"})
        diagnoses.append(diag)
        trace.append({"step": "single_agent", "detail": f"round {rounds}: station {out.bottleneck_station} / {out.fault_type}; action {out.action}"})
        if out.fault_type == "none" or out.action is None:
            outcome = "no_fault" if out.fault_type == "none" else "no_recommendation"
            break
        check = validate_and_apply(out.action, config, log)
        if not check.ok:
            feedback.append({"kind": "invalid_action", "action": out.action, "reason": check.reason})
            outcome = "no_recommendation"
            continue
        rec = Recommendation(action=out.action, rationale=out.rationale, verified=False)
        rec, decision, entry = approver.review(rec, config, diag, settings, rounds)
        gate_log.append(entry)
        trace.append({"step": "gate", "detail": f"{'approved' if decision.approved else 'rejected'}: {decision.reason}"})
        if decision.approved:
            res = validate_and_apply(rec.action, config, log)
            if res.ok and res.config is not None and res.action is not None:
                final, applied, outcome = res.config, res.action.model_dump(), "applied"
            else:
                outcome = "blocked_invalid"
            break
        feedback.append({"kind": "gate_rejected", "action": rec.action, "reason": decision.reason})
        outcome = "rejected_max_iterations"
    return RunRecord(
        system="single_agent", scenario=scenario.name, seed=seed, outcome=outcome, iterations=rounds, diagnoses=diagnoses,
        gate_log=gate_log, applied_action=applied, final_config=final.model_dump(), usage=meter.as_dict(), trace=trace,
        action_rejections=log.entries,
    )
