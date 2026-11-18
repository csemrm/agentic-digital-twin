"""Generate every number in the paper from a results directory: LaTeX tables plus a macros file.

Usage (from the repository root):
    .venv/bin/python paper/make_tables.py [--results results_real] [--out paper/generated]

Nothing in ``main.tex`` is a hand-typed result. Text cites ``\\Macro`` values written here, and the
tables are rendered from the same CSVs, so re-running after a new experiment updates the paper.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval import analysis  # noqa: E402

NAMES = {
    "rule_based": "Naive rule",
    "toc_heuristic": "TOC rules",
    "twin_search": "Twin search",
    "single_agent": "Single agent",
    "multi_agent_no_sim": "Multi-agent, no sim.",
    "multi_agent": "Multi-agent + sim. (ours)",
}
ORDER = list(NAMES)
MACRO_KEY = {  # system -> macro suffix (letters only)
    "rule_based": "Rule", "toc_heuristic": "Toc", "twin_search": "Twin",
    "single_agent": "Single", "multi_agent_no_sim": "NoSim", "multi_agent": "Multi",
}
GATE_ARMS = [
    ("stress", "Honest, trusting"), ("stress_indep", "Honest, independent"),
    ("stress_forged", "Forged, trusting"), ("stress_forged_indep", "Forged, independent"),
]


def num(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace("-", "$-$")


def signed(x: float, digits: int = 1) -> str:
    return ("$+$" if x >= 0 else "$-$") + f"{abs(x):.{digits}f}"


def cell(row: pd.Series, pct: bool = False, digits: int = 1) -> str:
    k = 100.0 if pct else 1.0
    return f"{num(row['mean'] * k, digits)} [{num(row['ci_low'] * k, digits)}, {num(row['ci_high'] * k, digits)}]"


def get(table: pd.DataFrame, metric: str, **where: str) -> pd.Series:
    mask = table["metric"] == metric
    for k, v in where.items():
        mask &= table[k] == v
    sub = table[mask]
    if sub.empty:
        raise KeyError(f"no row for {metric} {where}")
    return sub.iloc[0]


def tabular(header: list[str], rows: list[list[str]], spec: str) -> str:
    out = [f"\\begin{{tabular}}{{{spec}}}", "\\toprule", " & ".join(header) + " \\\\", "\\midrule"]
    out += [" & ".join(r) + " \\\\" for r in rows]
    out += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", type=Path, default=Path("results_real"))
    ap.add_argument("--out", type=Path, default=Path("paper/generated"))
    args = ap.parse_args()
    res, out = args.results, args.out
    out.mkdir(parents=True, exist_ok=True)

    meta = json.loads((res / "run_meta.json").read_text())
    overall = pd.read_csv(res / "summary_by_system.csv")
    by_scn = pd.read_csv(res / "summary_by_system_scenario.csv")
    runs = pd.read_csv(res / "runs.csv")
    reviews = pd.read_csv(res / "gate_reviews.csv")
    clean = runs[runs["experiment"] == "clean"]
    systems = [s for s in ORDER if s in set(overall["system"])]
    macros: dict[str, str] = {}

    # ---- main table: clean experiment, fault scenarios ------------------------------------------
    rows = []
    for s in systems:
        fa = get(by_scn, "false_alarm_action", system=s, scenario="healthy")
        rows.append([
            NAMES[s],
            cell(get(overall, "station_correct", system=s), pct=True, digits=0),
            cell(get(overall, "gain_pct", system=s)),
            cell(get(overall, "ineffective_fix", system=s), pct=True, digits=0),
            f"{num(100 * fa['mean'], 0)}",
        ])
    (out / "tab_main.tex").write_text(tabular(
        ["System", "Bottleneck acc.\\ (\\%)", "Throughput gain (\\%)", "Ineffective fixes (\\%)", "Healthy false alarms (\\%)"],
        rows, "lcccc"))

    # ---- gate table -------------------------------------------------------------------------------
    catch = {a: analysis.gate_catch_table(reviews[reviews["experiment"] == a], ["system"]).set_index("system") for a, _ in GATE_ARMS}
    rows = []
    for s in systems:
        row = [NAMES[s]]
        for a, _ in GATE_ARMS:
            c = catch[a]
            row.append(f"{num(100 * c.loc[s, 'catch_rate'], 0)} ({int(c.loc[s, 'bad_reviews'])})" if s in c.index else "--")
        rows.append(row)
    (out / "tab_gate.tex").write_text(tabular(["System"] + [lbl for _, lbl in GATE_ARMS], rows, "lcccc"))

    # ---- macros -----------------------------------------------------------------------------------
    macros["Model"] = str(meta["mode"])
    macros["Nseeds"] = str(meta["n_seeds"])
    macros["Npairs"] = str(int(get(overall, "gain_pct", system="multi_agent")["n"]))
    macros["BadRate"] = f"{meta['bad_rate_stress']:g}"
    for s in systems:
        k = MACRO_KEY[s]
        macros[f"Gain{k}"] = num(get(overall, "gain_pct", system=s)["mean"])
        macros[f"Ineff{k}"] = num(100 * get(overall, "ineffective_fix", system=s)["mean"], 0)
        macros[f"Acc{k}"] = num(100 * get(overall, "station_correct", system=s)["mean"], 0)
        macros[f"Tokens{k}"] = f"{int(round(get(overall, 'total_tokens', system=s)['mean'])):,}".replace(",", "\\,")
        macros[f"FalseAlarm{k}"] = num(100 * get(by_scn, "false_alarm_action", system=s, scenario="healthy")["mean"], 0)
        macros[f"Invalid{k}"] = num(100 * get(overall, "invalid_fix", system=s)["mean"], 0)
    for base in ("toc_heuristic", "twin_search", "single_agent", "multi_agent_no_sim"):
        n, d, lo, hi = analysis.paired_diff_ci(clean, "gain_pct", "multi_agent", base)
        k = MACRO_KEY[base]
        macros[f"Diff{k}"] = f"{signed(d)}\\,pp (95\\% CI [{signed(lo)}, {signed(hi)}])"
        macros[f"DiffLo{k}"], macros[f"DiffHi{k}"] = num(lo), num(hi)
    for a, tag in (("stress_forged", "ForgedTrust"), ("stress_forged_indep", "ForgedIndep"), ("stress", "HonestTrust"), ("stress_indep", "HonestIndep")):
        for s in ("multi_agent", "twin_search", "single_agent", "multi_agent_no_sim"):
            macros[f"Catch{tag}{MACRO_KEY[s]}"] = num(100 * catch[a].loc[s, "catch_rate"], 0)
    ci = runs[runs["experiment"].isin(["clean", "clean_indep"]) & runs["scenario"].isin(analysis.FAULT_SCENARIOS)]
    for s in ("single_agent", "multi_agent_no_sim", "multi_agent"):
        g = ci[(ci["system"] == s) & (ci["experiment"] == "clean_indep")]
        macros[f"IndepGain{MACRO_KEY[s]}"] = num(g["gain_pct"].mean())
        macros[f"IndepApplied{MACRO_KEY[s]}"] = num(100 * g["applied"].mean(), 0)
    macros["TwinSims"] = f"{int(clean[(clean['system'] == 'twin_search') & clean['scenario'].isin(analysis.FAULT_SCENARIOS)]['twin_sims'].mean())}"

    lines = ["% Generated by paper/make_tables.py from " + str(res) + "; do not edit."]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    (out / "macros.tex").write_text("\n".join(lines) + "\n")
    print(f"wrote {len(macros)} macros and 2 tables to {out}")


if __name__ == "__main__":
    main()
