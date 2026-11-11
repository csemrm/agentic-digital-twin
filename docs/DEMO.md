# 5-minute demo script

Setup (before the audience arrives): `make setup && make test`, then `make dashboard`. Mock mode is fine; say so out loud.

## 0:00 The idea (30 s)

"A five-station line makes about 410 units a shift when healthy. When something degrades, an AI team diagnoses it, but **nothing reaches you until the digital twin has shown the fix actually raises output**, and nothing is applied without your click. Verify before act."

Point at the sidebar architecture diagram: Monitor, Diagnosis, Simulation, you.

## 0:30 Healthy baseline (30 s)

Scenario `healthy`, seed 1, **Start run**. Outcome: `no_fault`, no gate. "Agents don't invent problems."

## 1:00 A real fault, the happy path (90 s)

Scenario `breakdowns`, seed 1, **Start run**.

1. KPI panel: throughput is well below normal. In the station split, station 4 has a large "down" share.
2. Findings: Monitor flags high downtime. Diagnosis names station 4 / breakdowns with its reasoning and confidence.
3. Candidate table: each fix was run over 8 seeded replications against the unmodified line. Show before/after units/shift, gain %, confidence interval and p-value. Only rows with `passes = True` can be recommended; the best one goes to the gate.
4. Gate: the top fix and its twin evidence. Click **Approve**. Outcome shows the applied typed action and the before/after throughput on fresh seeds.

## 2:30 Rejection loop (60 s)

Start `breakdowns` again. This time click **Reject**. The graph goes back to Diagnosis ("round 2"), proposes a different fix (the rejected one is excluded), simulates it and returns to the gate. Mention the cap of 3 rounds.

## 3:30 The safety layer (45 s)

Scenario `slow_station`, **seed 4**. In the candidate table, point at the row marked `valid = False`: the agent's first proposal was over-aggressive (`add_buffer` size 9) and the validator rejected it with the reason shown in the `note` column, so it was never simulated or recommended. "LLMs can propose unsafe things; the typed schema is a hard wall." (The same rejection is written to the console log and to `action_rejections` in the run record.)

## 4:15 No simulation (30 s)

Untick "Simulation agent on", start `slow_station`. The gate shows a warning: **No twin evidence.** "This is the ablation behind RQ2: without verification, the supervisor has only the agent's word."

## 4:45 Evidence (15 s)

Open `results/summary.md` and `results/plots/gain_pct.png`: every number comes from `make run-experiments`. State plainly which mode produced them and read the Limitations section.

## Likely questions

- *Is the LLM real?* In mock mode no; set `ANTHROPIC_API_KEY` and `LLM_MODE=real` for a real model. Cached, so rerunning is cheap.
- *Why trust the twin?* The twin is also the world here, so there is no model mismatch; that is a stated limitation.
- *What does the gate catch?* See the stress experiment in `summary.md` (RQ3) and the caveat that the batch approver is simulated.
