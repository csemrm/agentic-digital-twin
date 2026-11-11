# Results (MOCK MODE)

> **MOCK MODE.** These numbers come from scripted, rule-based stand-ins for the LLM roles, not a real model. They validate the pipeline, the twin and the metrics. They say nothing about how well a real LLM diagnoses or proposes fixes. In particular the single-agent and multi-agent roles share the same diagnosis heuristic here, so identical diagnosis accuracy is expected by construction. Re-run with `ANTHROPIC_API_KEY` set for real-LLM results.

Seeds per cell: 10 (observation seeds 1..10). Generated 2026-11-11. Stress experiment injects bad recommendations at rate 0.5. All CIs are 95% (Wilson for proportions, t for means).

## Overall, fault scenarios (clean experiment)

| System | Bottleneck acc. % | Fault-type acc. % | Throughput gain % | Invalid/harmful-fix rate % | Ineffective-fix rate % | LLM steps | Tokens | Explanation (1-5) |
|---|---|---|---|---|---|---|---|---|
| rule_based | 27.5 [16.1, 42.8] | n/a | 0.4 [0.1, 0.6] | 0.0 [0.0, 8.8] | 97.5 [87.1, 99.6] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 2.18 [2.09, 2.28] |
| single_agent | 100.0 [91.2, 100.0] | 100.0 [91.2, 100.0] | 13.1 [11.6, 14.7] | 0.0 [0.0, 8.8] | 0.0 [0.0, 8.8] | 1.2 [1.1, 1.3] | 1035.7 [919.9, 1151.4] | 5.00 [5.00, 5.00] |
| multi_agent_no_sim | 100.0 [91.2, 100.0] | 100.0 [91.2, 100.0] | 13.1 [11.6, 14.7] | 0.0 [0.0, 8.8] | 0.0 [0.0, 8.8] | 3.0 [3.0, 3.0] | 1976.4 [1966.2, 1986.7] | 5.00 [5.00, 5.00] |
| multi_agent | 100.0 [91.2, 100.0] | 100.0 [91.2, 100.0] | 16.7 [15.2, 18.2] | 0.0 [0.0, 8.8] | 0.0 [0.0, 8.8] | 3.0 [3.0, 3.0] | 1976.4 [1966.2, 1986.7] | 5.00 [5.00, 5.00] |

## Bottleneck accuracy (%) by scenario

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 0.0 [0.0, 27.8] | 10.0 [1.8, 40.4] | 90.0 [59.6, 98.2] | 0.0 [0.0, 27.8] | 100.0 [72.2, 100.0] |
| single_agent | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] | 90.0 [59.6, 98.2] | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] |
| multi_agent_no_sim | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] | 90.0 [59.6, 98.2] | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] |
| multi_agent | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] | 90.0 [59.6, 98.2] | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] |

## Throughput gain (%) by scenario

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 0.2 [0.1, 0.4] | 0.6 [-0.5, 1.8] | 0.0 [-0.0, 0.1] | 0.5 [0.5, 0.5] | 0.1 [0.1, 0.1] |
| single_agent | 13.6 [13.6, 13.6] | 5.3 [5.3, 5.3] | 0.0 [-0.0, 0.1] | 15.6 [15.6, 15.6] | 18.0 [16.9, 19.2] |
| multi_agent_no_sim | 13.6 [13.6, 13.6] | 5.3 [5.3, 5.3] | 0.0 [-0.0, 0.1] | 15.6 [15.6, 15.6] | 18.0 [16.9, 19.2] |
| multi_agent | 19.2 [19.2, 19.2] | 8.7 [8.7, 8.7] | 0.0 [0.0, 0.0] | 20.1 [20.1, 20.1] | 18.8 [18.8, 18.8] |

## Invalid or harmful fix rate (%) by scenario

A recommendation is invalid if it breaks the typed-action constraints, harmful if independent replications show a throughput loss above 1%.

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| single_agent | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| multi_agent_no_sim | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| multi_agent | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |

## Ineffective-fix rate (%) by scenario

An applied fix is ineffective if independent replications show a throughput gain below 2% (includes any action on the healthy line).

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 100.0 [72.2, 100.0] | 90.0 [59.6, 98.2] | 10.0 [1.8, 40.4] | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] |
| single_agent | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 10.0 [1.8, 40.4] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| multi_agent_no_sim | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 10.0 [1.8, 40.4] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| multi_agent | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |

## False-alarm actions on the healthy line (%)

| System | healthy |
|---|---|
| rule_based | 10.0 [1.8, 40.4] |
| single_agent | 10.0 [1.8, 40.4] |
| multi_agent_no_sim | 10.0 [1.8, 40.4] |
| multi_agent | 0.0 [0.0, 27.8] |

## Human-gate catch rate (stress experiment)

| System | Bad recs reaching gate | Caught % | 95% CI |
|---|---|---|---|
| rule_based | 20 | 60.0 | [38.7, 78.1] |
| single_agent | 29 | 65.5 | [47.3, 80.1] |
| multi_agent_no_sim | 30 | 63.3 | [45.5, 78.1] |
| multi_agent | 38 | 100.0 | [90.8, 100.0] |

Catch rate split by why the recommendation was bad:

| System | Reason | Bad recs | Caught % | 95% CI |
|---|---|---|---|---|
| multi_agent | harmful | 16 | 100.0 | [80.6, 100.0] |
| multi_agent | invalid | 22 | 100.0 | [85.1, 100.0] |
| multi_agent_no_sim | harmful | 11 | 0.0 | [0.0, 25.9] |
| multi_agent_no_sim | invalid | 19 | 100.0 | [83.2, 100.0] |
| rule_based | harmful | 8 | 0.0 | [0.0, 32.4] |
| rule_based | invalid | 12 | 100.0 | [75.7, 100.0] |
| single_agent | harmful | 10 | 0.0 | [0.0, 27.8] |
| single_agent | invalid | 19 | 100.0 | [83.2, 100.0] |

Share of stress runs where a bad (invalid or harmful) fix was actually applied: rule_based 20%, single_agent 25%, multi_agent_no_sim 28%, multi_agent 0%.

## Answers to the research questions

**RQ1: Does a multi-agent design find the true bottleneck more accurately than a single LLM agent?**

Bottleneck accuracy (fault scenarios, first diagnosis): multi-agent 100.0 [91.2, 100.0]%, single agent 100.0 [91.2, 100.0]%. Paired difference (multi - single): +0.00 pp (95% CI [+0.00, +0.00], n=40 pairs): no detectable difference (CI includes 0). Versus rule-based: +72.50 pp (95% CI [+57.50, +85.00], n=40 pairs): higher. Cost: multi-agent uses 3.00 [3.00, 3.00] LLM steps and 1976 [1966, 1987] tokens per run vs 1.20 [1.07, 1.33] steps and 1036 [920, 1151] tokens for the single agent.

In mock mode both designs use the same diagnosis heuristic, so this comparison cannot answer RQ1; only a real-LLM run can.

**RQ2: Does simulating fixes before recommending them improve recommendation quality?**

Multi-agent with simulation vs without (clean experiment, fault scenarios). Throughput gain difference: +3.57 pp of throughput (95% CI [+2.97, +4.18], n=40 pairs): higher. Invalid/harmful-fix rate difference (fraction of runs): +0.00 (95% CI [+0.00, +0.00], n=40 pairs): no detectable difference (CI includes 0). Ineffective-fix rate difference (fraction of runs): +0.00 (95% CI [+0.00, +0.00], n=40 pairs): no detectable difference (CI includes 0). Versus the single agent, throughput gain difference: +3.57 pp of throughput (95% CI [+2.97, +4.18], n=40 pairs): higher. Note that the Simulation agent picks the best-measured candidate from the same proposal list, so a positive gain difference partly reflects selection among candidates rather than better proposals.

**RQ3: How often does the human gate catch a harmful or invalid recommendation?**

Overall catch rate over bad recommendations that reached the gate: rule_based 60%, single_agent 66%, multi_agent_no_sim 63%, multi_agent 100%. Invalid recommendations caught: rule_based 100% (n=12), single_agent 100% (n=19), multi_agent_no_sim 100% (n=19), multi_agent 100% (n=22). Harmful-but-valid recommendations caught: rule_based 0% (n=8), single_agent 0% (n=10), multi_agent_no_sim 0% (n=11), multi_agent 100% (n=16). By design of the simulated approver, harmful-but-valid fixes can only be caught when twin numbers are shown (multi-agent), so read the harmful row as a check of that mechanism rather than an independent finding. A real supervisor's catch rate needs human data (the dashboard has the real gate).

## Limitations

- The twin is both the world the agents observe and the verifier they use, so there is no model mismatch: verified gains are real inside the simulation by definition. Real plants would add a sim-to-real gap.
- Fault scenarios are synthetic, few (5) and chosen by the authors; ground truth is exact only because the faults are seeded. Line parameters are illustrative, not from a real plant.
- 10 seeds per cell gives wide confidence intervals; small differences are not distinguishable from noise.
- The human gate is a rule-based simulation of a supervisor (batch mode). It never errs, is never fooled by plausible text, and sees exactly the evidence defined in `docs/ASSUMPTIONS.md`.
- Fix effects are measured on 20 independent replications; a fix is 'harmful' if it lowers mean throughput by more than 1%.
- Explanation quality: the judge is a lexical mock rubric (counts cited numbers, label match, length), not a measure of quality. Human scores must be collected via `results/human_review_template.csv` (blind; key in `human_review_key.csv`).
- Throughput gain averages fixes over runs including ones where no fix was applied (gain 0).
