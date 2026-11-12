# Torn Fren: V19/V20/V21 matched three-way comparison — 2026-10-08

**Research only. No live deployment and no production routing modified.**

## Source integrity
- Received full user V21 all-item master (236 catalog entries, 170 attempts, 116 complete, 54 insufficient).
- Received V20 full master (187 attempts, 114 complete, 73 insufficient).
- Replayed V19, V20, and V21 saved arrival timestamps on identical older frozen history snapshot SHA256 `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`, requiring recorded quantity >=30 at arrival or within 10s, provider bounce filtering and collector gap censoring. Confirmed old V19 corrected tally exactly 1,172 old false negatives, zero false positives, 27,654 scored.

|Version|Completed models|Scored arrivals|Corrected hits|Corrected arrival success|>=90%|
|---|---:|---:|---:|---:|---:|
|V19|134|27,654|18,415|66.59%|42|
|V20|114|12,786|7,575|59.24%|31|
|V21|116|13,567|9,353|68.94%|41|

V20 original stored labels showed only 5,109/12,786=39.96% success. We found **2,466 falsely marked failures**, zero false successes. V20 model selection was done using these wrong labels, so corrected *evaluation* does not mean it was trained with corrected labels; V21 trained and selected with direct quantity truth. Aggregate V20/V21 rates apply to different target item populations, so only matched per-item results can settle contests.

## Matched comparison
- 85 V19/V20 pairs with >=30 common starting decisions, 87 V19/V21, 96 V20/V21.
- 68 items have all 3 model families on >=30 common decision starts; another 64 have exactly 2 families.
- Among 96 V20/V21 comparable pairs, 22 meaningful V21 leads (>=3 hits AND >=2pp); 21 meaningful V20 leads; 40 exact hit ties; remaining differences are marginal.
- V21 and V20 tie for Argentina Meteorite Fragment at 117/122 (95.9%), V21 with a 292.5min median departure wait vs V20 315min. Much of the stock wait is genuine; do not penalize lengthy natural restock cycles.
- Argentina Monkey Plushie: V21 138/163 (84.7%) vs V20 124/163 (76.1%).
- Cayman Diving Gloves: V21 124/126 (98.4%) vs V20 116/126 (92.1%).
- UAE Camel Plushie: V20 117/161 (72.7%) vs V21 83/161 (51.6%).
- Argentina Soccer Ball: V20 102/124 (82.3%) vs V21 82/124 (66.1%).
- China Ecstasy and Swiss Ketamine: V19 has same 100% matched success as V20 and V21, with immediate V19 departures vs V20/V21 12h waits. Do not confuse those waits with natural scarcity.
- UK Shrooms: V21 100%, much faster departures on matched starts than legacy.
- UK/Canada Xanax and Japan Xanax have separately researched specialists (newer DB), not fully incorporated into these generic model rankings.

## Provisional registry (236 entries)
Using common exact starts where possible, conservative incumbent retention for marginal differences; tie on arrival success resolved by earlier *feasible* departure. All entries have status `OFFLINE_RESEARCH_ONLY`:
- 65 V19 generic selections
- 14 V20 generic selections
- 74 V21 generic selections (one has only 25 sessions, underpowered)
- 30 depart-now high-availability baselines
- 24 best-effort sparse, lower-confidence
- 28 with historically observed max below requested 30 units
- 1 Japan Xanax specialist reserved.

**152 have generic V19/V20/V21 evaluation backed by at least 30 arrival decisions; 77/152 candidates show >=90% and 99/152 show >=80% on previously viewed chronological holdouts.** That is explicitly not a fresh, unbiased champion success estimate. Test sessions are correlated and the historical holdout was consulted while picking winners.

For 21 flower/plushie items, 15 generic candidates >=90%; six remain <90%:
- UK Nessie Plushie 89.6% V20
- Argentina Monkey Plushie 84.7% V21
- China Panda Plushie 81.5% V20
- UAE Camel Plushie 72.7% V20
- UK Red Fox Plushie 69.5% V20
- Switzerland Chamois Plushie 67.7% V19.

Prior specialist flower/plushie models and legacy V9/V10 may beat these generic estimates; preserve until matched.

## Release gating / next step
1. Dual-layer **stock forecast** separate from **travel optimization**. Existing live `services.prediction_v2_live` predicts estimated drop time and restock window. V19–V21 arrival-only scores do NOT prove restock timing, interval coverage, lifetime prediction, personalized calibrated confidence, or projected second restock.
2. Produce opt-in shadow predictions on newer untouched sessions (VM snapshot and future data), with actual vs expected drop, window coverage, and arrival success. Store model IDs, exact raw configs, quality/stale flags. Do not claim 95% chance for next trip based on uncalibrated raw historical success.
3. Handle sparse and below-30 items with item-specific requested quantity and honest low-evidence states, and natural restock waits beyond 12h as out-of-horizon, not predictor failures.
4. Build runnable production registry and compatibility adapter with caching, unit/integration tests and rollback path; previous dual-layer contract is *not* wired to live website/Discord.
5. Only after those tests, consider gradual flagged deployment (starting private/shadow), maintaining V2 forecast fallback and not falsely advertising >90% on all 236 items.

The detailed source evaluation artifacts were produced locally in user's ChatGPT conversation:
`v19_v20_v21_comparison.csv` and `torn_fren_matched_provisional_registry.{csv,json}`, plus the bundled markdown report and zip.
