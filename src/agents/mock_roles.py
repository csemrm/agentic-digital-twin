"""Scripted, rule-based stand-ins for the LLM roles, used in mock (offline) mode.

Diagnosis follows the classic *active period* idea: the bottleneck is the
station that is least often blocked or starved (busy + down fraction highest).
These handlers exist so the whole pipeline runs without an API key; results
produced with them measure the pipeline, not the quality of a real LLM.
"""

from __future__ import annotations

import re
from typing import Any

from src.llm.backends import MockHandler

DROP_THRESHOLD_PCT = -5.0
SLOW_RATIO = 1.15
DOWN_THRESHOLD = 0.08
BLOCKED_THRESHOLD = 0.05
SMALL_BUFFER = 2


def _slow_ratio(st: dict[str, Any]) -> float:
    measured = st["measured_cycle_time_s"]
    return measured / st["standard_cycle_time_s"] if measured else 1.0


def _active(st: dict[str, Any]) -> float:
    return st["utilization"] + st["down"]


def monitor_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Flag throughput drop and per-station utilization / blocked / starved / down patterns."""
    obs = payload["observation"]
    anomalies: list[dict[str, Any]] = []
    drop = max(0.0, -obs["throughput_vs_reference_pct"])
    if obs["throughput_vs_reference_pct"] <= DROP_THRESHOLD_PCT:
        anomalies.append({"kind": "throughput_drop", "station": None, "detail": f"{drop:.1f}% below reference output"})
    for st in obs["stations"]:
        sid = st["id"]
        if _slow_ratio(st) >= SLOW_RATIO:
            anomalies.append({"kind": "slow_cycle", "station": sid, "detail": f"measured cycle {_slow_ratio(st):.2f}x standard"})
        if st["down"] >= DOWN_THRESHOLD:
            anomalies.append({"kind": "high_downtime", "station": sid, "detail": f"down {st['down']:.0%}, {st['breakdowns']} breakdowns"})
        if st["blocked"] >= 0.15:
            anomalies.append({"kind": "blocked", "station": sid, "detail": f"blocked {st['blocked']:.0%} of the shift"})
        if st["starved"] >= 0.15:
            anomalies.append({"kind": "starved", "station": sid, "detail": f"starved {st['starved']:.0%} of the shift"})
    text = "No anomalies; output is normal." if not anomalies else f"{len(anomalies)} anomalies; output {drop:.1f}% below reference."
    return {"anomalies": anomalies, "throughput_drop_pct": round(drop, 1), "summary": text}


def _classify(st: dict[str, Any], others: list[dict[str, Any]]) -> str:
    slow, down = _slow_ratio(st) >= SLOW_RATIO, st["down"] >= DOWN_THRESHOLD
    small_buffer = (st["buffer_after_capacity"] or 99) <= SMALL_BUFFER and st["blocked"] >= BLOCKED_THRESHOLD
    if small_buffer and not slow:
        kind = "buffer"
    elif slow and down:
        return "mixed"
    elif down:
        kind = "breakdowns"
    elif slow:
        kind = "slow_station"
    else:
        kind = "buffer" if small_buffer else "slow_station"
    if kind in ("slow_station", "breakdowns") and any(_slow_ratio(o) >= SLOW_RATIO or o["down"] >= DOWN_THRESHOLD for o in others):
        return "mixed"
    return kind


def diagnosis_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Pick the least-blocked/starved station; skip stations a previous round found unfixable."""
    obs = payload["observation"]
    excluded = {f["station"] for f in payload.get("feedback", []) if f.get("kind") == "no_viable_fix"}
    if obs["throughput_vs_reference_pct"] > DROP_THRESHOLD_PCT:
        return {"bottleneck_station": None, "fault_type": "none", "explanation": "Output is within normal range; no fault.", "confidence": 0.8}
    ranked = sorted((s for s in obs["stations"] if s["id"] not in excluded), key=_active, reverse=True)
    if not ranked:
        return {"bottleneck_station": None, "fault_type": "none", "explanation": "No remaining candidate stations.", "confidence": 0.2}
    top = ranked[0]
    margin = _active(top) - (_active(ranked[1]) if len(ranked) > 1 else 0.0)
    kind = _classify(top, [s for s in obs["stations"] if s["id"] != top["id"]])
    expl = (
        f"Station {top['id']} is active {_active(top):.0%} of the time (blocked {top['blocked']:.0%}, starved {top['starved']:.0%}, "
        f"down {top['down']:.0%}; cycle {_slow_ratio(top):.2f}x standard), so it limits flow: {kind.replace('_', ' ')}."
    )
    return {"bottleneck_station": top["id"], "fault_type": kind, "explanation": expl, "confidence": round(min(0.95, 0.5 + 3 * margin), 2)}


def _neighbours(station: int, stations: list[dict[str, Any]]) -> list[int]:
    """Adjacent stations ordered by lowest utilization first (best place to move work to)."""
    ids = [n for n in (station - 1, station + 1) if 1 <= n <= len(stations)]
    return sorted(ids, key=lambda n: stations[n - 1]["utilization"])


def candidates_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Propose the natural fix for the diagnosed fault first, then alternatives.

    On every fourth seed the first proposal is deliberately over-aggressive so
    the typed-action validator is exercised.
    """
    diag, stations = payload["diagnosis"], payload["stations"]
    s, kind = diag["bottleneck_station"], diag["fault_type"]
    if s is None:
        return {"candidates": [], "rationale": "No fault to fix."}
    last = len(stations)
    buf_station = s if s < last else s - 1

    def rebalance(frac: float) -> list[dict[str, Any]]:
        return [{"type": "rebalance_task", "from_station": s, "to_station": n, "fraction": frac} for n in _neighbours(s, stations)]

    maint = {"type": "change_maintenance", "station": s, "mtbf_multiplier": 1.5, "mttr_multiplier": 0.7}
    maint_strong = {"type": "change_maintenance", "station": s, "mtbf_multiplier": 2.0, "mttr_multiplier": 0.5}
    buf3 = {"type": "add_buffer", "station": buf_station, "size": 3}
    buf5 = {"type": "add_buffer", "station": buf_station, "size": 5}
    plans = {
        "slow_station": rebalance(0.2) + [buf3],
        "breakdowns": [maint, maint_strong, buf3],
        "buffer": [buf3, buf5, maint],
        "mixed": [maint, maint_strong] + rebalance(0.2) + [buf3],
    }
    cands = plans[kind]
    if payload.get("seed", 1) % 4 == 0 and payload.get("iteration", 1) == 1:
        aggressive = {"type": "add_buffer", "station": buf_station, "size": 9} if kind in ("buffer", "slow_station") else {**maint, "mtbf_multiplier": 3.0}
        cands = [aggressive] + cands
    tried = payload.get("tried_actions", [])
    cands = [c for c in cands if c not in tried]
    return {"candidates": cands[: payload.get("max_candidates", 5)], "rationale": f"Standard remedies for {kind.replace('_', ' ')} at station {s}."}


def single_agent_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """One-shot diagnosis plus first proposed fix, reusing the same heuristics as the separate roles."""
    obs, feedback = payload["observation"], payload.get("feedback", [])
    diag = diagnosis_handler({"observation": obs, "feedback": []})
    stations = [{"id": s["id"], "utilization": s["utilization"], "buffer_after_capacity": s["buffer_after_capacity"]} for s in obs["stations"]]
    cands = candidates_handler(
        {"diagnosis": diag, "stations": stations, "tried_actions": [f["action"] for f in feedback if "action" in f],
         "seed": payload.get("seed", 1), "iteration": payload.get("iteration", 1), "max_candidates": 1}
    )["candidates"]
    return {**diag, "action": cands[0] if cands else None, "rationale": "Single-call diagnosis and fix."}


def judge_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Lexical rubric stand-in for the judge: label match, count of cited numbers, length. Not a quality measure."""
    text, claimed, ref = payload["explanation"], payload["claimed"], payload["reference"]
    station_ok = claimed["station"] == ref["station"]
    type_ok = claimed["fault_type"] == ref["fault_type"] or (
        ref["fault_type"] == "mixed" and claimed["fault_type"] in ("breakdowns", "slow_station")
    )
    correctness = 5 if station_ok and type_ok else 3 if station_ok else 1
    numbers = len(re.findall(r"\d+(?:\.\d+)?%?", text))
    evidence = 1 if numbers == 0 else min(5, 1 + numbers)
    words = len(text.split())
    clarity = 5 if 12 <= words <= 60 else 3 if words >= 5 else 1
    return {
        "correctness": correctness,
        "evidence": evidence,
        "clarity": clarity,
        "overall": round((correctness + evidence + clarity) / 3, 2),
        "comment": "mock lexical rubric",
    }


MOCK_HANDLERS: dict[str, MockHandler] = {
    "monitor": monitor_handler,
    "diagnosis": diagnosis_handler,
    "candidates": candidates_handler,
    "single_agent": single_agent_handler,
    "judge": judge_handler,
}
