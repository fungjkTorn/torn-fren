# V146 final 24-item VM replay — complete uploaded logfile

Read-only replay finished successfully, issue snapshot counts: 552 first-item-UTC-hour cohorts (23 per item, 24 roster). Source is user's complete UTF-16LE Tee-Object V146 file uploaded 2026-10-13, not prior truncated terminal snippet. This report never asserts true game arrival success, immutable as-issued source provenance or country provider freshness.

## Full 24-item aggregates

| Method | Issued departure proposals | Mature poll-state >=30 hits | Mature misses | Pending | Unknown | Matched vs leaving now |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Original V128 | 224/552 | 131 | 51 | 26 | 16 | Not calculated in this report |
| V145 recovered phase + original MC (96 calls, 4/item cap) | 92/552 | 71 | 14 | Unclear among non-scorable issued | Unclear among non-scorable issued | 82 mature matched pairs: **4 V145-only wins vs 4 leave-now-only wins = net 0** |
| V148 explicit restored restock/depletion intervals | 463/552 | 269 | 101 | 52 | 41 | 346 mature matched pairs: **48 V148-only wins vs 54 leave-now-only wins = net -6** |

Conditional mature proxy rates are 131/182 (72.0%) V128, 71/85 (83.5%) V145, and 269/370 (72.7%) V148. **DO NOT RANK THESE PERCENTAGES AS DIRECT COMPARABLE**: V145 is budget-capped (nonrepresentative), models proposed on differing subsets, and matched leave-now is required to assess incremental usefulness. V148 offers high proposal coverage (83.9%) but no measured lift over leave-now on 346 matched observations. Separate restock cycles can be reused across hourly issues.

V145 **217 newly eligible** entries across the exact 552 issued records after benign provider-switch phase restoration. 56 issued entries already eligible for both methods. **389 eligible** (including new and originally eligible) had no MC evaluation due the cap of 96, 4 per item. Another 67 remained incomplete phases / unknown onset. 40 of V145 MC runs were on newly recovered eligibility. The 389 *are not new recoveries*.

## Item observations

| Item | V145 newly eligible | Original V128 proposals | V145 capped proposals | V148 proposals | V148 proxy hit / miss | Matched V148-only minus leave-now-only | V148 median departure wait |
|---|---:|---:|---:|---:|---:|---:|---:|
| Argentina Ceibo | 11 | 6 | 4 | 19 | 14/3 | 0 | 75.0 min |
| Argentina Monkey | 5 | 15 | 4 | 20 | 9/7 | -3 | 3.6 min |
| Canada Crocus | 17 | 5 | 4 | 23 | 16/0 | +2 | 0.0 min |
| Canada Wolverine | 3 | 19 | 4 | 22 | 10/7 | -1 | 6.1 min |
| Canada Xanax | 12 | 7 | 4 | 21 | 14/2 | +7 | 19.0 min |
| Cayman Banana Orchid | 11 | 6 | 4 | 18 | 13/1 | +1 | 0.0 min |
| Cayman Stingray | 4 | 16 | 4 | 20 | 11/8 | 0 | 8.3 min |
| China Panda | 5 | 15 | 4 | 20 | 12/5 | +1 | 10.6 min |
| China Peony | 18 | 0 | 4 | 23 | 10/7 | -4 | 55.2 min |
| Hawaii Orchid | 13 | 6 | 4 | 20 | 15/2 | +1 | 69.1 min |
| Japan Cherry Blossom | 14 | 9 | 4 | 23 | 11/7 | -2 | 50.2 min |
| **Japan Xanax** | **13** | **0** | **0** | **0** | **0/0 because 0 proposals, NOT 0% accuracy** | n/a | n/a |
| Mexico Dahlia | 5 | 4 | 4 | 9 | 8/1 | +2 | 9.4 min |
| Mexico Jaguar | 2 | 19 | 4 | 21 | 18/1 | 0 | 0.0 min |
| South Africa African Violet | 12 | 6 | 4 | 18 | 7/6 | -5 | 81.9 min |
| South Africa Lion | 3 | 19 | 4 | 22 | 12/6 | -2 | 7.5 min |
| Switzerland Chamois | 7 | 15 | 4 | 22 | 13/3 | 0 | 0.0 min |
| Switzerland Edelweiss | 10 | 0 | 4 | 19 | 8/5 | -2 | 10.1 min |
| UAE Camel | 2 | 17 | 4 | 19 | 8/6 | -1 | 1.6 min |
| UAE Tribulus | 16 | 4 | 4 | 23 | 14/4 | -1 | 68.5 min |
| UK Heather | 8 | 6 | 4 | 15 | 10/1 | -1 | 64.2 min |
| UK Nessie | 5 | 15 | 4 | 20 | 9/7 | +1 | 12.0 min |
| UK Red Fox | 8 | 15 | 4 | 23 | 11/9 | -2 | 6.1 min |
| UK Xanax | 13 | 0 | 4 | 23 | 16/3 | +3 | 160.6 min |

## Interpretation and engineering priority

- **Preserve both deployed views and the existing V75 specialists**. V148 creates many restock-window proposals but matched outcomes favor leave-now by six unique trials, so not suitable for public promotion.
- **Do keep V145 phase extraction** as a tested, research-only fix that recognizes real observed start/end bounded phases across benign provider changes, without automatically making flight claims.
- **Japan Xanax:** V145 recovered 13 eligible out of 23 issued hours, but V145 MC issued zero departures in its four evaluated samples and V148 returned NO_CONSERVATIVE_REACHABLE_WINDOW on 22 hours. Diagnose specifically short stock lifetime relative to uncertainty in restock onset, not missing restocks. Do not relax conservative gating into unsupported flight advice.
- **Long waits:** UK Xanax V148 median 160.6-minute departure delay requires observational cadence and earlier-cycle explanation. Generic median waits 50–80min on some flowers can be reasonable or not depending on actual observed cadence and how often >=30 survives.
- **Next model evaluation:** Score departure candidates and observed >=30 at arrival using matched as-issued cohorts; preserve pending and uncaptured source ambiguities. Report *expected restock timing error*, *cycle missed/selected*, quantity survival and paired incremental lift; avoid claiming a win from raw coverage.
- **VM usability:** V149 compact output now prints <=45 lines including every item instead of enormous V146 JSON; user does not need to rerun V146 solely for report extraction.

The live collector, original detailed V2 graph, experimental 24-item dashboard and services were not changed.

## Research continuation after full replay

Committed V150 stock-window failure diagnostics, regression tests and integration into the next *read-only* V146 replay. It explains the 22/23 conservative NO_CONSERVATIVE_REACHABLE_WINDOW outcomes for Japan Xanax by separating mismatched cross-quantile restock/stocked-lifetime bands from truly unreachable median stock windows. A median-only possible window is research output only, explicitly NOT an actionable flight or calibrated probability. Exact future performance remains untested on VM; the newly committed modules were NOT deployed. The VM replay helper stages V150 alongside V145/V148 and emits the newer concise V149 report; **user need not rerun the existing full replay** merely for compact display.

A complete offline report and CSV were generated from the uploaded UTF-16LE full file and linked directly in the completion message.
