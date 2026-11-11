"""LangGraph verify-before-act loop: Monitor -> Diagnosis -> Simulation -> Supervisor gate.

A gate rejection (or a round with no verified fix) routes back to Diagnosis,
capped at ``PipelineSettings.max_iterations`` diagnosis rounds. Only an
approved fix is applied to the twin. Pass ``approver=None`` for human-in-the-loop
mode: the graph pauses before the gate until ``submit_human_decision`` is called.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.actions import RejectionLog, validate_and_apply
from src.agents.gate import SimulatedApprover
from src.agents.observe import observe
from src.agents.roles import run_candidates, run_diagnosis, run_monitor
from src.agents.simulation import run_simulation_agent
from src.agents.types import GateDecision, PipelineSettings, Recommendation, RunRecord
from src.llm import LLMClient, UsageMeter
from src.scenarios import Scenario
from src.twin import LineConfig


class PipelineState(TypedDict, total=False):
    """Shared typed state of the loop (plain dicts so it checkpoints cleanly)."""

    config: dict[str, Any]
    observation: dict[str, Any]
    monitor: dict[str, Any]
    diagnosis: dict[str, Any]
    feedback: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    recommendation: dict[str, Any] | None
    gate_decision: dict[str, Any]
    human_decision: dict[str, Any] | None
    iteration: int
    applied_action: dict[str, Any] | None
    outcome: str
    trace: Annotated[list[dict[str, Any]], operator.add]
    gate_log: Annotated[list[dict[str, Any]], operator.add]
    diagnoses: Annotated[list[dict[str, Any]], operator.add]
    action_rejections: Annotated[list[dict[str, Any]], operator.add]


class Pipeline:
    """One run of the multi-agent loop on a scenario."""

    def __init__(
        self,
        scenario: Scenario,
        seed: int,
        client: LLMClient,
        approver: SimulatedApprover | None = None,
        settings: PipelineSettings | None = None,
        use_simulation: bool = True,
        system: str | None = None,
    ) -> None:
        self.scenario, self.seed, self.client, self.approver = scenario, seed, client, approver
        self.settings = settings or PipelineSettings()
        self.use_simulation = use_simulation
        self.system = system or ("multi_agent" if use_simulation else "multi_agent_no_sim")
        self.meter = UsageMeter()
        self.human_in_loop = approver is None
        self._cfg = {"configurable": {"thread_id": f"{self.system}-{scenario.name}-{seed}"}, "recursion_limit": 80}
        self.graph = self._build()

    # ----- nodes -----
    def _config(self, state: PipelineState) -> LineConfig:
        return LineConfig.model_validate(state["config"])

    def _monitor(self, state: PipelineState) -> dict[str, Any]:
        obs = observe(self._config(state), self.seed).payload
        summary = run_monitor(self.client, obs, self.meter).model_dump()
        return {"observation": obs, "monitor": summary, "trace": [{"step": "monitor", "detail": summary["summary"]}]}

    def _diagnosis(self, state: PipelineState) -> dict[str, Any]:
        it = state.get("iteration", 0) + 1
        d = run_diagnosis(self.client, state["observation"], state["monitor"], state.get("feedback", []), self.meter).model_dump()
        detail = f"round {it}: station {d['bottleneck_station']} / {d['fault_type']} (conf {d['confidence']}): {d['explanation']}"
        return {"diagnosis": d, "iteration": it, "diagnoses": [d], "trace": [{"step": "diagnosis", "detail": detail}]}

    def _candidates(self, state: PipelineState) -> dict[str, Any]:
        config, feedback = self._config(state), list(state.get("feedback", []))
        tried = [f["action"] for f in feedback if f.get("kind") == "gate_rejected"]
        proposal = run_candidates(
            self.client, state["diagnosis"], state["observation"], tried, self.seed, state["iteration"], self.settings.max_candidates, self.meter
        )
        log = RejectionLog()
        rec: Recommendation | None = None
        if self.use_simulation:
            results = run_simulation_agent(config, proposal.candidates, self.settings, log)
            summaries = [r.model_dump() for r in results]
            best = next((r for r in results if r.passed), None)
            if best:
                rec = Recommendation(action=best.action, rationale=proposal.rationale, verified=True, evidence=best)
            detail = f"simulated {len(results)} candidates; {sum(r.passed for r in results)} passed"
        else:
            summaries = [{"action": c} for c in proposal.candidates]
            first = next((c for c in proposal.candidates if validate_and_apply(c, config, log).ok), None)
            if first:
                rec = Recommendation(action=first, rationale=proposal.rationale, verified=False)
            detail = f"proposed {len(proposal.candidates)} candidates; first valid taken unverified"
        if rec is None:
            feedback.append({"kind": "no_viable_fix", "station": state["diagnosis"]["bottleneck_station"], "detail": detail})
        return {
            "candidates": summaries,
            "recommendation": rec.model_dump() if rec else None,
            "feedback": feedback,
            "action_rejections": log.entries,
            "trace": [{"step": "simulation" if self.use_simulation else "propose", "detail": detail}],
        }

    def _gate(self, state: PipelineState) -> dict[str, Any]:
        config, rec = self._config(state), Recommendation.model_validate(state["recommendation"])
        injected = False
        if self.approver is not None:
            rec, injected = self.approver.maybe_inject(rec, config, state["diagnosis"], self.settings)
            decision = self.approver.decide(rec, config)
        else:
            if not state.get("human_decision"):
                raise RuntimeError("human gate reached without a decision")
            decision = GateDecision.model_validate(state["human_decision"])
        entry = {
            "iteration": state["iteration"],
            "action": rec.action,
            "verified": rec.verified,
            "gain_pct": rec.evidence.gain_pct if rec.evidence else None,
            "approved": decision.approved,
            "reason": decision.reason,
            "injected": injected,
        }
        feedback = list(state.get("feedback", []))
        if not decision.approved:
            feedback.append({"kind": "gate_rejected", "station": state["diagnosis"]["bottleneck_station"], "action": rec.action, "reason": decision.reason})
        verdict = "approved" if decision.approved else "rejected"
        return {
            "recommendation": rec.model_dump(),
            "gate_decision": decision.model_dump(),
            "human_decision": None,
            "feedback": feedback,
            "gate_log": [entry],
            "trace": [{"step": "gate", "detail": f"{verdict}: {decision.reason}"}],
        }

    def _apply(self, state: PipelineState) -> dict[str, Any]:
        log = RejectionLog()
        res = validate_and_apply(state["recommendation"]["action"], self._config(state), log)
        if not res.ok or res.config is None:
            return {"outcome": "blocked_invalid", "action_rejections": log.entries, "trace": [{"step": "apply", "detail": f"blocked: {res.reason}"}]}
        return {
            "config": res.config.model_dump(),
            "applied_action": res.action.model_dump() if res.action else None,
            "trace": [{"step": "apply", "detail": f"applied {res.action.model_dump() if res.action else None}"}],
        }

    def _finalize(self, state: PipelineState) -> dict[str, Any]:
        if state.get("outcome"):
            outcome = state["outcome"]
        elif state.get("applied_action"):
            outcome = "applied"
        elif state["diagnosis"]["fault_type"] == "none":
            outcome = "no_fault"
        elif not state.get("recommendation") or not state.get("gate_decision"):
            outcome = "no_recommendation"
        else:
            outcome = "rejected_max_iterations"
        return {"outcome": outcome, "trace": [{"step": "finalize", "detail": outcome}]}

    # ----- routing -----
    def _after_diagnosis(self, state: PipelineState) -> str:
        return "finalize" if state["diagnosis"]["fault_type"] == "none" else "candidates"

    def _retry_or_stop(self, state: PipelineState) -> str:
        return "diagnosis" if state["iteration"] < self.settings.max_iterations else "finalize"

    def _after_candidates(self, state: PipelineState) -> str:
        return "gate" if state.get("recommendation") else self._retry_or_stop(state)

    def _after_gate(self, state: PipelineState) -> str:
        return "apply" if state["gate_decision"]["approved"] else self._retry_or_stop(state)

    def _build(self) -> Any:
        g = StateGraph(PipelineState)
        for name, fn in [("monitor", self._monitor), ("diagnosis", self._diagnosis), ("candidates", self._candidates),
                         ("gate", self._gate), ("apply", self._apply), ("finalize", self._finalize)]:
            g.add_node(name, fn)
        g.add_edge(START, "monitor")
        g.add_edge("monitor", "diagnosis")
        g.add_conditional_edges("diagnosis", self._after_diagnosis, {"candidates": "candidates", "finalize": "finalize"})
        g.add_conditional_edges("candidates", self._after_candidates, {"gate": "gate", "diagnosis": "diagnosis", "finalize": "finalize"})
        g.add_conditional_edges("gate", self._after_gate, {"apply": "apply", "diagnosis": "diagnosis", "finalize": "finalize"})
        g.add_edge("apply", "finalize")
        g.add_edge("finalize", END)
        if self.human_in_loop:
            return g.compile(checkpointer=MemorySaver(), interrupt_before=["gate"])
        return g.compile()

    # ----- running -----
    def _initial(self) -> PipelineState:
        return {"config": self.scenario.config.model_dump(), "iteration": 0, "feedback": []}

    def start(self) -> dict[str, Any]:
        """Run until the end (simulated approver) or until the human gate is reached."""
        return self.graph.invoke(self._initial(), self._cfg)

    @property
    def paused_at_gate(self) -> bool:
        """True while waiting for a human decision."""
        return self.human_in_loop and tuple(self.graph.get_state(self._cfg).next) == ("gate",)

    def submit_human_decision(self, approved: bool, reason: str = "") -> dict[str, Any]:
        """Provide the human verdict and resume the graph."""
        self.graph.update_state(self._cfg, {"human_decision": {"approved": approved, "reason": reason or ("approved by supervisor" if approved else "rejected by supervisor")}})
        return self.graph.invoke(None, self._cfg)

    def current_state(self) -> dict[str, Any]:
        """Latest checkpointed state (human mode) for live display."""
        return dict(self.graph.get_state(self._cfg).values)

    def to_record(self, state: dict[str, Any]) -> RunRecord:
        """Package a (final) state as a :class:`RunRecord`."""
        return RunRecord(
            system=self.system,
            scenario=self.scenario.name,
            seed=self.seed,
            outcome=state.get("outcome", "pending"),
            iterations=state.get("iteration", 0),
            diagnoses=state.get("diagnoses", []),
            gate_log=state.get("gate_log", []),
            applied_action=state.get("applied_action"),
            final_config=state["config"],
            usage=self.meter.as_dict(),
            trace=state.get("trace", []),
            action_rejections=state.get("action_rejections", []),
        )

    def run(self) -> RunRecord:
        """Run to completion with the simulated approver and return the record."""
        if self.human_in_loop:
            raise RuntimeError("run() needs a simulated approver; use start()/submit_human_decision() for a human")
        return self.to_record(self.start())
