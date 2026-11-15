# Results (model: gpt-4.1-mini)

Seeds per cell: 10 (observation seeds 1..10). Generated 2026-11-15. Stress experiment injects bad recommendations at rate 0.5. All CIs are 95% (Wilson for proportions, t for means).

## Overall, fault scenarios (clean experiment)

| System | Bottleneck acc. % | Fault-type acc. % | Throughput gain % | Invalid/harmful-fix rate % | Ineffective-fix rate % | LLM steps | Tokens | Explanation (1-5) |
|---|---|---|---|---|---|---|---|---|
| rule_based | 27.5 [16.1, 42.8] | n/a | 0.4 [0.1, 0.6] | 0.0 [0.0, 8.8] | 97.5 [87.1, 99.6] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 2.23 [2.10, 2.37] |
| toc_heuristic | 100.0 [91.2, 100.0] | 75.0 [59.8, 85.8] | 13.5 [12.3, 14.7] | 0.0 [0.0, 8.8] | 0.0 [0.0, 8.8] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 3.50 [3.26, 3.75] |
| twin_search | 100.0 [91.2, 100.0] | n/a | 17.7 [16.7, 18.6] | 0.0 [0.0, 8.8] | 0.0 [0.0, 8.8] | 0.0 [0.0, 0.0] | 0.0 [0.0, 0.0] | 2.08 [2.02, 2.14] |
| single_agent | 75.0 [59.8, 85.8] | 75.0 [59.8, 85.8] | 7.8 [5.2, 10.4] | 15.0 [7.1, 29.1] | 25.0 [14.2, 40.2] | 1.0 [1.0, 1.0] | 1069.0 [1062.8, 1075.1] | 4.35 [4.12, 4.58] |
| multi_agent_no_sim | 80.0 [65.2, 89.5] | 72.5 [57.2, 83.9] | 8.1 [5.9, 10.2] | 0.0 [0.0, 8.8] | 40.0 [26.3, 55.4] | 3.0 [3.0, 3.0] | 2794.7 [2758.7, 2830.6] | 4.30 [4.06, 4.53] |
| multi_agent | 80.0 [65.2, 89.5] | 72.5 [57.2, 83.9] | 12.3 [10.6, 14.1] | 0.0 [0.0, 8.8] | 0.0 [0.0, 8.8] | 3.1 [3.0, 3.2] | 2887.8 [2757.9, 3017.7] | 4.30 [4.06, 4.53] |

## Bottleneck accuracy (%) by scenario

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 0.0 [0.0, 27.8] | 10.0 [1.8, 40.4] | 90.0 [59.6, 98.2] | 0.0 [0.0, 27.8] | 100.0 [72.2, 100.0] |
| toc_heuristic | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] | 90.0 [59.6, 98.2] | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] |
| twin_search | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] | 90.0 [59.6, 98.2] | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] |
| single_agent | 100.0 [72.2, 100.0] | 30.0 [10.8, 60.3] | 0.0 [0.0, 27.8] | 70.0 [39.7, 89.2] | 100.0 [72.2, 100.0] |
| multi_agent_no_sim | 80.0 [49.0, 94.3] | 60.0 [31.3, 83.2] | 0.0 [0.0, 27.8] | 80.0 [49.0, 94.3] | 100.0 [72.2, 100.0] |
| multi_agent | 80.0 [49.0, 94.3] | 60.0 [31.3, 83.2] | 0.0 [0.0, 27.8] | 80.0 [49.0, 94.3] | 100.0 [72.2, 100.0] |

## Throughput gain (%) by scenario

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 0.2 [0.1, 0.4] | 0.6 [-0.5, 1.8] | 0.0 [-0.0, 0.1] | 0.5 [0.5, 0.5] | 0.1 [0.1, 0.1] |
| toc_heuristic | 12.8 [12.8, 12.8] | 8.1 [8.1, 8.1] | 0.0 [-0.0, 0.0] | 14.6 [14.6, 14.6] | 18.4 [17.5, 19.3] |
| twin_search | 19.2 [19.2, 19.2] | 12.7 [12.7, 12.7] | 0.1 [-0.1, 0.3] | 20.1 [20.1, 20.1] | 18.8 [18.8, 18.8] |
| single_agent | 13.7 [13.1, 14.2] | 0.8 [-3.4, 5.0] | -2.1 [-6.4, 2.2] | 9.1 [1.2, 16.9] | 7.6 [3.8, 11.5] |
| multi_agent_no_sim | 11.9 [7.4, 16.4] | 5.9 [2.5, 9.2] | -1.4 [-5.9, 3.0] | 12.8 [8.1, 17.6] | 1.6 [0.1, 3.2] |
| multi_agent | 14.5 [12.2, 16.7] | 7.7 [6.0, 9.5] | 0.0 [0.0, 0.0] | 17.3 [15.5, 19.2] | 9.8 [5.1, 14.6] |

## Invalid or harmful fix rate (%) by scenario

A recommendation is invalid if it breaks the typed-action constraints, harmful if independent replications show a throughput loss above 1%.

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| toc_heuristic | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| twin_search | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| single_agent | 0.0 [0.0, 27.8] | 30.0 [10.8, 60.3] | 20.0 [5.7, 51.0] | 30.0 [10.8, 60.3] | 0.0 [0.0, 27.8] |
| multi_agent_no_sim | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 10.0 [1.8, 40.4] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| multi_agent | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |

## Ineffective-fix rate (%) by scenario

An applied fix is ineffective if independent replications show a throughput gain below 2% (includes any action on the healthy line).

| System | breakdowns | buffer | healthy | mixed | slow_station |
|---|---|---|---|---|---|
| rule_based | 100.0 [72.2, 100.0] | 90.0 [59.6, 98.2] | 10.0 [1.8, 40.4] | 100.0 [72.2, 100.0] | 100.0 [72.2, 100.0] |
| toc_heuristic | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 10.0 [1.8, 40.4] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| twin_search | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 10.0 [1.8, 40.4] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |
| single_agent | 0.0 [0.0, 27.8] | 70.0 [39.7, 89.2] | 100.0 [72.2, 100.0] | 30.0 [10.8, 60.3] | 0.0 [0.0, 27.8] |
| multi_agent_no_sim | 20.0 [5.7, 51.0] | 40.0 [16.8, 68.7] | 100.0 [72.2, 100.0] | 20.0 [5.7, 51.0] | 80.0 [49.0, 94.3] |
| multi_agent | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] | 0.0 [0.0, 27.8] |

## False-alarm actions on the healthy line (%)

| System | healthy |
|---|---|
| rule_based | 10.0 [1.8, 40.4] |
| toc_heuristic | 10.0 [1.8, 40.4] |
| twin_search | 10.0 [1.8, 40.4] |
| single_agent | 100.0 [72.2, 100.0] |
| multi_agent_no_sim | 100.0 [72.2, 100.0] |
| multi_agent | 0.0 [0.0, 27.8] |

## Human-gate catch rate (stress experiment)

| System | Bad recs reaching gate | Caught % | 95% CI |
|---|---|---|---|
| rule_based | 20 | 60.0 | [38.7, 78.1] |
| toc_heuristic | 20 | 60.0 | [38.7, 78.1] |
| twin_search | 38 | 100.0 | [90.8, 100.0] |
| single_agent | 44 | 56.8 | [42.2, 70.3] |
| multi_agent_no_sim | 41 | 61.0 | [45.7, 74.3] |
| multi_agent | 37 | 100.0 | [90.6, 100.0] |

Catch rate split by why the recommendation was bad:

| System | Reason | Bad recs | Caught % | 95% CI |
|---|---|---|---|---|
| multi_agent | harmful | 16 | 100.0 | [80.6, 100.0] |
| multi_agent | invalid | 21 | 100.0 | [84.5, 100.0] |
| multi_agent_no_sim | harmful | 16 | 0.0 | [0.0, 19.4] |
| multi_agent_no_sim | invalid | 25 | 100.0 | [86.7, 100.0] |
| rule_based | harmful | 8 | 0.0 | [0.0, 32.4] |
| rule_based | invalid | 12 | 100.0 | [75.7, 100.0] |
| single_agent | harmful | 19 | 0.0 | [0.0, 16.8] |
| single_agent | invalid | 25 | 100.0 | [86.7, 100.0] |
| toc_heuristic | harmful | 8 | 0.0 | [0.0, 32.4] |
| toc_heuristic | invalid | 12 | 100.0 | [75.7, 100.0] |
| twin_search | harmful | 16 | 100.0 | [80.6, 100.0] |
| twin_search | invalid | 22 | 100.0 | [85.1, 100.0] |

Share of stress runs where a bad (invalid or harmful) fix was actually applied: rule_based 20%, toc_heuristic 20%, twin_search 0%, single_agent 38%, multi_agent_no_sim 30%, multi_agent 0%.

## Answers to the research questions

**RQ1: Does a multi-agent design find the true bottleneck more accurately than a single LLM agent?**

Bottleneck accuracy (fault scenarios, first diagnosis): multi-agent 80.0 [65.2, 89.5]%, single agent 75.0 [59.8, 85.8]%. Paired difference (multi - single): +5.00 pp (95% CI [-10.00, +20.00], n=40 pairs): no detectable difference (CI includes 0). Versus rule-based: +52.50 pp (95% CI [+37.50, +67.50], n=40 pairs): higher. Cost: multi-agent uses 3.10 [2.96, 3.24] LLM steps and 2888 [2758, 3018] tokens per run vs 1.00 [1.00, 1.00] steps and 1069 [1063, 1075] tokens for the single agent.

**RQ2: Does simulating fixes before recommending them improve recommendation quality?**

Multi-agent with simulation vs without (clean experiment, fault scenarios). Throughput gain difference: +4.28 pp of throughput (95% CI [+2.75, +5.94], n=40 pairs): higher. Invalid/harmful-fix rate difference (fraction of runs): +0.00 (95% CI [+0.00, +0.00], n=40 pairs): no detectable difference (CI includes 0). Ineffective-fix rate difference (fraction of runs): -0.40 (95% CI [-0.55, -0.25], n=40 pairs): lower. Versus the single agent, throughput gain difference: +4.54 pp of throughput (95% CI [+2.11, +7.10], n=40 pairs): higher. Note that the Simulation agent picks the best-measured candidate from the same proposal list, so a positive gain difference partly reflects selection among candidates rather than better proposals.

**Does the multi-agent system beat strong non-LLM baselines?**

`toc_heuristic` applies Theory-of-Constraints rules to the observed KPIs (no twin, no LLM). `twin_search` simulates the whole typed action grid and gates the best verified fix (no LLM, no diagnosis). Paired differences, multi-agent minus baseline (clean experiment, fault scenarios):

| Baseline | Throughput gain | Ineffective-fix rate (fraction of runs) |
|---|---|---|
| toc_heuristic | -1.13 pp of throughput (95% CI [-3.05, +0.71], n=40 pairs): no detectable difference (CI includes 0) | +0.00 (95% CI [+0.00, +0.00], n=40 pairs): no detectable difference (CI includes 0) |
| twin_search | -5.35 pp of throughput (95% CI [-6.76, -3.95], n=40 pairs): lower | +0.00 (95% CI [+0.00, +0.00], n=40 pairs): no detectable difference (CI includes 0) |

Cost: `twin_search` spends about 496 twin simulations per run on a fault line and no tokens; multi-agent tests at most the proposer's candidate list (default 5) per round with 2888 [2758, 3018] tokens. Exhaustive twin search gains more throughput than multi-agent, so on this 5-station grid the proposer's shortlist, not the twin, limits the multi-agent result; the LLM roles are not what produces the gain. What the multi-agent system still offers over `twin_search` is a diagnosis and an explanation, which the search does not produce: it makes no diagnosis, so its station accuracy is only the station its best fix targets and its fault type is not scored. Its candidate grid is limited to the typed action set, as for every system. In mock mode the multi-agent proposer is rule-based, so this comparison says nothing about LLM-proposed candidates.

## Does the gate need to trust the evidence? (independent re-simulation)

The default gate approves a verified fix iff the *presented* twin evidence clears the threshold, so a fix that arrives with stale or fabricated evidence is approved on its numbers. The independent gate ignores presented evidence: it validates the action, then re-simulates it on its own seeds (3000+, disjoint from the Simulation agent's 1000+ and the scoring seeds 2000+) with the same test, and decides on that alone. In the forged arms every injected bad fix that has evidence carries the real fix's evidence. 'Bad' is judged by the independent scoring replications, not by either gate.

Catch rate over bad recommendations reaching the gate (stress experiments):

| System | honest evidence, trusting gate | honest evidence, independent gate | forged evidence, trusting gate | forged evidence, independent gate |
|---|---|---|---|---|
| rule_based | 60% (n=20) | 100% (n=20) | 60% (n=20) | 100% (n=20) |
| toc_heuristic | 60% (n=20) | 100% (n=20) | 60% (n=20) | 100% (n=20) |
| twin_search | 100% (n=38) | 100% (n=38) | 63% (n=30) | 100% (n=38) |
| single_agent | 57% (n=44) | 100% (n=75) | 57% (n=44) | 100% (n=75) |
| multi_agent_no_sim | 61% (n=41) | 100% (n=70) | 61% (n=41) | 100% (n=70) |
| multi_agent | 100% (n=37) | 100% (n=38) | 63% (n=30) | 100% (n=38) |

Cost of independence on good fixes (clean experiment, fault scenarios; no bad recommendations injected):

| System | Gain %, trusting gate | Fixes applied | Gain %, independent gate | Fixes applied |
|---|---|---|---|---|
| rule_based | 0.4 [0.1, 0.6] | 100% | 0.1 [-0.1, 0.4] | 2% |
| toc_heuristic | 13.5 [12.3, 14.7] | 100% | 13.5 [12.3, 14.7] | 100% |
| twin_search | 17.7 [16.7, 18.6] | 100% | 17.7 [16.7, 18.6] | 100% |
| single_agent | 7.8 [5.2, 10.4] | 100% | 9.7 [7.8, 11.7] | 82% |
| multi_agent_no_sim | 8.1 [5.9, 10.2] | 100% | 10.2 [8.4, 12.0] | 88% |
| multi_agent | 12.3 [10.6, 14.1] | 100% | 12.3 [10.6, 14.1] | 100% |

Reading: with forged evidence the trusting gate can only catch invalid actions, so a harmful-but-valid fix that arrives with good-looking numbers escapes. The independent gate catches it because it never uses those numbers. The price is extra twin simulations per review (2 x n_reps) and the gate itself becoming the verifier: a system with no Simulation step is also checked, so differences in fix safety between systems shrink under this gate. The re-simulation uses the same twin as the proposer, so it removes selection bias and forgery but not model mismatch; a real sim-to-real gap needs a mis-specified-twin experiment.

**RQ3: How often does the human gate catch a harmful or invalid recommendation?**

Overall catch rate over bad recommendations that reached the gate: rule_based 60%, toc_heuristic 60%, twin_search 100%, single_agent 57%, multi_agent_no_sim 61%, multi_agent 100%. Invalid recommendations caught: rule_based 100% (n=12), toc_heuristic 100% (n=12), twin_search 100% (n=22), single_agent 100% (n=25), multi_agent_no_sim 100% (n=25), multi_agent 100% (n=21). Harmful-but-valid recommendations caught: rule_based 0% (n=8), toc_heuristic 0% (n=8), twin_search 100% (n=16), single_agent 0% (n=19), multi_agent_no_sim 0% (n=16), multi_agent 100% (n=16). By design of the default simulated approver, harmful-but-valid fixes can only be caught when twin numbers are shown (multi-agent), so read the harmful row as a check of that mechanism rather than an independent finding; the independent-gate section above tests what happens when those numbers cannot be trusted. A real supervisor's catch rate needs human data (the dashboard has the real gate).

## Limitations

- The twin is both the world the agents observe and the verifier they use, so there is no model mismatch: verified gains are real inside the simulation by definition. Real plants would add a sim-to-real gap.
- Fault scenarios are synthetic, few (5) and chosen by the authors; ground truth is exact only because the faults are seeded. Line parameters are illustrative, not from a real plant.
- 10 seeds per cell gives wide confidence intervals; small differences are not distinguishable from noise.
- The human gate is a rule-based simulation of a supervisor (batch mode). It never errs, is never fooled by plausible text, and sees exactly the evidence defined in `docs/ASSUMPTIONS.md`.
- Fix effects are measured on 20 independent replications; a fix is 'harmful' if it lowers mean throughput by more than 1%.
- Explanation quality: the judge is an LLM judge that sees the reference label; it may favour fluent text and was not validated against the human scores. Human scores must be collected via `results/human_review_template.csv` (blind; key in `human_review_key.csv`).
- Throughput gain averages fixes over runs including ones where no fix was applied (gain 0).
