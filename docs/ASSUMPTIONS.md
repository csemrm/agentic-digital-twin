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

## Validation tolerances

- The capacity-bound test allows 3% over the analytic bound, since the bound is an expected rate and the test averages only 8 replications.
- The Little's law test uses a 40-shift run and 5% relative tolerance (the line starts empty and ends with parts in flight).
