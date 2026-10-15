# Inventory feature ablation on complete historical stock paths

The previous cycle-regression family improved timing errors but generally failed to improve useful arrival outcomes. This experiment instead conditions observed future stock paths on currently available inventory information. No new batch sizes or repeated future cycle medians are invented.

Three fixed feature groups use the same historical origins and arrival labels:

| Group | Inputs |
|---|---|
| phase | Physical positive/zero phase, phase age, recent completed positive/empty durations, daily sine/cosine |
| quantity | Phase inputs plus current absolute quantity, fraction of observed batch remaining, observed batch size relative to recent observed restock batches |
| flow | Quantity inputs plus completed historical stock-decline rate, supported current rate adjustment, current-rate support flag, estimated positive-stock and ≥30 residual duration |

These are sampled inventory decline rates, not verified purchases. The current-rate adjustment uses the established quantity-rate tracker: at least three drops spanning at least three minutes within the last ten minutes, no last quantity update older than 180 seconds, same-provider uninterrupted segment, fixed shrinkage/caps. Provider changes, positive top-ups and collection gaps reset the current segment. Historical completed rates may still provide a labeled fallback. Quantities 1–29 remain physically positive; only exact zero starts the empty/restock clock.

For each issue, consider the last 512 eligible half-hour historical origins, matched on physical positive/zero state. The entire eight-hour wait plus standard flight and 190-second outcome allowance must already have matured before issue. Each group selects the nearest 32 paths using feature scales fitted only to those eligible past origins (IQR floor 0.25; scaled distances clipped to ±8). Thus feature groups hold path pool, neighbor count, scale method and departure rule constant. No future labels or current final-period normalization enter selection.

For each group, test two fixed departure policies: first supported departure-bin score ≥0.70; and a diagnostic near-peak policy with 0.15 floor and earliest score within 0.03 of the eligible peak. The inherited grid is 120 seconds, with adjacent-bin smoothing, at least 16 known paths and 80% known weighted mass. All scores are uncalibrated. No peak result is accepted without its coverage/wait costs.

Six policies run on all eight weak items plus Jaguar and Peony controls. Primary feature comparisons are quantity70 versus phase70 and flow70 versus quantity70. Also compare all six against existing rate, hybrid, local, regime, aligned and residual references on the same snapshot. Preserve success/failure/UNKNOWN/PENDING/ABSTAIN, all five-minute starts pooled, twelve UTC-minute offsets, UTC hourly, chronological slices and matched outcomes. Starts are correlated, not independent flights. Existing best-item references must stay visible even if the new ablation control is weaker.

This is exploratory historical reconstruction. New policies have no supported restock/depletion event forecast accuracy and do not inherit those metrics from the zero forecaster used in the replay plumbing. No production change, automatic model promotion or change to the original or separately frozen Chamois forward protocols is authorized by a good historical result. Any useful new candidate needs subsequent fixed validation.
