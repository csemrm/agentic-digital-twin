# Assumptions

Every modelling choice and parameter source. Update as phases land.

## Twin

- **Line parameters are illustrative, not copied from a paper.** The healthy line is a mildly unbalanced 5-station serial line in the style of textbook line-balancing examples (e.g. Hopp & Spearman, *Factory Physics*; Buzacott & Shanthikumar). Mean cycle times 60 / 62 / 63 / 61 / 60 s. No proprietary data.
- **Cycle times** lognormal with CV 0.25 (0.5 at station 3 in the `buffer` scenario).
- **Failures** are exponential in *operating* time (a station cannot fail while starved or blocked); repairs are exponential with mean MTTR. Healthy MTBF 7200 s, MTTR 180 s.
- **Buffers** hold 5 units in the healthy line. Blocking after service. Infinite raw material before station 1; unbounded sink after station 5.
- **Shift** is 8 simulated hours, starting from an empty line (no warm-up trimming); throughput is units finished per shift. Comparisons share this ramp-up, so it cancels in gain calculations.
- **Randomness**: independent seeded streams per station and purpose, so two configs run with the same seed share common random numbers.

## Scenarios and ground truth

- `healthy`: no fault, truth `None`.
- `slow_station`: station 2 at 95 s. Truth station 2.
- `breakdowns`: station 4 MTBF 900 s / MTTR 300 s. Truth station 4.
- `buffer`: buffer after station 2 capacity 1, station 2 fails often (MTBF 1500 / MTTR 360), station 3 CV 0.5. Truth is the station that **owns** the undersized buffer (station 2), fault type `buffer`.
- `mixed`: station 4 MTBF 800 / MTTR 400 (primary) plus station 2 at 75 s (secondary). Truth station 4, chosen because it has the lowest analytic effective capacity; tests assert this.
- Analytic effective capacity = cycle time / availability, availability = MTBF / (MTBF + MTTR). It ignores buffering effects, so it is only used to label slow-station, breakdown and mixed scenarios.

## Action constraints (safety layer)

- `AddBuffer`: stations 1..4, adds 1..5 slots, total capacity capped at 12.
- `RebalanceTask`: adjacent stations only, fraction in (0, 0.30]; moves `fraction x` the source station's mean cycle time to the destination (total work conserved).
- `ChangeMaintenance`: only stations with a failure model; `mtbf_multiplier` in [1, 2], `mttr_multiplier` in [0.5, 1] (improvements only, no-ops rejected).
- These limits are illustrative engineering bounds, not derived from a real plant. Anything outside the pydantic schema (unknown type, extra field, wrong type) is rejected with a logged reason.

## LLM layer

- Default model `claude-haiku-5-5` (override with `LLM_MODEL`). Mode is `mock` unless `ANTHROPIC_API_KEY` is set (or `LLM_MODE=real` is forced). No sampling parameters are passed; determinism across reruns comes from the on-disk cache keyed by (model, system prompt, user prompt).
- Mock mode uses scripted, rule-based role handlers and character-based token estimates (about 4 chars/token). **Mock results exercise the pipeline; they say nothing about real LLM quality** and are labelled as mock everywhere.
- A "step" is one LLM call, including cache hits and JSON repair re-asks. Tokens from cache hits are still counted (what a fresh run would spend).
- Retries: exponential backoff (1, 2, 4, 8 s) on rate-limit, connection and 5xx errors; one repair re-ask on invalid JSON.

## Agents and gate

- Agents observe one simulated 8 h shift. They see engineered standard cycle times and current buffer capacities, but not the scenario label, MTBF/MTTR settings, or ground truth. "Normal output" (reference throughput) is the healthy line's mean over 5 fixed seeds.
- Mock diagnosis uses *active period* bottleneck detection (highest busy + down fraction). Fault type rules: slow if measured cycle >= 1.15x standard, breakdowns if down >= 8%, buffer if buffer after the station <= 2 and it is blocked >= 5%, mixed if a second station also shows a fault signal. Output within 5% of reference counts as "no fault".
- Mock candidate generator proposes the natural remedy first. On every 4th seed (first round only) its first proposal is deliberately over-aggressive, so the validator path is exercised. This is a test device, not evidence about LLMs.
- Simulation agent: 8 replications on seeds 1000..1007, paired with the unmodified line; pass = mean gain >= 2% and one-sided paired t-test p < 0.05.
- Gate loop cap: 3 diagnosis rounds. A round with no verified fix also counts toward the cap, and re-diagnosis skips stations previously found unfixable.
- `SimulatedApprover` sees only presented evidence. With twin evidence it approves iff gain >= 2%. Without evidence (ablation, single agent) it can only check constraint validity, so a harmful-but-valid fix is approved. Injected bad recommendations are either invalid (buffer after the last station) or harmful (move 30% of a neighbour's work onto the diagnosed bottleneck). A real supervisor would be noisier; this is a stated limitation.

## Baselines

All six systems face the same gate, the same typed-action validator and the same 3-round cap. All act only on a >= 5% throughput drop, so a healthy line is not penalised for a false alarm.

- **Rule-based**: bottleneck = highest utilization (busy fraction only, ignoring downtime). Fix = add 3 buffer slots after it (before it if it is the last station). One gate round, no LLM. A deliberately naive floor.
- **TOC heuristic** (`toc_heuristic`, classical comparator): Theory-of-Constraints rules on the observed KPIs only. Constraint = station with the highest utilization + downtime. If its measured cycle time is > 1.15x standard: rebalance 20% of its work to the less-active adjacent station. Else if it is down > 8% of the shift and has a failure model: `change_maintenance` (MTBF x1.5, MTTR x0.75). Else: add 3 buffer slots before it (after it if it is station 1). No twin, no LLM, one gate round, unverified. Thresholds were fixed a priori and not tuned on the scenarios; it misreads the `buffer` scenario as a breakdown problem, and that is reported as is.
- **Twin search** (`twin_search`, brute-force comparator): no LLM and no diagnosis. Enumerates a coarse grid of every action the validator allows (buffer sizes 1/3/5 after each station; rebalance fractions 0.1/0.2/0.3 in both directions between adjacent stations; five MTBF/MTTR multiplier pairs per station with a failure model), tests each with the Simulation agent's own paired-replication test (same `n_reps`, 2% gain threshold, alpha 0.05), and offers verified fixes best-first to the gate, up to the round cap. No multiple-comparison correction is applied, matching the pipeline; scoring uses independent seeds, so lucky winners show up as ineffective fixes. Its "diagnosis" is only the station its best fix targets (fault type `unspecified`, excluded from type accuracy), so its station accuracy is incidental. Cost is reported as `twin_sims` (n_reps x (1 + grid size), about 496 per fault-line run); the search result is memoised per config, but the reported cost is the uncached one. The twin is the same simulator that scores the fix, with different seeds, so there is no sim-to-real gap for this baseline either.
- **Single agent**: one `single_agent` call returns diagnosis plus one typed action; no simulation. It receives validator and gate rejections as feedback (extra LLM step each) and may retry up to the cap.
- **Multi-agent without simulation** (ablation): the full graph with the Simulation node replaced by "take the first constraint-valid proposal, unverified".
- In mock mode the single agent and the multi-agent roles share the same diagnosis and proposal heuristics, so mock differences come only from pipeline structure (verification, retries), not from different "intelligence".

## Evaluation metrics

- Two experiments over the same grid (4 systems x 5 scenarios x N seeds, observation seeds 1..N, default N=10): `clean` (approver never injects) answers RQ1 and RQ2; `stress` (approver injects a bad recommendation with probability 0.5 per review) answers RQ3. Injection draws are seeded per (scenario, seed) and identical across systems, so systems face the same injections.
- **Bottleneck accuracy**: station of the *first* diagnosis equals the seeded station; on the healthy line, correct means reporting no fault. Fault-type accuracy accepts `breakdowns` or `slow_station` for a `mixed` scenario; the rule-based baseline gives no type (excluded).
- **Throughput gain**: mean throughput of the final config vs the scenario config over 20 independent replications (seeds 2000..2019, disjoint from the Simulation agent's 1000..1007 and the observation seeds); 0 when nothing is applied. Reported as a mean over runs, so no-action runs pull it down.
- **Invalid/harmful-fix**: a non-injected recommendation that reached the gate is invalid (breaks schema or constraints) or harmful (independent gain below -1%). **Ineffective-fix**: an applied fix with independent gain below 2%.
- **Gate catch rate**: among gate reviews of bad recommendations (invalid or harmful by the independent evaluation, injected or not), the share rejected. Computed in the stress experiment only.
- **Steps/tokens**: from the usage meter (judge calls excluded).
- **Explanation quality**: judge scores the first diagnosis's explanation on correctness, evidence and clarity (1-5, overall = mean). Judge sees the reference label. Mock mode uses a lexical rubric. The human template (`results/human_review_template.csv`) is blind (shuffled; system names only in `human_review_key.csv`), 2 seeds per system-scenario cell.
- CIs: Wilson for proportions, t-interval for means, paired bootstrap (2000 resamples) for differences between systems on shared (scenario, seed) pairs over the 4 fault scenarios.

## Validation tolerances

- The capacity-bound test allows 3% over the analytic bound, since the bound is an expected rate and the test averages only 8 replications.
- The Little's law test uses a 40-shift run and 5% relative tolerance (the line starts empty and ends with parts in flight).
