# October 14 — per-item event models and product integration

This continues the complete private handoff and preserves the original V2 graph,
experimental board, and additive Travel Decisions page. No production service,
collector, incumbent model, or web source was modified.

## Verified research

Private run [38586436243](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38586436243)
completed successfully at public numerical source
`e0a8951926ce83d025bfdc80bbe49a16f8e07fc0`. Seven days, 24 items,
48,384 clock-selected five-minute issues per policy; snapshot cutoff 1791988576.

`research/causal_phase_analogs.py` keeps at most 512 completed phases of each
type and selects 18 item-local neighbors. Features are phase-onset quantity,
the preceding completed phase duration, and cyclic UTC time. The opposite
phase uses shared time coordinates only. Incomplete phases, gaps, and
provider changes across stock thresholds cannot enter training as complete
cycles. Benign same-phase provider changes preserve continuity. It emits the
same complete event stream as V163, including unreachable events. This is a
new causal challenger, not certified parity with archived ML specialists.

| Item | Median baseline | Analog midpoint | Analog current-stock/quarter |
|---|---:|---:|---:|
| Jaguar Plushie | 66.65% | 98.69% | 95.11% |
| Stingray Plushie | 67.56% | 96.97% | 91.94% |
| Wolverine Plushie | 68.61% | 81.49% | 75.32% |
| Japan Xanax | 40.53% | 34.44% | 29.21% |

These are resolved historical sampled-arrival rates, with different resolution
sets. On matched Jaguar issues, midpoint won exclusively 532 times and lost
13; Stingray midpoint won 481 and lost 24. Jaguar current-stock/quarter
planned mean wait 347 seconds versus 1,399 for midpoint; Stingray 366 versus
993 seconds. Earliest useful travel remains an objective, so the highest
percentage does not automatically select the release policy.

The same fixed four-hour event study observed 2,366 clean restocks:

| Family | Matched within 10m | Recall | Precision | Within 60s |
|---|---:|---:|---:|---:|
| V163 | 1,101 / 2,366 | 46.53% | 43.45% | 209 / 2,366 |
| Phase analogs | 1,238 / 2,366 | 52.32% | 50.28% | 199 / 2,366 |

Coarse timing improved; tight timing did not. Repeated issues and first
issue-phase proposals are correlated. None of this certifies live player
flights, purchases, or a calibrated probability. Japan and most long-flight
plushies remain weak. Do not globally replace incumbents.

## Added validation and interface work

- `research/departure_reconfirmation.py`: fixed hourly trip starts, replacing
  the plan at each five-minute issue, at most eight hours waiting. A departure
  exactly at the next issue must use the new forecast. Stale source evidence
  prevents simulated departure. Pending, abstention and scored arrivals stay
  separate. This is historical replanning, not actual player execution.
- `research/per_item_readiness.py`: analog event policies face the same
  historical and latest-day 90% gate, coverage, sample and matched-win gates.
  No automatic assignments or promotion. Earliest waiting cost breaks ties
  among candidates clearing the same tier.
- `research/product_runtime_audit.py`: bounded localhost-only GETs of both
  legacy pages/APIs and Travel Decisions; no redirects, proxying, collector
  files, raw API payloads or deployment. Reports route hashes and roster
  diagnostics. HTTP 200 alone never establishes accurate or fresh data.
- Travel Decisions now clears departure and landing clocks when freshness
  expires client-side, including the available-trip count. Browser tests cover
  this and API failure while editing the flight field.
- `research/build_travel_event_snapshot.py`: coherent read-only batch
  preparation and atomic JSON publication, with explicit per-item history and
  flight-adapter assignments. Reads one SQLite transaction, requires a <=180s
  source heartbeat, rejects active collection outages, and validates the exact
  board consumer contract. No model executes per HTTP request. No timer or
  production integration is installed by this script or these commits.

Numerical/reconfirmation source approved for private research:
`63d24c7f41767130a3b2bc3495a2735b40a1d591`.
Publisher source: `6b64e9a14442cd1e0e63760d4bc0b8072753bf95`.
The publisher source passed 51 relevant unit tests, Chromium interaction tests,
and all three compatibility workflows. The local scratch Python lacks FastAPI;
route tests passed in GitHub CI, which installs declared dependencies.

## Operational scope and next gate

The manifests, snapshot exporter, and private dataset still define 24 items.
The user's new goal is 28 by tonight; four additional item/country identities
are not defined in the repository. Do not invent their names or imply that
changing a row limit adds their stock history. A roster expansion also requires
collector-owner export coverage; the isolated worker cannot bypass its ACL.

Continuously fresh production feed installation and legacy-page integration
remain outstanding. The roughly 30-minute research snapshot is not suitable
for continuously fresh public trip clocks. Inspect actual deployment drift
and stage an additive canary with rollback; never copy research web/app.py over
the deployed app. Routine research needs no user VM commands or reinstall.

The follow-up private run includes the exact readiness gates, reconfirmation
outcomes and read-only runtime audit. Record its verified result below before
concluding this session. Fresh chronological/forward validation remains
required before promoting any historical winner.

## Verified follow-up and runtime observations

Private [38587427915](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38587427915)
passed at numerical source `63d24c7f41767130a3b2bc3495a2735b40a1d591`,
cutoff 1791990397. It evaluated 168 fixed hourly trip starts per item/policy,
with five-minute replanning and source expiration at departure:

| Policy/item | Successful / resolved | Departure coverage | Mean wait among departures |
|---|---:|---:|---:|
| Jaguar analog current-stock/quarter | 152 / 158 = 96.20% | 168 / 168 | 9.3 min |
| Stingray analog quarter | 153 / 156 = 98.08% | 168 / 168 | 14.8 min |
| Wolverine analog midpoint | 152 / 161 = 94.41% | 167 / 168 | 20.1 min |
| Japan Xanax analog midpoint | 67 / 152 = 44.08% | 167 / 168 | 83.1 min |

Unknowns and pending outcomes are excluded from resolved fractions, not
converted to successes. These are correlated historical replanning cohorts,
not matched comparisons, fresh holdout certification or real player trips.
The recorded sampled phase paths cannot prove exact-second upstream stock.

Replanning exposes starvation: analog midpoint had zero departures for Crocus,
Banana Orchid and Dahlia despite strong frozen-plan percentages. Daily widest
center never departed for most items. Reject such release candidates. The
readiness gate now additionally requires at least 100 scoreable replanned
arrivals, >=60% actual simulated departure coverage, and replanned success
>=90% for the target tier (>=80% for the lower tier). Recomputed with the exact
new gate from run38587427915's retained policy counters, the result remains
**12 target-tier, 4 promising, 8 requiring more research**. Cherry Blossom
changes from the weaker replanned late-onset policy to analog midpoint.
This does not upgrade Wolverine to the target tier: its frozen-policy week
remains below90%, even though replanning exceeded90%.

Target-tier candidates: Ceibo, Crocus, Banana Orchid, Stingray, Peony, Cherry
Blossom, Dahlia, Jaguar, African Violet, Edelweiss, Tribulus, Heather.
Below target: Wolverine, Canada Xanax, Orchid, UK Xanax.
Needs research: Monkey, Panda, Japan Xanax, Lion, Chamois, Camel, Nessie, Red Fox.

The read-only VM localhost audit verified HTTP200 for `/`, `/experimental`,
and `/api/experimental/v41/predictions`. The latter has24 unique configured
items, zero missing/duplicates/unexpected items. Current reported statuses:
19 RESEARCH_PROPOSAL_ONLY,2 RESEARCH_PREVIEW_UNVALIDATED,
2 DEPARTURE_PASSED,1 RESEARCH_PREVIEW_STALE_OR_INVALID. These do not certify
current actionable recommendations. Both Travel Decisions routes return404.
No production page was changed. The runner can perform these safe route
checks without user VM commands; privileged deployment still needs a staged
collector-owner integration and fresh feed.
