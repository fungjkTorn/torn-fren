# Matched V19/V21 arrival benchmark with restock-aware wait analysis (2026-10-08)

## Frozen evidence
- V19 source: original V19 `master(4).json` (236 keys), 134 completed items and 102 insufficient, scored directly with stock truth after suppressing provider bounces.
- V21 source: user-uploaded `corrected_master.json` (10 complete targeted items, 1,076 holdout sessions, 768 successful, 100% recommendation coverage).
- Audit: user-uploaded `truth_audit.json`: 134 completed V19 keys, 27,654 directly checked sessions, 1,172 corrected false negatives, zero false positives; 42 >=90%; 62 >=80%; 78 >=70%.
- Both models use original frozen DB SHA256 `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`, requested stock >=30, within +10sec arrival allowed, country-specific travel flight.
- Reconstructed V19 truth at arrival from quantity change-event rows (provider-bounce suppression, collector gap invalidation). Compare only identical session start times present in both V19 and V21 holdout outputs. Results **still correlated** and are not a fresh prospective trial.
- 1,037 common scorable starting decisions, with V19 704/1037 = 67.89% and V21 729/1037 = 70.30%; +2.41 percentage points V21, concentrated in Meteorites and Large Suitcases.
- V21 all-10 non-paired 768/1076 = 71.38%, per-item macro mean 78.04%, median 88.54%. 5/10 at >=90%, 7/10 >=80%, 4 perfect. These do NOT apply to all 236 items.

| Country:item | Paired sessions | V19 directly corrected | V21 | V21-only successes | V19-only successes | V19 median departure wait | V21 median departure wait |
|---|---:|---:|---:|---:|---:|---:|---:|
| uni:Shrooms | 78 | 78 (100%) | 78 (100%) | 0 | 0 | 360m | 15m |
| can:Vicodin | 80 | 80 (100%) | 80 (100%) | 0 | 0 | 360m | 720m |
| swi:Ketamine | 76 | 76 (100%) | 76 (100%) | 0 | 0 | 0m | 720m |
| chi:Ecstasy | 77 | 77 (100%) | 77 (100%) | 0 | 0 | 0m | 720m |
| arg:Patagonian Fossil | 79 | 68 (86.1%) | 64 (81.0%) | 7 | 11 | 0m | 195m |
| chi:Printing Paper | 76 | 73 (96.1%) | 60 (78.9%) | 0 | 13 | 0m | 232.5m |
| arg:Meteorite Fragment | 122 | 80 (65.6%) | 117 (95.9%) | 40 | 3 | 0m | 300m |
| arg:Tear Gas | 163 | 51 (31.3%) | 40 (24.5%) | 19 | 30 | 105m | 150m |
| chi:Fireworks | 150 | 57 (38%) | 43 (28.7%) | 21 | 35 | 27.5m | 255m |
| haw:Large Suitcase | 136 | 64 (47.1%) | 94 (69.1%) | 45 | 15 | 47.5m | 195m |

## Crucial interpretation: natural waits are NOT penalized
Long waits can be *correct*. If current Meteorite stock cannot survive the flight and the next feasible restock is eleven hours away, waiting ~9 hours before departing is a good recommendation. Score arrival success independently; no absolute generic hours penalty. Separate stock-availability physics from avoidable missed opportunities.

The existing hindsight stock-opportunity evaluation used original stock change observations (>=30) and country flight, excludes collector gaps. For V21 holdouts:

| Item | V21 median actual wait | Median hindsight minimum viable wait | Median excess wait, successes only | Forced 12h cap |
|---|---:|---:|---:|---:|
| uni:Shrooms | 15m | 0m | 15m | 0/83 |
| can:Vicodin | 720m | 0m | 720m | 54/89 |
| swi:Ketamine | 720m | 0m | 720m | 58/84 |
| chi:Ecstasy | 720m | 0m | 720m | 60/85 |
| arg:Patagonian Fossil | 195m | 0m | 157.5m | 12/79 |
| chi:Printing Paper | 240m | 0m | 180m | 14/85 |
| arg:Meteorite Fragment | 292.5m | 153.1m | 40.7m | 17/122 |
| arg:Tear Gas | 150m | 7.5m | 304.5m | 26/163 |
| chi:Fireworks | 255m | 53m | 80.6m | 15/150 |
| haw:Large Suitcase | 195m | 150.9m | 101.7m | 5/136 |

**Important:** Median-of-differences is not difference-of-medians. The hindsight minimum viable departure is a perfect-information oracle, not necessarily an opportunity a causal model could safely predict. Never subtract all retrospective "excess" directly from a model's arrival success. A late departure that successfully catches a far-later restock is still an actual success. For 17 capped Meteorite sessions, 12 had an earliest hindsight viable departure at least 9h after the decision. The three always-stocked drug markets had 0m median earliest viable delay despite 12h V21 median wait; there V21 was wasteful, and in two markets V19 achieved the same 100% with immediate departures.

## Recommendation for the unified site and champion registry
- `uni:Shrooms`: V21 strong candidate, 100% matched and decreases median wait 6h->15m.
- `arg:Meteorite Fragment`: V21 top arrival candidate 95.9% matched, genuine slow-restock waiting explains part of 5h recommendation; compare with final corrected V20 and latest data, then optimize skipped opportunity risk.
- `haw:Large Suitcase`: V21 arrival candidate 69.1%, natural waiting often ~2.5h, further improve.
- `can:Vicodin`, `swi:Ketamine`, `chi:Ecstasy`: V19 same 100% but shorter median wait; reject V21's forced 12h-delay policy, not the idea of restock waiting.
- `arg:Patagonian Fossil`, `chi:Printing Paper`: matched corrected V19 beats V21 and leaves sooner.
- `arg:Tear Gas`, `chi:Fireworks`: both weak; V19 currently stronger on matched starts, need genuinely different models/low-quantity thresholds.
- V20 still running on user's PC. Do not claim it is completed. Before choosing winners across V19/V20/V21, use same-session stock truth, availability and quantity requirements, and per-item holdout dates. Do not promote by version number.
- **Restock forecast quality was not scored in V21**: no MAE/coverage for next drop window exists from these arrival-only outputs. This is a separate necessary benchmark for the website's estimated drop/window/confidence.
- No live deploy, no production routing changes. Research checkpoint only.
