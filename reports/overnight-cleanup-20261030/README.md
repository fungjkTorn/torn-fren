# Torn Fren overnight cleanup — completed October 30, 2026

Both fixed variants are complete. Retain the saved baseline: the full-history cleanup did not improve plushie success, reduced South African performance, and reduced UK advice coverage. The seven-day-half-life comparator lowered every non-UK success rate. These findings do not support promoting either cleanup as an accuracy upgrade. The live sixteen and collector were not changed.

## Evidence and protocol

Test week: October 22, 2026 at 10 PM through October 29 at 10 PM Eastern. Each of six items has exactly 2,017 issue clocks per variant (24,204 records total). Forecasts use only causal earlier actual stock observations; all earlier native training history remains available. Issuance is sampled every 300 seconds, while departures are unrestricted. Live V5 freezes each simulated trip at its recommended departure; success requires stock >30 at its exact arrival, with zero grace. No real-player trips are required. This already-inspected week is retrospective research, not a blind holdout.

Frozen native experiment: `4fe4b9e2f05200651d230012c9b59c42985758a3`. Recovery/comparison base: `2a6ce9285b3bb2b27d1fe5d1902277498775d472`. Recovery added reporting and auditing only. All native code fingerprints match the saved manifests, and every saved recovery prefix remains byte-for-byte unchanged. The stock database retains SHA256 `543b67f1fe4874961130948ecee1d9df4870efe80599726f13828b19da8a6687`.

## Known frozen-arrival results

| Item | Saved baseline | Full-history cleanup | Seven-day-half-life cleanup |
|---|---:|---:|---:|
| Camel | 89/121 (73.6%) | 89/121 (73.6%) | 81/117 (69.2%) |
| Nessie | 108/145 (74.5%) | 108/145 (74.5%) | 100/139 (71.9%) |
| Red Fox | 89/116 (76.7%) | 89/116 (76.7%) | 85/117 (72.6%) |
| Panda | 94/128 (73.4%) | 94/128 (73.4%) | 93/128 (72.7%) |
| South African Xanax | 25/35 (71.4%) | 20/29 (69.0%) | 16/36 (44.4%) |
| UK Xanax | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

UK is one independent successful trip in each version, not an established 100% success rate. Repeated refreshes during continuous stock do not create independent successes.

## Every failure, unknown and pending trip

Each failure has its own row in the variant’s `all-misses.csv`, including distances and intervals for the prior clean zero boundary and next qualified refill. Other failures include positive stock ≤30, boundary uncertainty and exact ties; they remain failures. Unknown/pending outcomes are separate from known failures and are individually exported in `all-unknown-and-pending.csv`.

| Variant | Item | Early | Late | Other failures | Unknown / pending | Median early / late miss, min |
|---|---|---:|---:|---:|---:|---:|
| clean-full | Camel | 17 | 7 | 8 | 8 / 2 | 2.78 / 1.92 |
| clean-full | Nessie | 16 | 16 | 5 | 9 / 1 | 3.82 / 4.51 |
| clean-full | Red Fox | 9 | 12 | 6 | 6 / 1 | 3.40 / 5.38 |
| clean-full | Panda | 16 | 15 | 3 | 10 / 2 | 3.12 / 2.78 |
| clean-full | South African Xanax | 1 | 8 | 0 | 4 / 1 | 4.82 / 30.86 |
| clean-full | UK Xanax | 0 | 0 | 0 | 0 / 0 | — / — |
| clean-recent7 | Camel | 15 | 14 | 7 | 11 / 2 | 3.25 / 5.00 |
| clean-recent7 | Nessie | 21 | 12 | 6 | 11 / 1 | 4.23 / 4.52 |
| clean-recent7 | Red Fox | 12 | 18 | 2 | 6 / 1 | 2.68 / 4.43 |
| clean-recent7 | Panda | 16 | 14 | 5 | 12 / 2 | 3.34 / 3.51 |
| clean-recent7 | South African Xanax | 2 | 17 | 1 | 0 / 1 | 34.09 / 29.45 |
| clean-recent7 | UK Xanax | 0 | 0 | 0 | 0 / 0 | — / — |

Full-history cleanup has 139 known failures, 37 unknown and seven pending trips; recency cleanup has 162 known failures, 40 unknown and seven pending trips. Both archives retain every frozen trip and outcome. Daily outcomes, withheld-forecast reasons and close-miss counts are in each `miss-analysis.json`. No missed arrival was shifted to manufacture a success.

## Advice coverage and waiting

Advice counts use all 2,017 clocks, including stale-country clocks. Waiting is measured from issue to recommended departure across advice clocks; repeated advice is deliberately separate from independent frozen-trip counts. Full p90/max distributions and frozen-trip revision-to-departure waits are in `recovery-validation.json`. A zero median wait on the final frozen issue does not mean the traveler had no earlier wait: recommendations can be revised before departure.

| Item | Baseline advice | Cleanup advice, both variants | Baseline median wait, min | Full median / p90 | Recency median / p90 |
|---|---:|---:|---:|---:|---:|
| Camel | 1762 (87.4%) | 1762 (87.4%) | 5.00 | 5.00 / 24.57 | 6.18 / 27.28 |
| Nessie | 1786 (88.5%) | 1786 (88.5%) | 14.85 | 14.85 / 34.83 | 14.16 / 34.57 |
| Red Fox | 1782 (88.3%) | 1782 (88.3%) | 13.71 | 13.87 / 33.22 | 5.00 / 25.00 |
| Panda | 1814 (89.9%) | 1814 (89.9%) | 13.34 | 13.47 / 33.63 | 14.15 / 34.27 |
| South African Xanax | 1849 (91.7%) | 1849 (91.7%) | 65.00 | 136.17 / 277.25 | 79.45 / 182.45 |
| UK Xanax | 1947 (96.5%) | 1935 (95.9%) | 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |

Coverage did not improve for the five non-UK items. UK lost 12 advice clocks relative to this saved baseline: both cleanups advise on 1,935/1,947 fresh-country clocks, with 70 stale clocks and 12 model abstentions. Those extra abstentions and the unchanged one-trip sample are not an accuracy gain. South African full-history advice waits rose from a 65-minute median to 136.17 minutes, while simulated trips fell from 40 to 34.

## Exact observed opportunity comparison

Target matching uses the same resolved observed opportunity/episode identities as the saved V5 comparison, never the nearest predicted timestamp. Unresolved identities cannot be paired; all trips remain in the overall results. `exact-observed-opportunity-pairs.csv` includes shared and unshared identities and exact departure shifts.

| Variant | Item | Both known | Candidate-only success | Baseline-only success | Baseline-only / candidate-only opportunities | Median paired departure shift, min |
|---|---|---:|---:|---:|---:|---:|
| clean-full | Camel | 119 | 0 | 0 | 0 / 0 | 0.00 |
| clean-full | Nessie | 144 | 0 | 0 | 0 / 0 | 0.00 |
| clean-full | Red Fox | 115 | 0 | 0 | 0 / 0 | 0.00 |
| clean-full | Panda | 127 | 0 | 0 | 0 / 0 | 0.00 |
| clean-full | South African Xanax | 29 | 0 | 3 | 6 / 0 | 0.00 |
| clean-full | UK Xanax | 1 | 0 | 0 | 0 / 0 | 0.00 |
| clean-recent7 | Camel | 111 | 7 | 11 | 3 / 2 | 1.43 |
| clean-recent7 | Nessie | 135 | 2 | 6 | 7 / 3 | 0.00 |
| clean-recent7 | Red Fox | 111 | 9 | 14 | 1 / 2 | 5.00 |
| clean-recent7 | Panda | 119 | 11 | 14 | 4 / 6 | 0.00 |
| clean-recent7 | South African Xanax | 31 | 3 | 13 | 4 / 1 | -97.50 |
| clean-recent7 | UK Xanax | 1 | 0 | 0 | 0 / 0 | 0.00 |

Recency’s net shared-known success differences are −4 Camel, −4 Nessie, −5 Red Fox, −3 Panda and −10 South Africa. Full-history cleanup has no plushie net gain and loses three South African shared-known successes. Its six lost South African observed opportunities further weaken the case for promotion. A percentage alone would miss these tradeoffs.

## Outcomes for the four approved cleanup areas

1. **UK sustained surplus:** signed ten-minute net-stock blocks include flat/rising stock and exclude known refills, resets, outages and stale intervals. Current-quantity support can recommend immediate travel without inventing an onset or depletion timestamp. This implements the approved behavior, but the current comparison reduces advice coverage and cannot validate accuracy beyond one continuous-stock trip. Keep continuous-stock labeling and provisional status.

2. **Current-stock window ends:** lower-quartile remaining lifetime and upper-quartile net-loss projection replace the median end estimate, including a response to the latest fresh rapid loss. In South Africa this removed current-stock advice entirely (396 baseline current-stock advice clocks versus zero), shifted advice toward future windows and did not improve outcomes. Retain the baseline; a more conservative window end was not enough to solve the underlying timing problem. The original ten South African misses and their headroom remain in the supplied audit.

3. **Arrival placement:** the approved rule clamps native timing only when the upper-quartile restock start overlaps the lower-quartile stock end inside the selected feasible window. Otherwise it retains native timing and never skips that selected event on a model score. The empty-core limitation materially restricts how often this rule acts. Counts below are issue clocks, not independent trips.

| Item | Full future clocks / overlaps / adjusted | Recency future clocks / overlaps / adjusted |
|---|---:|---:|
| Camel | 1762 / 0 / 0 | 1762 / 0 / 0 |
| Nessie | 1786 / 0 / 0 | 1786 / 0 / 0 |
| Red Fox | 1782 / 6 / 4 | 1782 / 6 / 3 |
| Panda | 1814 / 5 / 4 | 1814 / 6 / 5 |
| South African Xanax | 1849 / 16 / 7 | 1849 / 0 / 0 |
| UK Xanax | 0 / 0 / 0 | 0 / 0 / 0 |

Camel and Nessie had no overlapping uncertainty cores at all, so this rule did not refine any of their arrivals. Across the full-history cleanup only 15 issue clocks were adjusted; recency adjusted eight. No plushie accuracy improvement can be attributed to a rule that mostly retained native timing. No new fallback or broader placement sweep was silently added.

4. **Bounded adaptation comparison:** one seven-day exponential half-life was tested while retaining positive weight for older history; native model identities and complete native inputs stayed pinned. The comparator underperformed on all five non-UK items and on exact shared opportunities. Reject this adaptation for promotion on the available evidence; do not tune another half-life on this week.

## Calendar and normal-refill diagnostic

South Africa has 42 clean same-provider returns from ≤30 to >30 during the week. Thirteen return below the pre-test learned normal-refill band. These are ambiguous availability returns/sellbacks, not asserted normal restocks. The existing calendar learns availability transitions, while miss boundaries use qualified normal-refill evidence. This definition alignment needs explicit investigation before a further South African forecasting change. The frozen comparison does not rewrite that calendar.

UK had one clean surplus-to-base reset example before the week and eight by the uploaded cutoff. The latest evidence supports a reset base of 2,500. That later calibration was not substituted into the replay’s initial profile. It is available for a future prospective setup using only information then known; it does not retrospectively validate this week. Complete observed transitions and profiles are in `checks/calendar-refill-diagnostic.json`.

## Recommendation and remaining readiness

Retain the baseline configurations. Red Fox’s baseline remains the strongest of these five non-UK candidates at 89/116 (76.7%) and can be considered separately for forward beta under the earlier screening rule. The cleanup comparison supplies no improvement that justifies replacing it. Camel, Nessie, Panda and South African Xanax still need better timing evidence. UK can be studied as a provisional continuous-stock case, but should not be advertised as a validated 100% model. Any live addition requires its normal VM preflight and explicit deployment decision; no deployment was performed here. No real-player flight requirement was introduced.

## Validation and recovery accounting

Both final archives have six items × 2,017 unique clocks, zero model errors, correct pinned identities/full-history flags, correct strict quantity/grace rules, causal net-rate label cutoffs and exact flight geometry. Every frozen trip preserves its issued recommendation. V5 rescoring is idempotent, original inputs remain unchanged, and duplicate observed-target audits pass. The original 36 real-snapshot and 12 exact resume checks are retained. Recovery regression checks passed 40 tests and 121 subtests. Re-scoring the baseline reproduced all per-item metrics and research identity exactly; only scoring-code provenance hashes differ.

The original environment’s output directories and jobs did not survive. An isolated worktree was restored without touching the older workspace’s uncommitted changes. Initial recovery attempts encountered a missing dependency and overlapping writes; those attempts were retained separately and excluded. Final runs used a fresh isolated parent copied from the exact supplied prefixes; no duplicate rows were edited or used for scoring. The final audit caught two missing UK recency tail clocks; the unchanged runner appended those two forecasts from the same actual source before rescoring. All authoritative files were then validated and restored under the requested `clean-full-v3` and `clean-recent7-v3` paths.

## Package contents

The package contains this report, comparison/validation JSON, every authoritative forecast JSONL, frozen-trip JSON/CSV, every failure CSV, all unknown/pending outcomes, exact opportunity pairs, original checks, protocol/recovery documents and source/code identities. Original supplied checkpoint and baseline ZIPs are retained as original evidence. Excluded recovery attempts are clearly separated and are not candidate accuracy archives. Raw stock SQLite bytes remain in the original source file, separately preserved with the SHA256 above; no stock database is committed to Git.

Source file: `torn-fren-challenger-history-20261030T020202Z.sqlite`, Library `libfile_f403ec62efd48191a0651e6a7d831b16`. Baseline archive: `libfile_3683e7f1eb6c8191a3f7e826fc033a02`. Completed report replaces unfinished `libfile_c6c7ca2635ec8191aed9a4b9c3f43c81`.
