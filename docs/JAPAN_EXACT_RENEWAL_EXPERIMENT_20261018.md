# Japan exact empirical renewal experiment

Research only. The owner journal trace as of 1792285091 contained 82 paired issues. Original sequence issued 30 forecasts; zero-handoff180 issued 33. Neither produced an eligible departure. The latter matched the original on 79/82 issues and restored three forecasts. This establishes moving/withdrawn future targets, not arrival success. Per-issued-plan target-fate counts overlap and are not independent failures. The supplied text did not include the full24 score output.

Prior one-minute cadence and common-random-number experiments failed to improve the success/coverage tradeoff and remain rejected.

## New hypothesis

A 64-path Monte Carlo estimate might miss or overstate narrow arrival windows. Compare it with full marginalization of an empirical iid cycle renewal process. This is a numerical/modeling ablation, not a promise of improved performance. The original paired-recent sampler and exact model both assume iid subsequent cycles; sequence and handoff controls retain their original sequential assumptions.

Use the last 96 completed physical-zero/restock/physical-zero tuples with a three-day recency half-life. Preserve each tuple's joint waiting, positive-stock and >=30 availability durations. Condition the first cycle on the observed current phase surviving to its current age. Require at least 16 completed cycles and four surviving analogs, as before. Borrow only the previously tested capped 180-second zero-agreement current phase. Do not synthesize phase or cross-provider training tuples.

At integer-second resolution, compute renewal mass R[0]=1 and R[t]=sum_d P(duration=d)*R[t-d]. Convolve this with the weighted single-cycle buying-availability reward using a zero-padded FFT. No cycle-boundary rounding or random seed selection. Exact means exact marginalization under this empirical model, not a calibrated real-world probability. Numerical FFT error is bounded in tests against independently enumerated paths.

Predeclare two gates: earliest support within .03 of the horizon maximum (floor .15), and earliest support >=.60. Compare original sequence, original handoff, handoff paired-recent MC peak/.60, and leave-now. Evaluate the same 864 visitor starts on the same inspected three-day development window. Preserve 300-second cadence, 15-second publication floor, 300-second forecast validity, 180-second source validity, eight-hour maximum wait, arrival quantity >=30 through +10 seconds, and true depletion exactly zero. Expose missing current-phase reasons separately.

Report known successes/failures, unknowns, pending, coverage, wait, chronological day slices and distinct departure timestamps. Reproduce original historical controls before interpreting changes. No automatic promotion. Any useful candidate needs fresh validation; inspected-day results are not independent validation.

## Completed result: reject both challengers

Private run 39089615803 / job117563363824, source49d233a2d084d6d2b49f9c3b6a174a0a43c58147. Both original control fingerprints reproduced exactly. Comparison finished in25.84sec. Artifact12122680287, ZIP SHA256 e74b07519a1e45e64470071cf653d718f4256b397f3b74585701c3f450ea562a, independently verified after download. Sanitized sealed snapshot SHA25616473276a10693339bf1a12b9a7e41fa9af2e3be98b490b82fb5c6aec176322c.

| Model | Success/known | Unknown | Departure coverage | Mean wait, min | Distinct departures |
|---|---:|---:|---:|---:|---:|
| Original sequence |391/467 (83.73%)|0|54.05%|201.3|13|
| Original handoff180 |518/659 (78.60%)|0|76.27%|192.6|21|
| Paired MC peak, handoff phase |279/757 (36.86%)|0|87.62%|176.1|24|
| Paired MC .60, handoff phase |128/328 (39.02%)|0|37.96%|224.1|6|
| Exact iid renewal peak |364/731 (49.79%)|97|95.83%|150.4|33|
| Exact iid renewal .60 |0/0|0|0%|—|0|

Exact peak improved over the iid MC peak but was much worse than the sequence/handoff incumbents, with97 unknown outcomes (11.23% of all864 starts). Its chronological-day known success was56.80%,71.64%,24.74%; coverage92.01%,95.49%,100%. Exact .60 never produced an executable departure. No promotion. The iid-cycle assumption remains too diffuse/unreliable at Japan's flight lead; removing sampling variance does not solve prediction. Do not claim the model is impossible in general.

The curve had known-phase support on575/864 issues and no current phase on289. Only five unique completed-history kernels were used over the whole replay plus8h followup. That is diagnostic of this strict accepted training representation, not a count of actual restocks.

## Full-roster journal hardening

Future records store source cutoff and issue-time poll age, reject an entire atomic frame when its source expires before publication, and keep true depletion0. Scoring validates metadata versus record identity and expected source SHA, freezes one truth cutoff for all items, explicitly counts legacy rows with no source clock, and optionally emits per-item loading progress to stderr (--progress). Frozen scoring remains available for older journals. Old missing clocks are never reconstructed as facts. This does not update running owner recorders or activate production changes.
