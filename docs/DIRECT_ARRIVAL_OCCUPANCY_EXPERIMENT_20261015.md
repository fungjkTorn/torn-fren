# Direct arrival occupancy experiment

The last two new model families failed to improve Japan. Correcting a future
cycle clock did not reliably identify its short buying windows after a long
flight. This motivates a different supervised target, rather than another
offset or an untested ensemble of those rejected candidates.

This experiment fits a per-item, regularized logistic model directly to
poll-backed stock >=30 at flight-plus-wait horizons. It predicts no depletion
or restock event times. Physical phase remains positive versus exactly zero;
quantity 1–29 never starts the restock timer.

Fixed design before this run: hourly historical origins; training horizons
every 15 minutes from the item's flight time to flight+8h; trailing 21-day
history; seven-day recency half-life; equal total weight per origin; ridge
penalty 3; refit on canonical six-hour boundaries. Each outcome is eligible
only after its individual arrival plus 190 seconds. Inputs are observed
physical phase and age, stock quantity and batch fraction, completed cycle
summaries, horizon interactions, three periodic cycle harmonics and arrival
time of day. All normalization uses only eligible training rows.

Historical training precedes the issue evaluation window. The coefficients
are reconstructed from mature history at each refit, independently of replay
start, avoiding the previous correction learner's empty-window initialization.
Offline label arrays are not accessible to prediction until their maturity
gate passes. Unknown arrival evidence never becomes a negative training label.

Two fixed departure policies: earliest five-minute departure scoring at least
0.70; and a diagnostic peak policy taking the earliest departure within 0.02
of the maximum score, with a 0.15 floor. These scores are **uncalibrated**.
Neither gate is a promised success rate. No hyperparameter search on the
reported evaluation period and no automatic promotion.

Evaluate the eight weak items using the same snapshot and all five-minute
start cohorts as established references. Compare paired outcomes, coverage,
waits, all UTC offsets, day floors, pending/unknown counts, and as-issued
versus replanned decisions. Hourly training origins and five-minute evaluation
cohorts remain correlated; they are not independent flights. This is exploratory
historical reconstruction, not fresh-data confirmation or purchases.

The existing frozen forward protocol keeps its original source and window.
The new model is excluded from that already-declared protocol. The targeted
experiment uses a separate private request/workflow and research snapshot;
production and normal approved-source selection remain unchanged.

After the first run rejected a general replacement, an execution ablation was
added for rate, hybrid and both direct policies: take the first healthy
proposal within the same eight-hour deadline, freeze that departure clock,
and refresh heartbeat health at departure. Later model advice is deliberately
ignored; stale departure evidence cancels the commitment. Compare this
counterfactual with replanning on identical five-minute starts, including
paired wins/losses and waits. This is a diagnostic of execution sensitivity,
not permission to recommend ignoring fresh stock data. It does not retrain
or change coefficients, thresholds, or existing departure policy behavior.
