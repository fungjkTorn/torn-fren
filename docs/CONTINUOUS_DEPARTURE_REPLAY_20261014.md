# Every-issued departure evaluation — October 14, 2026

The three-page product contract remains `TORN_FREN_PRODUCT_MASTER_BLUEPRINT_20261013.md`: preserve original V2 graph, preserve/expand experimental board, add Travel Decisions. This change is research code and private runner evaluation; no production routes, services, collector or incumbent models were changed.

## Completed

`research/continuous_departure_replay.py` reconstructs every five-minute issue independently of future events. It runs V163 event histories through the V166 player flight adapter, retains all future events (including unreachable ones), freezes chosen departure and arrival, and scores subsequent poll-backed delta stock. It records abstention, success, failure, pending and unknown, immediate-departure comparisons, first proposals per known issue phase, distinct observed stock episodes reached, and short-lead restock counts in nonoverlapping next-tick slices. Short-lead slices are a different protocol from four-hour forecasts; their timing counts must not be presented as long-lead travel accuracy.

Arrival evidence requires successful polls bracketing arrival through ten-second grace, bounded poll lags, no collection gap, consistent item provider, and stable threshold status across **all** recorded changes in the bracket. An unchanged item delta is valid between healthy polls. Hidden depletion/replenishment between equal endpoints is UNKNOWN. Sanitized heartbeats omit upstream provider identity and per-country feed timestamps: these remain sampled availability proxies, not exact-second game truth or successful purchases.

Snapshot cutoff is read inside the same read-only SQLite transaction as observations. Future observations cannot change earlier choices, checked by a regression that mutates later stock and compares earlier frozen forecasts. Every run stores its complete private issue journal and model SHA, not the raw database. Source files are public; outcome artifacts stay private.

## First empirical run

Source `2a795780f7f72be7a7c7516e368d4a9170f52309`; public causal/unit CI [38503168634](https://github.com/fungjkTorn/torn-fren/actions/runs/38503168634) passed. Private [38503253941](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38503253941) succeeded, using 480,153-row snapshot cutoff 1791944970. Two days, 24 items, 13,824 issues per policy:

| Fixed policy | Success / resolved arrivals | Proposal coverage | Pending | Unknown |
|---|---:|---:|---:|---:|
| V166 median earliest | 7,922 / 11,223 = 70.59% | 89.61% | 668 | 497 |
| Midpoint all history | 8,026 / 10,849 = 73.98% | 89.61% | 1,046 | 493 |
| Midpoint recent 8 | 8,151 / 10,817 = 75.35% | 88.31% | 946 | 445 |
| Late onset all history | 6,862 / 8,663 = 79.21% | 70.10% | 688 | 339 |

These denominators differ. The larger late-onset percentage partly selects fewer opportunities; it is not proof of universal superiority. Repeated five-minute issues are correlated and planned WATCH trips are frozen, not re-confirmed executions. No 90% claim or production promotion is justified.

Jaguar median 336/497=67.61%, midpoint 434/505=85.94%; Nessie median 310/484=64.05%, midpoint 285/481=59.25%. Japan Xanax median 165/429=38.46%, midpoint 170/505=33.66%, recent-8 midpoint 185/473=39.11%; late onset abstained entirely. Buffering helps some items and harms others. Preserve item specialists rather than replace them globally.

## Follow-up implemented

Add a quarter-stock-window buffer to test a smaller delay, matched challenger-versus-V166 issue comparisons, and chronological 24-hour slices per item. Known collection outages at issue now suppress proposals even if a global heartbeat exists. Keep these fixed candidate policies and assess the second day separately; the repeatedly inspected history is not a pristine lockbox.

## Next gates

1. Review matched wins/losses and coverage per item and day, alongside waits and unknowns. Do not pick a router from its own evaluation outcomes.
2. Add genuine causal incumbent-specialist/V151 comparison after adapting their input contracts and benchmarking cost. They are **not evaluated by this replay yet**.
3. Assess current-stock-window opportunities (V166 currently derives future restock events), WATCH re-confirmation/execution and earliest credible calibrated policies.
4. Continue event-model improvements, especially Nessie and Japan, with chronological training and fresh forward evidence. Historical reconstruction is not genuine prospective capture.
5. Add the shared cached read-model for all three pages; inspect deployed source drift before any production integration. No new systemd installation is needed for routine GitHub tests.
