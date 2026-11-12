# V22 weak-item rescue: executed research checkpoint — 2026-10-08

**RESEARCH ONLY. DO NOT PROMOTE OR CHANGE LIVE ROUTES FROM THESE RESULTS.**

This updates [the V22 plan](./v22_weak_item_rescue_checkpoint_2026-10-08.md) with actual executable research, measured failures, and evidence for possible improvements. The separate plushie/flower model thread is unchanged.

## Dataset, causal controls, and reproducibility
- Original V19/V20/V21 frozen DB SHA256: `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`; global final recorded timestamp: 1791241486.
- Additional 49-hour VM snapshot `torn-fren-stock-history-latest.db`, SHA256 `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`; global final timestamp 1791418812.
- Threshold >=30 units, arrival or +10 seconds, exact country flight durations from legacy model master. Censor known collection gaps, remove one-poll conflicting-source provider bounces, require full 12-hour future horizon observed for fair comparisons.
- Developed **six state/age/recent-regime analog configurations**, selected solely on old chronology from 50–75% of time, and tested against the stored selected V19/V20/V21 model's same old final-period decision timestamps. Historical finalist sessions were **already viewed during earlier model selection**, so old-period model improvement here is development evidence, not unbiased prospective validation.
- Analog training outcomes have to resolve completely BEFORE the decision timestamp; candidate features only examine stock at or before decision. Candidate leaves once, with no real-time replanning yet.
- Next 49h VM evaluation freezes the old selected config and compares against depart-now on identical clean chronological starts. No old incumbent predictions were generated for these new starts, so an apparent win vs depart-now is NOT automatically a win vs incumbent. Half-hour sessions are correlated.
- Five local sanity checks passed: no future feature use, no unresolved training labels, gap censoring, stock truth semantics, and restock forecast interval causality. No production tests conducted.

## New feasibility discovery: 12-hour hindsight stock ceiling
For 41 weak (<50%) items, evaluate ANY >=30 landing within 12 hours from each historical start, on a 15-minute departure grid. This is a **hindsight oracle** with future actual stock known; NEVER display its rates as a forecast.
- Argentina Tear Gas 100% observed potential vs its existing 31.3% selected score.
- China Fireworks 99.6% potential vs 38.0% current.
- Japan Kabuki Mask and Sumo Doll 100%; China Katana 98.8%; Argentina Compass 100%.
- Cayman Steel Drum, China Bo Staff, China Twin Tiger Hooks, Hawaii Small Suitcase, Japan Hydrochloric Acid and UK Sextant had **0** verified qualifying opportunities within 12h in these final-period starts. Some have historical >=30 stock outside those periods: they need out-of-horizon and/or quantity-aware modeling, not a fictitious 90% number.
- Unlike hindsight waiting, genuine 11h restock waits must NEVER be penalized merely for lasting hours.

## All 41 V22 analog challengers executed
24 selected prior dynamic-model incumbents were compared on at least 30 identical old starting times; 17 were sparse fallbacks that can only be compared with depart-now on the old period. The analog improved by >=10pp and >=3 matched successful arrivals on only **three** previously modeled weak items:
- South Africa Combat Vest: incumbent 19/77 (24.7%) vs V22 53/77 (68.8%), selected `renewal_day`.
- Hawaii Basalt Point: incumbent 26/63 (41.3%) vs V22 39/63 (61.9%), selected `broad_month`.
- Argentina Chalcedony Point: incumbent 38/84 (45.2%) vs V22 50/84 (59.5%), selected `tod_week`.
Other test items were mixed; many old champions were clearly better and should be retained. Avoid optimistic per-item promotion by version label.

## Newer VM snapshot, frozen old-choice V22 vs depart-now: fifteen items
All rates below are paired on **the same** new VM decisions. 12h horizon is observed and collector-gap-free:
| Item | V22 frozen challenger | Depart now |
|---|---:|---:|
| Canada Fire Hydrant | 58/64 (90.6%) | 26/64 (40.6%) |
| China Katana | 47/69 (68.1%) | 23/69 (33.3%) |
| China Fireworks | 32/67 (47.8%) | 12/67 (17.9%) |
| Argentina Chalcedony Point | 42/70 (60.0%) | 21/70 (30.0%) |
| Hawaii Basalt Point | 40/71 (56.3%) | 22/71 (31.0%) |
| Japan Kabuki Mask | 36/69 (52.2%) | 30/69 (43.5%) |
| Japan Sumo Doll | 36/69 (52.2%) | 31/69 (44.9%) |
| Argentina Tear Gas | 13/70 (18.6%) | 10/70 (14.3%) |
| Argentina Compass | 16/70 (22.9%) | 26/70 (37.1%); V22 loses |
| South Africa Combat Vest | 65/65 (100%) | 65/65 (100%); no new-VM advantage |
| Hawaii Taurus | 58/61 (95.1%) | 56/61 (91.8%) |
| South Africa Mag 7 | 52/52 (100%) | 52/52 (100%) |
| Mexico Flare Gun | 51/68 (75%) | 51/68 (75%) |
| Canada Safety Boots | 9/67 (13.4%) | 0/67 (0%) |
| South Africa Combat Gloves | 29/65 (44.6%) | 29/65 (44.6%) |

The frozen analog is a viable **research challenger** for Canada Fire Hydrant, China Katana, China Fireworks, Argentina Chalcedony Point and Hawaii Basalt Point. Obtain matched old-incumbent *new* predictions and several fresh periods before promoting. Other cases stay with their incumbent or a trivial stock-survival baseline.

## Explicit next-drop forecast: separate from travel success
Added experimental rolling renewal wait prediction with time-since-last-depletion survival conditioning. Parameters selected by old-period MAE, evaluated on newer VM observations; bounds are empirical but NOT calibrated window coverage.
- Argentina Tear Gas: MAE 4.0 minutes, 84.1% next-drop window coverage, median window 13.5 minutes, 44 hourly decisions.
- Japan Sumo Doll: MAE 20 minutes, 90.3% coverage, median width 93.9 minutes, 31 decisions.
- Japan Kabuki Mask: MAE 26.1 minutes, 76.5% coverage, median width 104 minutes, 34 decisions.
- China Fireworks: MAE 260 minutes, only 34.3% coverage (wide 392-minute window), 35 decisions.
- China Katana: MAE 162.3 minutes, 52% coverage (wide 427-minute window), 25 decisions.
- Canada Fire Hydrant: 100% interval coverage but median 1,316-minute window. **This is not a useful high-confidence restock prediction**.
- South Africa Combat Vest: only TWO scorable next-drop states on new VM; inconclusive.

**Essential conclusion:** Argentina Tear Gas can predict the *next* qualifying restock fairly precisely and still fail travel timing. It refills every ~20.5 minutes and qualifying stock lasts ~3.1 minutes; its 111-minute flight spans ~5.4 restock cycles. Predicting the nearest drop is NOT predicting the flight-reachable drop. Explicit multi-cycle projection and stock survival must connect the two forecast layers.

## Multi-cycle alternate model results
A second new challenger extrapolates the last N restock intervals and conditions landing offset on the resolved qualifying stocked lifetimes. Selected old validation configuration (no new tuning):
- Japan Sumo Doll on new VM **39/69 (56.5%)**, vs static V22 analog 36/69 (52.2%), depart-now 31/69 (44.9%). But this periodic model produced 94/235 on older matched starts, below V19 incumbent 98/235. Still experimental.
- Argentina Tear Gas periodic 9/70 (12.9%), versus V22 analog 13/70 (18.6%). A simple periodic clock is not enough across 5+ cycles in flight.

## Decision / next priority
1. Freeze V19–V21 registry and V22 candidates independently. No automatic production promotion.
2. For >=30 short-lived stocks: forecast **multiple cycles ahead with regime variation** and current-stock survival, then optimize a reachable leave time. Tear Gas and Fireworks remain critical.
3. For slowly changing high-availability items: use stock survival to pick depart now, not an unjustified 12-hour delay; maintain natural long-restock wait without a time penalty when it is actually needed.
4. Next shadow run must compare frozen V22 against recorded EXECUTABLE V19/V20/V21 predictions at the same newer starts, not just depart-now, and track restock point/window, landing odds, gaps, and exposure to selection bias.
5. Per-user requested quantities and >12h opportunities remain separate capability tasks, as do calibrated confidence and safe website integration.

**Reproducible scripts, five unit tests, 41-row result CSV, 15-item VM shadow JSON, next-drop forecasting JSON and multi-cycle experiment JSON** were generated as a downloadable ChatGPT conversation research bundle: `torn_fren_v22_weak_item_research_2026-10-08.zip`. The bundle is NOT in this GitHub repository; do not claim the V22 prototype itself is deployed or committed. This checkpoint records progress safely while production V2 and previous research masters remain unchanged.
