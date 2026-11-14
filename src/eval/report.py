"""Generate results/summary.md: tables from the actual runs and data-driven answers to RQ1-RQ3."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.eval import analysis
from src.eval.analysis import FAULT_SCENARIOS, paired_diff_ci

SYSTEM_ORDER = ["rule_based", "toc_heuristic", "twin_search", "single_agent", "multi_agent_no_sim", "multi_agent"]
PCT_METRICS = {"station_correct", "type_correct", "invalid_fix", "bad_applied", "false_alarm_action"}


def cell(row: pd.Series | None, pct: bool = False, digits: int = 2) -> str:
    """Format ``mean [ci_low, ci_high]`` (or n/a)."""
    if row is None or math.isnan(row["mean"]):
        return "n/a"
    k = 100.0 if pct else 1.0
    lo, hi = row["ci_low"] * k, row["ci_high"] * k
    ci = "" if math.isnan(lo) else f" [{lo:.{digits}f}, {hi:.{digits}f}]"
    return f"{row['mean'] * k:.{digits}f}{ci}"


def pick(table: pd.DataFrame, metric: str, **where: str) -> pd.Series | None:
    """Single row of a long-form summary table, or None."""
    mask = table["metric"] == metric
    for k, v in where.items():
        mask &= table[k] == v
    sub = table[mask]
    return sub.iloc[0] if len(sub) else None


def md_table(header: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavoured markdown table."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def verdict(n: int, diff: float, lo: float, hi: float, unit: str) -> str:
    """One-phrase reading of a paired difference and its bootstrap CI."""
    if n == 0 or math.isnan(diff):
        return "not computable"
    word = "higher" if lo > 0 else "lower" if hi < 0 else "no detectable difference (CI includes 0)"
    return f"{diff:+.2f}{unit} (95% CI [{lo:+.2f}, {hi:+.2f}], n={n} pairs): {word}"


def _systems(table: pd.DataFrame) -> list[str]:
    return [s for s in SYSTEM_ORDER if s in set(table["system"])]


def _overall_table(overall: pd.DataFrame) -> str:
    cols = [("station_correct", "Bottleneck acc. %", True), ("type_correct", "Fault-type acc. %", True), ("gain_pct", "Throughput gain %", False),
            ("invalid_fix", "Invalid/harmful-fix rate %", True), ("ineffective_fix", "Ineffective-fix rate %", True), ("steps", "LLM steps", False), ("total_tokens", "Tokens", False),
            ("expl_quality", "Explanation (1-5)", False)]
    rows = [[s] + [cell(pick(overall, m, system=s), pct, 1 if m != "expl_quality" else 2) for m, _, pct in cols] for s in _systems(overall)]
    return md_table(["System"] + [c[1] for c in cols], rows)


def _scenario_table(summary: pd.DataFrame, metric: str, pct: bool) -> str:
    scenarios = list(dict.fromkeys(summary["scenario"]))
    rows = [[s] + [cell(pick(summary, metric, system=s, scenario=sc), pct, 1) for sc in scenarios] for s in _systems(summary)]
    return md_table(["System"] + scenarios, rows)


def _baseline_section(clean: pd.DataFrame, overall: pd.DataFrame) -> list[str]:
    """Multi-agent vs the non-LLM baselines: does the agent design beat a classical rule or brute-force twin search?"""
    have = set(clean["system"])
    if not {"toc_heuristic", "twin_search"} <= have:
        return []
    out = ["**Does the multi-agent system beat strong non-LLM baselines?**", "",
           "`toc_heuristic` applies Theory-of-Constraints rules to the observed KPIs (no twin, no LLM). `twin_search` simulates the whole typed action grid and gates "
           "the best verified fix (no LLM, no diagnosis). Paired differences, multi-agent minus baseline (clean experiment, fault scenarios):", ""]
    rows = []
    for base in ("toc_heuristic", "twin_search"):
        g = paired_diff_ci(clean, "gain_pct", "multi_agent", base)
        e = paired_diff_ci(clean, "ineffective_fix", "multi_agent", base)
        rows.append([base, verdict(g[0], g[1], g[2], g[3], " pp of throughput"), verdict(e[0], e[1], e[2], e[3], "")])
    out += [md_table(["Baseline", "Throughput gain", "Ineffective-fix rate (fraction of runs)"], rows), ""]
    sims = clean[(clean["system"] == "twin_search") & clean["scenario"].isin(FAULT_SCENARIOS)]["twin_sims"].mean()
    tok = pick(overall[overall["system"] == "multi_agent"], "total_tokens")
    ts = paired_diff_ci(clean, "gain_pct", "multi_agent", "twin_search")
    if ts[0] == 0 or math.isnan(ts[1]):
        reading = "The multi-agent vs twin-search throughput difference is not computable."
    elif ts[3] < 0:
        reading = ("Exhaustive twin search gains more throughput than multi-agent, so on this 5-station grid the proposer's shortlist, not the twin, limits the "
                   "multi-agent result; the LLM roles are not what produces the gain.")
    elif ts[2] > 0:
        reading = "Multi-agent gains more throughput than exhaustive twin search, so its targeted proposals find fixes the coarse grid misses."
    else:
        reading = ("No detectable throughput difference between multi-agent and exhaustive twin search, so the LLM roles add little over brute force here; "
                   "their case would rest on action spaces too large to enumerate, which a 5-station grid is not.")
    out += [f"Cost: `twin_search` spends about {sims:.0f} twin simulations per run on a fault line and no tokens; multi-agent tests at most the proposer's candidate "
            f"list (default 5) per round with {cell(tok, digits=0)} tokens. {reading} "
            "What the multi-agent system still offers over `twin_search` is a diagnosis and an explanation, which the search does not produce: it makes no diagnosis, so "
            "its station accuracy is only the station its best fix targets and its fault type is not scored. Its candidate grid is limited to the typed action set, as for "
            "every system. In mock mode the multi-agent proposer is rule-based, so this comparison says nothing about LLM-proposed candidates.", ""]
    return out


def build_report(runs: pd.DataFrame, reviews: pd.DataFrame, overall: pd.DataFrame, summary: pd.DataFrame, catch_overall: pd.DataFrame, meta: dict[str, Any]) -> str:
    """Assemble the markdown report; every number comes from ``runs``/``reviews``."""
    clean = runs[runs["experiment"] == "clean"]
    stress = runs[runs["experiment"] == "stress"]
    mock = meta["mode"] == "mock"
    out = [f"# Results ({'MOCK MODE' if mock else 'model: ' + meta['mode']})", ""]
    if mock:
        out += [
            "> **MOCK MODE.** These numbers come from scripted, rule-based stand-ins for the LLM roles, not a real model. They validate the pipeline, the twin and the "
            "metrics. They say nothing about how well a real LLM diagnoses or proposes fixes. In particular the single-agent and multi-agent roles share the same "
            "diagnosis heuristic here, so identical diagnosis accuracy is expected by construction. Re-run with `ANTHROPIC_API_KEY` set for real-LLM results.", ""]
    out += [f"Seeds per cell: {meta['n_seeds']} (observation seeds {meta['seeds'][0]}..{meta['seeds'][-1]}). Generated {meta['date']}. "
            f"Stress experiment injects bad recommendations at rate {meta['bad_rate_stress']}. All CIs are 95% (Wilson for proportions, t for means).", "",
            "## Overall, fault scenarios (clean experiment)", "", _overall_table(overall), "",
            "## Bottleneck accuracy (%) by scenario", "", _scenario_table(summary, "station_correct", True), "",
            "## Throughput gain (%) by scenario", "", _scenario_table(summary, "gain_pct", False), "",
            "## Invalid or harmful fix rate (%) by scenario", "",
            "A recommendation is invalid if it breaks the typed-action constraints, harmful if independent replications show a throughput loss above 1%.", "",
            _scenario_table(summary, "invalid_fix", True), "",
            "## Ineffective-fix rate (%) by scenario", "",
            "An applied fix is ineffective if independent replications show a throughput gain below 2% (includes any action on the healthy line).", "",
            _scenario_table(summary, "ineffective_fix", True), "",
            "## False-alarm actions on the healthy line (%)", "", _scenario_table(summary[summary["scenario"] == "healthy"], "false_alarm_action", True), ""]
    out += ["## Human-gate catch rate (stress experiment)", "",
            md_table(["System", "Bad recs reaching gate", "Caught %", "95% CI"],
                     [[r.system, str(int(r.bad_reviews)), f"{100 * r.catch_rate:.1f}", f"[{100 * r.ci_low:.1f}, {100 * r.ci_high:.1f}]"]
                      for r in catch_overall.set_index("system").reindex(_systems(catch_overall)).reset_index().itertuples()]), ""]
    escaped = {s: stress[(stress["system"] == s) & stress["scenario"].isin(FAULT_SCENARIOS)]["bad_applied"].mean() for s in _systems(stress)}
    by_status = analysis.gate_catch_by_status(reviews[reviews["experiment"] == "stress"])
    out += ["Catch rate split by why the recommendation was bad:", "",
            md_table(["System", "Reason", "Bad recs", "Caught %", "95% CI"],
                     [[r.system, r.status, str(int(r.bad_reviews)), f"{100 * r.catch_rate:.1f}", f"[{100 * r.ci_low:.1f}, {100 * r.ci_high:.1f}]"]
                      for r in by_status.itertuples()]) if not by_status.empty else "No bad recommendations reached the gate.", "",
            "Share of stress runs where a bad (invalid or harmful) fix was actually applied: "
            + ", ".join(f"{s} {100 * v:.0f}%" for s, v in escaped.items()) + ".", ""]

    a_ma, a_sa = overall[overall["system"] == "multi_agent"], overall[overall["system"] == "single_agent"]
    d1 = paired_diff_ci(clean, "station_correct", "multi_agent", "single_agent")
    d1r = paired_diff_ci(clean, "station_correct", "multi_agent", "rule_based")
    tok_ma, tok_sa = pick(a_ma, "total_tokens"), pick(a_sa, "total_tokens")
    d2g = paired_diff_ci(clean, "gain_pct", "multi_agent", "multi_agent_no_sim")
    d2i = paired_diff_ci(clean, "invalid_fix", "multi_agent", "multi_agent_no_sim")
    d2s = paired_diff_ci(clean, "gain_pct", "multi_agent", "single_agent")
    d2e = paired_diff_ci(clean, "ineffective_fix", "multi_agent", "multi_agent_no_sim")
    out += ["## Answers to the research questions", "",
            "**RQ1: Does a multi-agent design find the true bottleneck more accurately than a single LLM agent?**", "",
            f"Bottleneck accuracy (fault scenarios, first diagnosis): multi-agent {cell(pick(a_ma, 'station_correct'), True, 1)}%, "
            f"single agent {cell(pick(a_sa, 'station_correct'), True, 1)}%. Paired difference (multi - single): "
            f"{verdict(d1[0], 100 * d1[1], 100 * d1[2], 100 * d1[3], ' pp')}. Versus rule-based: {verdict(d1r[0], 100 * d1r[1], 100 * d1r[2], 100 * d1r[3], ' pp')}. "
            f"Cost: multi-agent uses {cell(pick(a_ma, 'steps'))} LLM steps and {cell(tok_ma, digits=0)} tokens per run vs "
            f"{cell(pick(a_sa, 'steps'))} steps and {cell(tok_sa, digits=0)} tokens for the single agent.", ""]
    if mock:
        out += ["In mock mode both designs use the same diagnosis heuristic, so this comparison cannot answer RQ1; only a real-LLM run can.", ""]
    out += ["**RQ2: Does simulating fixes before recommending them improve recommendation quality?**", "",
            f"Multi-agent with simulation vs without (clean experiment, fault scenarios). Throughput gain difference: {verdict(d2g[0], d2g[1], d2g[2], d2g[3], ' pp of throughput')}. "
            f"Invalid/harmful-fix rate difference (fraction of runs): {verdict(d2i[0], d2i[1], d2i[2], d2i[3], '')}. "
            f"Ineffective-fix rate difference (fraction of runs): {verdict(d2e[0], d2e[1], d2e[2], d2e[3], '')}. Versus the single agent, throughput gain difference: "
            f"{verdict(d2s[0], d2s[1], d2s[2], d2s[3], ' pp of throughput')}. Note that the Simulation agent picks the best-measured candidate from the same proposal list, "
            "so a positive gain difference partly reflects selection among candidates rather than better proposals.", ""]
    out += _baseline_section(clean, overall)

    def rate(system: str, status: str) -> str:
        r = by_status[(by_status["system"] == system) & (by_status["status"] == status)]
        return f"{100 * r['catch_rate'].iloc[0]:.0f}% (n={int(r['bad_reviews'].iloc[0])})" if len(r) else "n/a (none reached the gate)"

    c = catch_overall.set_index("system")["catch_rate"] if not catch_overall.empty else pd.Series(dtype=float)
    out += ["**RQ3: How often does the human gate catch a harmful or invalid recommendation?**", "",
            "Overall catch rate over bad recommendations that reached the gate: "
            + ", ".join(f"{s} {100 * c[s]:.0f}%" for s in _systems(runs) if s in c.index) + ". "
            "Invalid recommendations caught: "
            + ", ".join(f"{s} {rate(s, 'invalid')}" for s in _systems(runs)) + ". "
            "Harmful-but-valid recommendations caught: "
            + ", ".join(f"{s} {rate(s, 'harmful')}" for s in _systems(runs)) + ". "
            "By design of the simulated approver, harmful-but-valid fixes can only be caught when twin numbers are shown (multi-agent), so read the harmful row as a check "
            "of that mechanism rather than an independent finding. A real supervisor's catch rate needs human data (the dashboard has the real gate).", "",
            "## Limitations", "",
            "- The twin is both the world the agents observe and the verifier they use, so there is no model mismatch: verified gains are real inside the simulation by definition. Real plants would add a sim-to-real gap.",
            "- Fault scenarios are synthetic, few (5) and chosen by the authors; ground truth is exact only because the faults are seeded. Line parameters are illustrative, not from a real plant.",
            f"- {meta['n_seeds']} seeds per cell gives wide confidence intervals; small differences are not distinguishable from noise.",
            "- The human gate is a rule-based simulation of a supervisor (batch mode). It never errs, is never fooled by plausible text, and sees exactly the evidence defined in `docs/ASSUMPTIONS.md`.",
            "- Fix effects are measured on 20 independent replications; a fix is 'harmful' if it lowers mean throughput by more than 1%.",
            "- Explanation quality: the judge is " + ("a lexical mock rubric (counts cited numbers, label match, length), not a measure of quality" if mock else "an LLM judge that sees the reference label; it may favour fluent text and was not validated against the human scores")
            + ". Human scores must be collected via `results/human_review_template.csv` (blind; key in `human_review_key.csv`).",
            "- Throughput gain averages fixes over runs including ones where no fix was applied (gain 0)."]
    return "\n".join(out) + "\n"
