# V22 weak-item rescue: parallel improvement track (2026-10-08)

Research only; do not alter V19/V20/V21 masters, running collector or production routes. Separate from flower/plushie specialists.

## Current catalog
Of 236 country-item entries, exactly **41 score under 50%** on the selected historical arrival benchmark: 24 selected generic models (V19 12, V20 2, V21 10), plus 17 weak sparse depart-now fallbacks. **28 further items** never reached the requested 30-unit stock threshold on the frozen DB and require a distinct, quantity-aware benchmark.

The preliminary diagnostic uses the frozen old DB checksum 9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761, with provider-bounce suppression and observed windows no more than 600 seconds long. It estimates fraction of observed time with stock >=30 (a descriptive statistic, NOT a live success probability).

### Distinct failure groups
- 3 ultra-scarce items (<1% observed time with >=30 available)
- 5 scarce items (1-10%)
- 19 intermittently stocked (10-50%)
- 14 mostly stocked (>50%); bad timing/state or changing regimes is likely the problem

Examples: Cayman Steel Drum 0% selected arrival score, ~1.7% of historical observed time stocked >=30; China Bo Staff 0% and virtually no qualifying stock; Japan Sensu 2.8% and ~1.2% stocked. Argentina Tear Gas 31.3% despite ~67.9% observed historical stocked time and Canada Mountie Hat 25.5% despite ~59.7% suggest potential policy improvements. Period shifts matter: Japan Hydrochloric Acid overall ~92.9% historical stocked time but effectively 0% in the final chronological quarter, Hawaii Small Suitcase ~48.5% overall but ~0% final quarter (check collector coverage and source reliability before calling this a market regime change).

Full item-specific observations in v22_weak_item_stock_diagnostics_2026-10-08.csv (conversation artifact).

## Five new V22 challenger families
1. **Current-stock survival**: forecast whether available stock will last for the actual flight from quantity, age, depletion rate and recent lifetimes. Recommend leaving now when advantageous.
2. **Restock hazard / renewal**: forecast the next qualifying stock-window opening, then recommend a departure targeting the earliest reachable window. Allow genuine 11+ hour waiting without penalizing success, and mark opportunities outside the search horizon separately.
3. **State-and-age nearest neighbors**: condition on live vs sold-out, age since depletion/replenishment, remaining fraction, slope, time of day and recency; fit multiple versions, select only on causal training.
4. **Recent-regime adaptation**: change-point/drought detection, short-vs-long lifetime and availability weights, stale/gap handling, fallback when recent behavior diverges.
5. **Quantity-specific thresholds**: benchmark >=1 or suitable user-selected target for the 28 never-at-30 items, separately from >=30 headline scores.

## Evaluation and promotion
- Start with representatives across all groups: China Bo Staff, Cayman Steel Drum, Japan Sensu, Argentina Tear Gas, China Fireworks, Canada Mountie Hat, Hawaii Small Suitcase, Japan Hydrochloric Acid, Canada Ice Pick, South Africa Combat Vest, Japan Kabuki Mask.
- Keep frozen V19/V20/V21 model per item as incumbent, plus a simple depart-now baseline.
- Compare at identical historical starting times with observation gaps censored and only previously resolved training outcomes used; fit candidate configs in chronological training and assess on untouched later periods. Avoid treating correlated 30-minute sessions as independent trips.
- Report arrival exact and +10sec,+1m,+3m; restock MAE and window coverage; forecast confidence calibration; unnecessary *missed earlier opportunities*, distinct from necessary natural long restock waits.
- Prioritize first crossing 50%, then 70%, 80%, 90%, where physically feasible. Don't hide legitimate low availability with arbitrary scoring tricks.
- Preserve all champions and candidate configs; no automatic deployment until dual-layer website/Discord return actual restock-time and window fields, as well as effective departure recommendations, with shadow replay and rollback tested.

## Parallel tracks
**Improve weak models** (V22) alongside **restock-window prediction**, **newer-data validation** and **production engineering**. Improving 41 weak items is a first-class objective, not a post-deployment cleanup task.
