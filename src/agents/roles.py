"""LLM-backed roles: Monitor, Diagnosis, and candidate-fix generation."""

from __future__ import annotations

from typing import Any

from src.actions import ACTION_SCHEMA_HINT
from src.agents.types import CandidateProposal, Diagnosis, MonitorSummary
from src.llm import LLMClient, UsageMeter

MONITOR_SYSTEM = (
    "You are the Monitor agent for a 5-station serial production line. Read the KPI observation and flag anomalies "
    "(throughput drop vs reference, high down/blocked/starved fractions, cycle time above standard). Be concise and factual."
)
DIAGNOSIS_SYSTEM = (
    "You are the Diagnosis agent for a 5-station serial production line. Identify the bottleneck station and fault type "
    "(slow_station, breakdowns, buffer, mixed, or none if output is normal). The bottleneck is the station least often "
    "blocked or starved. If feedback lists rejected fixes or stations with no verified fix, revise your diagnosis."
)
CANDIDATES_SYSTEM = (
    "You propose candidate fixes for a diagnosed production-line fault. Use ONLY these typed actions: "
    f"{ACTION_SCHEMA_HINT}. Stay within constraints: buffers add 1-5 slots (max capacity 12, not after the last station); "
    "rebalance only between adjacent stations, fraction in (0,0.3]; maintenance mtbf_multiplier in [1,2], mttr_multiplier in [0.5,1]. "
    "List the most promising fix first and avoid actions already tried."
)


def run_monitor(client: LLMClient, observation: dict[str, Any], meter: UsageMeter) -> MonitorSummary:
    """Monitor agent: flag anomalies in the observed shift."""
    return client.complete_json(
        "monitor", MONITOR_SYSTEM, "Flag anomalies in this shift.", {"observation": observation}, MonitorSummary, meter
    )


def run_diagnosis(
    client: LLMClient, observation: dict[str, Any], monitor: dict[str, Any], feedback: list[dict[str, Any]], meter: UsageMeter
) -> Diagnosis:
    """Diagnosis agent: name the bottleneck and fault type, using feedback from earlier rounds."""
    payload = {"observation": observation, "monitor": monitor, "feedback": feedback}
    return client.complete_json("diagnosis", DIAGNOSIS_SYSTEM, "Diagnose the bottleneck.", payload, Diagnosis, meter)


def run_candidates(
    client: LLMClient,
    diagnosis: dict[str, Any],
    observation: dict[str, Any],
    tried: list[dict[str, Any]],
    seed: int,
    iteration: int,
    max_candidates: int,
    meter: UsageMeter,
) -> CandidateProposal:
    """Propose typed candidate fixes for the diagnosis (unverified)."""
    payload = {
        "diagnosis": diagnosis,
        "stations": [
            {"id": s["id"], "utilization": s["utilization"], "buffer_after_capacity": s["buffer_after_capacity"]}
            for s in observation["stations"]
        ],
        "tried_actions": tried,
        "max_candidates": max_candidates,
        "seed": seed,
        "iteration": iteration,
    }
    return client.complete_json(
        "candidates", CANDIDATES_SYSTEM, f"Propose up to {max_candidates} candidate fixes.", payload, CandidateProposal, meter, max_tokens=900
    )
