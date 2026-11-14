"""Run every system on the same seeded scenarios and write results/ (CSVs, plots, summary).

Usage: ``python -m src.eval.runner [--seeds N] [--out results] [--docs docs] [--bad-rate 0.3]``.
Two base experiments share the grid: ``clean`` (approver never injects bad
recommendations; RQ1, RQ2) and ``stress`` (approver injects bad recommendations
at ``--bad-rate``; RQ3). Unless ``--no-gate-arms`` is given, four more arms ablate
the gate: ``clean_indep``, ``stress_indep`` (a gate that re-simulates on its own
seeds), ``stress_forged`` and ``stress_forged_indep`` (injected bad fixes carry
the good fix's evidence).
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.agents import Pipeline, PipelineSettings, RunRecord, SimulatedApprover, default_client
from src.agents.gate import IndependentApprover
from src.agents.observe import observe
from src.baselines import run_rule_based, run_single_agent, run_toc_heuristic, run_twin_search
from src.eval import analysis, plots, report
from src.eval.metrics import score_run
from src.eval.truth import TruthEvaluator
from src.llm import LLMClient
from src.scenarios import SCENARIOS, Scenario

SYSTEMS = ["rule_based", "toc_heuristic", "twin_search", "single_agent", "multi_agent_no_sim", "multi_agent"]
HUMAN_REVIEW_SEEDS = 2

# Gate arms: (injection on?, forge evidence?, independent gate?). ``clean``/``stress`` keep the evidence-trusting gate.
BASE_ARMS = {"clean": (False, False, False), "stress": (True, False, False)}
GATE_ARMS = {
    "clean_indep": (False, False, True),
    "stress_indep": (True, False, True),
    "stress_forged": (True, True, False),
    "stress_forged_indep": (True, True, True),
}


def make_approver(settings: PipelineSettings, bad_rate: float, seed: int, forge: bool, independent: bool) -> SimulatedApprover:
    """Evidence-trusting or independent re-simulating gate; injection draws depend only on ``seed`` (paired across arms)."""
    kw = dict(min_gain_pct=settings.min_gain_pct, bad_rate=bad_rate, seed=seed, forge_evidence=forge)
    return IndependentApprover(alpha=settings.alpha, n_reps=settings.n_reps, **kw) if independent else SimulatedApprover(**kw)


def run_system(system: str, sc: Scenario, seed: int, client: LLMClient, approver: SimulatedApprover, settings: PipelineSettings) -> RunRecord:
    """Dispatch one run of ``system``."""
    if system == "rule_based":
        return run_rule_based(sc, seed, approver, settings)
    if system == "toc_heuristic":
        return run_toc_heuristic(sc, seed, approver, settings)
    if system == "twin_search":
        return run_twin_search(sc, seed, approver, settings)
    if system == "single_agent":
        return run_single_agent(sc, seed, client, approver, settings)
    return Pipeline(sc, seed, client, approver, settings, use_simulation=system == "multi_agent", system=system).run()


def run_grid(
    client: LLMClient, seeds: list[int], bad_rate: float, experiment: str, truth: TruthEvaluator, settings: PipelineSettings,
    systems: list[str] = SYSTEMS, scenarios: list[str] | None = None, forge: bool = False, independent: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, list[tuple[RunRecord, Scenario]]]:
    """Run all systems x scenarios x seeds for one experiment; returns run rows, gate-review rows, raw records."""
    rows, reviews, records = [], [], []
    for name in scenarios or list(SCENARIOS):
        sc = SCENARIOS[name]
        scenario_offset = 97 * list(SCENARIOS).index(name)
        for seed in seeds:
            for system in systems:
                # same injection draws for every system on a given (scenario, seed): paired comparison
                approver = make_approver(settings, bad_rate, 10_000 + scenario_offset + seed, forge, independent)
                rec = run_system(system, sc, seed, client, approver, settings)
                row, rev = score_run(rec, sc, truth, client, experiment)
                rows.append(row)
                reviews.extend(rev)
                records.append((rec, sc))
    return pd.DataFrame(rows), pd.DataFrame(reviews), records


def write_human_review_template(records: list[tuple[RunRecord, Scenario]], out_dir: Path) -> None:
    """Blind CSV for 2-3 human reviewers (1-5 explanation quality) plus a separate key mapping item to system."""
    picked = [(r, sc) for r, sc in records if r.seed <= min(x.seed for x, _ in records) + HUMAN_REVIEW_SEEDS - 1]
    random.Random(0).shuffle(picked)
    items, key = [], []
    for i, (rec, sc) in enumerate(picked, 1):
        obs = observe(sc.config, rec.seed).payload
        stations = "; ".join(f"S{s['id']} active {s['utilization'] + s['down']:.0%} blocked {s['blocked']:.0%} starved {s['starved']:.0%}" for s in obs["stations"])
        d = rec.diagnoses[0]
        items.append(
            {
                "item_id": f"item{i:03d}", "scenario_seed": f"{sc.name}/{rec.seed}",
                "observation": f"throughput {obs['throughput_vs_reference_pct']:+.1f}% vs normal. {stations}",
                "claimed_bottleneck": d["bottleneck_station"], "claimed_fault": d["fault_type"], "explanation": d["explanation"],
                "reviewer_1_score_1to5": "", "reviewer_2_score_1to5": "", "reviewer_3_score_1to5": "", "notes": "",
            }
        )
        key.append({"item_id": f"item{i:03d}", "system": rec.system, "true_station": sc.truth.station, "true_fault": sc.truth.fault_type})
    pd.DataFrame(items).to_csv(out_dir / "human_review_template.csv", index=False)
    pd.DataFrame(key).to_csv(out_dir / "human_review_key.csv", index=False)


def run_experiments(seeds: list[int], out_dir: Path, docs_dir: Path | None, bad_rate: float, client: LLMClient | None = None,
                    settings: PipelineSettings | None = None, scenarios: list[str] | None = None, gate_arms: bool = False) -> dict[str, Any]:
    """Run the experiments, write all outputs, and return the metadata dict.

    ``clean`` and ``stress`` always run. ``gate_arms`` adds the independent-gate ablation (``GATE_ARMS``).
    """
    client = client or default_client()
    settings = settings or PipelineSettings()
    out_dir.mkdir(parents=True, exist_ok=True)
    truth = TruthEvaluator()
    arms = {**BASE_ARMS, **(GATE_ARMS if gate_arms else {})}
    run_parts, review_parts, records = [], [], []
    for name, (inject, forge, independent) in arms.items():
        r, v, recs = run_grid(client, seeds, bad_rate if inject else 0.0, name, truth, settings, scenarios=scenarios, forge=forge, independent=independent)
        run_parts.append(r)
        review_parts.append(v)
        if name == "clean":
            records = recs
    runs, reviews = pd.concat(run_parts, ignore_index=True), pd.concat(review_parts, ignore_index=True)
    meta = {
        "mode": "mock" if client.is_mock else client.model, "n_seeds": len(seeds), "seeds": seeds, "bad_rate_stress": bad_rate,
        "settings": asdict(settings), "date": datetime.now(timezone.utc).date().isoformat(), "systems": SYSTEMS, "experiments": list(arms),
    }
    clean = runs[runs["experiment"] == "clean"]
    summary = analysis.summarize(clean, ["system", "scenario"])
    overall = analysis.summarize(clean[clean["scenario"].isin(analysis.FAULT_SCENARIOS)], ["system"])
    catch = analysis.gate_catch_table(reviews[reviews["experiment"] == "stress"], ["system", "scenario"])
    catch_overall = analysis.gate_catch_table(reviews[reviews["experiment"] == "stress"], ["system"])
    runs.to_csv(out_dir / "runs.csv", index=False)
    reviews.to_csv(out_dir / "gate_reviews.csv", index=False)
    summary.to_csv(out_dir / "summary_by_system_scenario.csv", index=False)
    overall.to_csv(out_dir / "summary_by_system.csv", index=False)
    catch.to_csv(out_dir / "gate_catch_by_system_scenario.csv", index=False)
    catch_overall.to_csv(out_dir / "gate_catch_by_system.csv", index=False)
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))
    write_human_review_template(records, out_dir)
    plots.plot_all(summary, catch, out_dir / "plots", meta["mode"])
    text = report.build_report(runs, reviews, overall, summary, catch_overall, meta)
    (out_dir / "summary.md").write_text(text)
    if docs_dir is not None:
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "RESULTS.md").write_text(text)
    return meta


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=10, help="number of observation seeds (1..N)")
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--docs", type=Path, default=Path("docs"))
    ap.add_argument("--no-gate-arms", action="store_true", help="skip the independent-gate ablation experiments (faster)")
    ap.add_argument("--bad-rate", type=float, default=0.5, help="bad-recommendation injection rate in the stress experiment")
    args = ap.parse_args()
    meta = run_experiments(list(range(1, args.seeds + 1)), args.out, args.docs, args.bad_rate, gate_arms=not args.no_gate_arms)
    print(f"done ({meta['mode']} mode, {args.seeds} seeds): see {args.out}/summary.md")


if __name__ == "__main__":
    main()
