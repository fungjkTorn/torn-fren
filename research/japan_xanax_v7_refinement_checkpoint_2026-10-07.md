# Japan Xanax continued V7 refinement checkpoint — 2026-10-07

Scope: Japan Xanax only. 100% valid-opportunity coverage.

## Continued reconstruction refinement
The observation-lag result was extended by estimating not only the hidden restock start, but also the true depletion/zero timestamp from each stock trajectory. Robust Theil-Sen zero-time reconstruction was compared with OLS and Huber variants.

The best stable causal candidate retained:
- corrected stock-start labels from the 2500-unit reconstruction
- robust reconstructed depletion timestamp
- 40-cycle trimmed cooldown center
- historical mean lifetime
- last-10 fully resolved residual correction at 50% shrinkage
- +60 second landing adjustment

Fixed benchmark:
- 154 strict clean P2 samples
- first 60 burn-in
- 94 chronological evaluation opportunities
- 100% valid coverage

Performance:
- exact arrival: 51/94 = 54.3%
- +10 seconds: 52/94 = 55.3%
- +1 minute: 53/94 = 56.4%
- +3 minutes: 58/94 = 61.7%

First 47 evaluation opportunities:
- exact: 55.3%
- +3m: 61.7%

Later 47:
- exact: 53.2%
- +3m: 61.7%

Four chronological exact blocks:
- 50.0%
- 60.9%
- 45.8%
- 60.9%

So the >50% full-coverage result survives the later half, though one smaller internal block remains below 50%.

## Additional model families tested after the breakthrough
- residual Ridge regression over 55 causal timing/width/lag features
- gradient boosted residual models
- causal empirical interval optimizer
- width-nearest interval optimizer
- several robust depletion estimators (OLS / Huber / Theil-Sen)

None materially beat the simple causal reconstructed-mechanics model. Ridge/boosting generally reduced exact accuracy into the 30-40% range. The empirical interval optimizer was unstable across halves.

This reinforces that the main gain came from fixing measurement bias, not from model complexity.

## Probability calibration finding
Naive rolling empirical confidence estimates are badly miscalibrated: higher estimated confidence buckets can perform worse than lower buckets. Therefore the website must NOT expose those raw empirical percentages yet.

Before showing per-flight percentages, calibration must be trained separately from timing selection and verified chronologically.

## Leave-window finding
A first-pass empirical near-optimal +3m leave-window estimator produced a median window around 1.5 minutes, but this is not production-ready because the same raw empirical probability model is miscalibrated.

## Current preserved benchmark
100% clean coverage:
- exact 54.3%
- +10s 55.3%
- +1m 56.4%
- +3m 61.7%

Next:
1. improve/reconstruct ground truth conservatively;
2. calibrate probabilities without changing the timing model;
3. freeze the timing model before future validation;
4. validate on genuinely new cycles;
5. then integrate leave time / arrival time / calibrated probabilities into the graph.
