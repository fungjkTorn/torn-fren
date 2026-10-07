# Japan Xanax full-coverage signal search checkpoint — 2026-10-07

Scope: Japan Xanax only. All benchmark percentages use 100% of clean/valid opportunities after the existing provider-bounce and collector-gap exclusions.

## Clean benchmark
- strict clean P2 samples: 154
- initial history: 60 samples
- chronological evaluation: 94 valid opportunities
- Japan travel time: 149 minutes
- current preserved full-coverage exact record: about 46.8%
- current preserved full-coverage +3m record: about 55.3%

## Additional testing in this checkpoint

### Width-conditioned / residual interval policies
Tested causal interval-stabbing policies on the strong component baseline, with:
- 20/40/60/all lookbacks
- exponential decay
- current-width nearest-neighbor conditioning
- 2-bin and 3-bin width regimes
- exact, +1m and +3m training intervals

Best exact result was about 41.5%, below the preserved baseline. Rejected.

### Online regime trackers
Tested residual-state tracking using:
- EWMA
- rolling mean/median
- robust clipped EWMA
- local-level Kalman filters
- multiple cooldown/lifetime component baselines

Best exact result was about 42.6%. Rejected.

### Expert stacking
Tested expanding, strictly causal Ridge stacking over 40 diverse timer/lifetime experts and multiple target points inside the stock window.
Best exact result was about 36%. Rejected.

### Global foreign-market timing regime proxy
Built roughly 18k causal zero-to-restock events across all collected foreign items and normalized each event against that item's own prior timer history. Tested recent aggregate timing drift from:
- all countries
- Japan only
- 30m / 60m / 120m / 240m / 480m windows

Small raw correlations appeared in development slices, but adding the causal global-regime features did not improve the Japan Xanax exact benchmark. Best result stayed at or below the existing baseline.

### Timestamp / periodic timer structure
Tested whether the exact depletion timestamp predicts cooldown variation using cyclic timestamp features from 1 minute through 1 week, with Ridge, Gradient Boosting, Random Forest and Extra Trees.
All chronological tests had negative or approximately zero out-of-sample R² and worse MAE than the unconditional timer center. No usable server-clock pattern was found.

### Future G2 classification
Using only information available at the decision anchor (current width, recent widths, peak quantity, recent cooldowns, time of day, and global timing proxies), tested whether future G2 could at least be classified as early/late.
On the latest 60-cycle chronological block:
- logistic AUC around 0.39–0.50 depending on threshold
- random forest / extra trees / gradient boosting AUC around 0.42–0.44 for a 121m split
This is no better than chance and supports the conclusion that G2 has no detected pre-departure signal.

## Important no-signal oracle result
Removed G1 and L1 uncertainty entirely by giving the model the TRUE future G1 cooldown and TRUE future P1 lifetime for every evaluation case.

Then asked the most favorable possible no-signal question:
"What single G2 landing point would maximize exact arrival success over all 94 evaluation opportunities if we could see the whole evaluation set?"

Using the actual G2 values and actual target-window widths, the best possible single G2 point was:
- 45 / 94 exact = 47.87%
- best G2 landing point about 128.2 minutes

This is deliberately optimistic because:
1. G1 is magically known;
2. L1 is magically known;
3. the best G2 landing point is chosen after seeing the entire evaluation set.

Even under those advantages, a no-cycle-specific-G2-signal policy does not clear 50% exact.

A strictly causal historical-distribution version with true G1/L1 reached at most about 47.9% exact as well.

## Interpretation
The current ~46.8% full-coverage exact model is within roughly ONE successful arrival of the post-hoc no-G2-signal oracle (45/94 = 47.9%).

Therefore, further ordinary timer-center tuning is very unlikely to produce a meaningful exact-arrival gain. To break 50% at 100% valid coverage we specifically need a real, cycle-specific predictor for the FUTURE G2 timer draw before departure.

The data tested so far has not revealed such a signal.

## Product implication
Do not gate valid cycles out. Every valid opportunity should still receive:
- recommended leave time
- recommended arrival
- predicted stock window
- calibrated P(stock on arrival)
- P(+10s)
- P(+1m)
- P(+3m)
- confidence / uncertainty

The probabilities should vary by cycle instead of pretending every cycle is equally predictable.

## Next search targets
- inspect external/community implementations for any evidence of timer mechanics not represented in our features;
- continue searching for a true pre-departure G2 proxy rather than generic regression;
- calibrate the full-coverage probability surface and leave-window output;
- freeze the strongest candidate and validate on genuinely new future cycles.
