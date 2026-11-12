# Complete historical stock paths — October14 evening,2026

Three fixed arrival-only challengers use full historical stock trajectories instead of chaining marginal stocked/empty duration quantiles. Physical phase features use positive stock versus exactly0. Buying eligibility remains>=30; below30 never starts a physical restock timer.

## Model

research/causal_stock_paths.py constructs clock-selected half-hour historical starts, capped4096. Each outcome trajectory spans an8h departure-wait grid (120s bins) plus the country flight and190s evidence allowance. Repeated absolute arrival evaluations are cached. Every eligible path's full horizon must finish BEFORE the current issue; the final replay cutoff never substitutes for that per-issue maturity gate.

Features at each start use only preceding rows: physical phase, phase age, actual quantity, recent8 completed positive/zero duration medians, and cyclic UTC time. Initial unbounded phases, stale contexts or missing or stale successful-poll evidence do not supply training starts. Fixed feature scales, no future-fitted imputation/scaling. Most recent512 eligible starts, same physical phase. recent70 uses all those paths equally; analog70/analog80 use up to32 nearest conditions weighted exp(-sqrt(distance)).

A departure needs>=16 known outcomes and>=80% known path weight at that delay. Weighted available fraction is smoothed across adjacent120s bins and capped at its central value; choose first grid point reaching0.70 or0.80. These thresholds are uncalibrated scenario support, NOT expected success probabilities. Unknown path arrivals stay unknown. Completed horizon does not imply every sampled outcome was observable.

Path choices are evaluated under the SAME five-minute replanning,180s source expiry and8h maximum-wait protocol. Higher reported success with inadequate departure coverage or perpetual postponement fails the research objective.

## Comparison

Full mode retains40 policies. New --focused-zero mode retains23: V166 comparator, all physical-zero/hybrid policies, the existing unpromoted selector, and three path policies. It skips unused V151 Monte Carlo and legacy template flight simulations. Tests assert retained policy outcomes and counts match full mode exactly; all24 items still run. Legacy event-timing audits remain available. The old readiness shortlist cannot be compared to a full tournament when policies are intentionally omitted; no new policy enters its whitelist.

New path policies are compared on the same hourly starts against zero_anchored_current_quarter AND separately zero_rate_current_quarter and zero_hybrid_current_rate_current_quarter. This includes prior promising RedFox/Panda components and strong-item rate references, rather than claiming a gain only against a weak baseline. Inspect daily outcomes, unknowns, coverage, matched wins/losses and wait; do not select retrospective winners as prospective rates.

## Separate departure and timing models

The path planner predicts departures only. Physical-zero event forecasts remain reference context in its journal; event_timing_prediction_supported=false in path evidence, departure_only_model=true in its report, no per-policy next-tick event timing claims. Its selected event index is null. It does NOT acquire restock/depletion accuracy by borrowing the reference forecaster.

## Verification and scope

Tests check path horizon maturity at every issue, future mutation invariance, same earlier predictions under a shorter dataset cutoff, residual1–29 remaining physically positive, unknown/stale abstention, full/focused outcome parity, and full journal future perturbation. Existing browser/service checks remain.

Offline precomputation reads future rows only for future COMPLETED training trajectories. Those rows are inaccessible to earlier queries via the strict path-end eligibility bound; tests verify that boundary. No forecast uses its own future outcome.

Research only, no live model assignment or production writes. This history overlaps previously inspected experiments; it is not a pristine holdout or actual player-flight proof. Fresh forward validation remains required.
