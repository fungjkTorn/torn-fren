# Player decisions and per-item research — October 14, 2026

## What is built

An additive `/travel-decisions` page and `/api/travel-decisions` endpoint now exist on the research branch. Both are disabled unless `TORN_FREN_TRAVEL_DECISIONS_BETA=1`. They do not replace `/`, `/experimental`, or the existing APIs. **Not deployed to the production VM.** The actual deployed application differs from this branch; never copy research `web/app.py` over production.

The UI provides item/country/category search, sorting, browser-local watchlists, personal outbound flight minutes, departure countdown, actual landing clock, latest modeled departure, observed quantity, all projected restocks including unreachable ones, uncertainty bands and links to the original V2 graph. Research results are labeled historical; no calibration or purchase guarantee is invented. No API key is collected.

`services/travel_read_model.py` reads a bounded precomputed event snapshot, caches by inode/mtime/size, and applies `services/travel_window_policy.py` cheaply per item and player. No simulations or collector database reads happen in this endpoint. Bound is 250 items, 16 MiB snapshot; UI displays 50 rows at a time. Per-item assignments are explicit snapshot metadata, not automatic historical winners.

The configured `TORN_FREN_TRAVEL_EVENT_SNAPSHOT` file must contain the coherent V163 bulk event output (`asof_epoch`, `source_heartbeat_age_seconds`, `items`), optional `item_policies`, `item_evidence`, and model provenance. Forecasts include current observed quantity and last quantity-change epoch. Mixed issue identities, invalid policies, oversized input or unavailable files fail closed. Heartbeat age advances with clock; old deltas are not mislabeled as stale polls. Personal landing time excludes the ten-second research scoring grace.

**Live precomputation/publishing is not installed.** Current GitHub sanitized snapshots refresh roughly every thirty minutes and are unsuitable as a continuously fresh public UI feed. Connecting this page to production needs deployed-source inspection and a reviewed additive feed/route canary with rollback; no VM changes were made in this session.

## Model comparisons

The continuous every-300-second historical evaluator now includes:

- V166 median, quarter, midpoint, recent8 midpoint, late-onset policies.
- Quarter policy with an immediate modeled-current-stock opportunity when the remaining lifetime covers the flight.
- A causal daily-pattern adaptation of the archived Nessie template (2h lookback, one-day lag, ±1h shift, balanced fit). Raw indexed deltas avoid hindsight bounce cleaning. Earliest, widest-window center, and first-window center variants distinguish successful but needlessly late trips from earliest useful trips. **Not certified parity with all incumbent specialist implementations.**
- The real V151 independent whole-cycle model, 48 scenarios and its original support/abstention contract.

Same-issue leave-now and median-policy comparisons, per-item day slices, first proposal per known issue phase, pending/unknown and coverage remain visible. No candidate is promoted because it wins its own inspected backtest. Full item-specific archived ML selectors and true prospective event-engine capture still need work.

## Verified initial expanded experiment

Public source `bc3b49d938ae021c79ac671576eb80d7fa028db7`; causal and browser CI [38505841118](https://github.com/fungjkTorn/torn-fren/actions/runs/38505841118) passed. Search, categories, watchlist persistence, custom flight, graph link, desktop/mobile overflow and JS errors were tested in Chromium. Synthetic test screenshots were visually reviewed; **they are not live stock screenshots**. UI follow-up removes the redundant pagination button, keeps flight input intact during countdown updates, and maintains the research label on mobile.

Private expanded experiment [38505975994](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38505975994) passed. Two days, 13,824 issues per policy, resolved sampled availability:

| Policy | Success / resolved | Coverage |
|---|---:|---:|
| Median earliest | 7,954/11,269 = 70.58% | 89.53% |
| Quarter buffer | 8,638/11,172 = 77.32% | 89.53% |
| Quarter with current stock | 8,622/11,383 = 75.74% | 89.53% |
| V151 independent48 | 8,290/11,016 = 75.25% | 85.63% |
| Daily earliest | 9,229/12,858 = 71.78% | 99.80% |
| Daily widest center | 8,452/11,561 = 73.11% | 99.80% |

Denominators differ and repeated five-minute issues are correlated. The widest-center daily policy waits substantially longer (mean planned wait roughly 3.7 hours); high sampled success alone does not satisfy earliest useful departure. First-window-center is the follow-up designed to address that limitation.

Examples of item-specific behavior: Nessie widest-center 74.20% vs median64.40%; Jaguar midpoint86.00% vs median67.68%; Crocus V15192.11%, current-stock quarter92.27%; Banana Orchid daily center96.61%, current-stock quarter94.13%. Flowers often have small distinct-cycle sample counts despite many issue rows. Japan Xanax median39.01%, V1510 proposals, daily-center18.34%. These results do not establish a reliable beta or universal 90%.

## Next

Run longer chronological comparisons including the first useful template window, then select per-item research candidates with matched evidence, bounded waits, useful coverage and sufficient independent episodes. Prioritize weak Japan, Monkey, Panda, Lion, Camel, Chamois, Nessie and Red Fox families. Keep V2 and experimental intact; introduce this shared read-model additively after reconciliation. No repeated runner installation or manual historical VM command is needed.
