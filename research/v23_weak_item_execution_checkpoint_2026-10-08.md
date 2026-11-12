# V23 weak-item research checkpoint — 2026-10-08

Status: **offline-only exploratory research; no production routing, no live model promotion.** Other chat continues flower/plushie specialists independently.

## Data and method
Original frozen DB SHA256 `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`; newer VM DB SHA256 `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`; old cutoff 1791241486. Qty >=30 at arrival or within 10 seconds, fixed country flight durations, provider bounce suppression, collector gap censoring, full 12h horizon observable.

V23 configurations selected on an older chronological middle period before the newer VM evaluation. Nevertheless, this newer VM data was previously examined in V22 research: **these are exploratory results, not untouched prospective trials**. Half-hour test sessions are correlated.

## A. Multi-cycle arrival bootstrap — generally underperformed
Used fully resolved past restock intervals and stock lifetimes to simulate several future qualifying windows (192 simulations per decision), then selected earliest leave time close to best uncalibrated historical stock-arrival score. Confidence is NOT calibrated and must not be shown as a personalized percentage.

| Item | V23 bootstrap | V22 static analog | Depart now |
|---|---:|---:|---:|
| Argentina Tear Gas | 9/70 (12.9%) | 13/70 (18.6%) | 10/70 |
| China Fireworks | 7/67 (10.4%) | 32/67 (47.8%) | 12/67 |
| Japan Kabuki Mask | 30/69 (43.5%) | 36/69 (52.2%) | 30/69 |
| Japan Sumo Doll | 34/69 (49.3%) | 36/69 (52.2%) | 31/69 |
| China Katana | 22/69 (31.9%) | 47/69 (68.1%) | 23/69 |
| Canada Fire Hydrant | 46/64 (71.9%) | 58/64 (90.6%) | 26/64 |
| Argentina Chalcedony Point | 43/70 (61.4%) | 42/70 (60.0%) | 21/70 |
| Hawaii Basalt Point | 41/71 (57.7%) | 40/71 (56.3%) | 22/71 |

This method produced no robust improvement over V22; **do not promote**. Complex recurrent timing cannot be modeled well by independently bootstrapping a fixed history of intervals without a better regime/state representation.

## B. Current stock survival gate — all 41 weak items tried
Uses prior completed stock-window lifetime distributions to decide whether *current qualified stock* is likely to survive the player's flight. On the newer VM sample, 37 of 41 items had >=30 scorable decisions:
- **3 improved:** Tear Gas 14/70 versus V22 13/70; **Sumo Doll 40/69 (58.0%) versus 36/69 (52.2%)**; Argentina Compass 18/70 vs 16/70.
- **3 worsened:** Fireworks 28/67 vs 32/67; Kabuki Mask 34/69 vs 36/69; Katana 44/69 vs 47/69.
- **31 tied** the frozen V22 outcomes exactly.

Thus Sumo Doll is a promising *selective* challenger, not proof of a generally better policy.

## C. Fundamental stock event semantics
For stock target >=30, a quantity crossing 29 -> 30 is indeed a qualifying opportunity, but may not be a genuine substantial replenishment:
- **China Katana: 130** qualifying >=30 crossings; **88 (67.7%)** involved increases under 10 units.
- **China Fireworks: 71** qualifying crossings; only **3 (4.2%)** under 10 units.
- UK Frying Pan: 8 of 10 qualifying crossings under 10 units, low sample.

A >=10-unit jump is a provisional heuristic, NOT a known Torn restock API contract. We must distinguish **next qualifying availability** from **substantial stock restock** in the website. An alternate bootstrap based on substantial events also underperformed; don't promote.

## D. Offline two-layer integration proof
An experimental preview combines separate models into:
1. Current observed quantity and (when below target) next qualifying restock estimate/window; separately annotated uncalibrated and collection-quality requirements.
2. Best-effort recommended departure and corresponding arrival by a frozen V22 analog config, plus separate stock survival estimate when possible. No calibrated per-trip success probability is emitted.

For Argentina Tear Gas, the *next qualifying restock* can arrive within minutes while the recommended flight departure leads to an arrival multiple future restock cycles later. These outputs cannot be conflated. Example offline output stored in research ZIP. No website V2 route changed; V2's 2nd-cycle projection must be preserved. A stock change timestamp is NOT proof the collector is fresh; actual poll heartbeat required.

## Research tests
**9 local unit tests pass:** past/future truncation invariance, multicycle output bounds, no unresolved future lifetimes used, gap logic, arrival=departure+flight, never publishing fake calibrated confidence, restock-window point ordering, and no invented next qualifying restock while already stocked.

## Next steps toward controlled deployment
- Keep all V19–V22 selected configs and V2 website restock predictor as incumbents.
- For V23, research only: no global champion promotions; perhaps selectively shadow the Sumo Doll survival gate after further independent data.
- Implement an exact frozen **V19/V20/V21 champion shadow replay on new timestamps** to compare fairly with V22 and eventual V23 (not just depart-now). Check causality of historical feature resolution and avoid previously viewed holdout-based promotional claims.
- Make stock event classification explicit. Validate next drop MAE, window coverage *and width*, second/reachable drop, depletion survival separately from arrival success.
- Distinguish natural long waits from avoidable missed opportunities. Longer than 12h must be a forecast out-of-horizon state, not a failed prediction.
- Finish registry, collector freshness, API contract, opt-in shadow flag, tests and rollback before enabling public routing.

## Artifacts
ChatGPT generated `torn_fren_v23_weak_item_checkpoint_2026-10-08.zip` containing reproducible Python modules, example dual-layer payload, JSON results and tests, plus full local report `V23_Weak_Item_And_Dual_Layer_Checkpoint_2026-10-08.md`. Scripts are **not yet committed in executable form to GitHub**. This document is the durable repo checkpoint.
