# Japan exact empirical renewal experiment

Research only. The owner journal trace as of 1792285091 contained 82 paired issues. Original sequence issued 30 forecasts; zero-handoff180 issued 33. Neither produced an eligible departure. The latter matched the original on 79/82 issues and restored three forecasts. This establishes moving/withdrawn future targets, not arrival success. Per-issued-plan target-fate counts overlap and are not independent failures. The supplied text did not include the full24 score output.

Prior one-minute cadence and common-random-number experiments failed to improve the success/coverage tradeoff and remain rejected.

## New hypothesis

A 64-path Monte Carlo estimate might miss or overstate narrow arrival windows. Compare it with full marginalization of an empirical iid cycle renewal process. This is a numerical/modeling ablation, not a promise of improved performance. The original paired-recent sampler and exact model both assume iid subsequent cycles; sequence and handoff controls retain their original sequential assumptions.

Use the last 96 completed physical-zero/restock/physical-zero tuples with a three-day recency half-life. Preserve each tuple's joint waiting, positive-stock and >=30 availability durations. Condition the first cycle on the observed current phase surviving to its current age. Require at least 16 completed cycles and four surviving analogs, as before. Borrow only the previously tested capped 180-second zero-agreement current phase. Do not synthesize phase or cross-provider training tuples.

At integer-second resolution, compute renewal mass R[0]=1 and R[t]=sum_d P(duration=d)*R[t-d]. Convolve this with the weighted single-cycle buying-availability reward using a zero-padded FFT. No cycle-boundary rounding or random seed selection. Exact means exact marginalization under this empirical model, not a calibrated real-world probability. Numerical FFT error is bounded in tests against independently enumerated paths.

Predeclare two gates: earliest support within .03 of the horizon maximum (floor .15), and earliest support >=.60. Compare original sequence, original handoff, handoff paired-recent MC peak/.60, and leave-now. Evaluate the same 864 visitor starts on the same inspected three-day development window. Preserve 300-second cadence, 15-second publication floor, 300-second forecast validity, 180-second source validity, eight-hour maximum wait, arrival quantity >=30 through +10 seconds, and true depletion exactly zero. Expose missing current-phase reasons separately.

Report known successes/failures, unknowns, pending, coverage, wait, chronological day slices and distinct departure timestamps. Reproduce original historical controls before interpreting changes. No automatic promotion. Any useful candidate needs fresh validation; inspected-day results are not independent validation.
