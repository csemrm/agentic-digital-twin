"""Rule-based baseline: highest utilization is the bottleneck; fix = add a buffer after it."""

from __future__ import annotations

from src.actions import RejectionLog, validate_and_apply
from src.agents.gate import SimulatedApprover
from src.agents.mock_roles import DROP_THRESHOLD_PCT
from src.agents.observe import observe
from src.agents.types import PipelineSettings, Recommendation, RunRecord
from src.llm import UsageMeter
from src.scenarios import Scenario

BUFFER_SIZE = 3


def run_rule_based(scenario: Scenario, seed: int, approver: SimulatedApprover, settings: PipelineSettings | None = None) -> RunRecord:
    """Run the heuristic once: act only on a throughput drop, no LLM, no verification, one gate round."""
    settings = settings or PipelineSettings()
    config = scenario.config
    obs = observe(config, seed).payload
    trace = [{"step": "observe", "detail": f"throughput {obs['throughput_vs_reference_pct']:+.1f}% vs reference"}]
    base = dict(system="rule_based", scenario=scenario.name, seed=seed, usage=UsageMeter().as_dict())
    if obs["throughput_vs_reference_pct"] > DROP_THRESHOLD_PCT:
        diag = {"bottleneck_station": None, "fault_type": "none", "explanation": "Output normal.", "confidence": 1.0}
        return RunRecord(**base, outcome="no_fault", iterations=0, diagnoses=[diag], gate_log=[], applied_action=None,
                         final_config=config.model_dump(), trace=trace)
    top = max(obs["stations"], key=lambda s: s["utilization"])["id"]
    diag = {"bottleneck_station": top, "fault_type": "unspecified",
            "explanation": f"Station {top} has the highest utilization.", "confidence": 1.0}
    action = {"type": "add_buffer", "station": top if top < config.n_stations else top - 1, "size": BUFFER_SIZE}
    rec = Recommendation(action=action, rationale="Fixed heuristic: buffer after the busiest station.", verified=False)
    rec, decision, entry = approver.review(rec, config, diag, settings, 1)
    trace.append({"step": "gate", "detail": f"{'approved' if decision.approved else 'rejected'}: {decision.reason}"})
    log, applied, final = RejectionLog(), None, config
    outcome = "rejected"
    if decision.approved:
        res = validate_and_apply(rec.action, config, log)
        if res.ok and res.config is not None and res.action is not None:
            final, applied, outcome = res.config, res.action.model_dump(), "applied"
        else:
            outcome = "blocked_invalid"
    return RunRecord(**base, outcome=outcome, iterations=1, diagnoses=[diag], gate_log=[entry], applied_action=applied,
                     final_config=final.model_dump(), trace=trace, action_rejections=log.entries)
