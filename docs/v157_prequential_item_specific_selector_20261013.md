# V157: as-of held-out item-specific cycle model selection (research only)

## Decision from the actual V156 read-only VM replay

The user's latest successful VM comparison covered **600 first-issued item-hour cohorts, 24 items**, and did not alter any live service, database, worker, or website. V156 chose paired modeling on **0 of 508** issued departures and exactly matched independent V151 (316/414 mature observed ≥30-at-landing poll-state proxies, net +0 vs independent). The raw *always-paired* model scored 321/415 mature with 12 paired-only hits and 9 independent-only hits among 406 matched (net +3), showing that forced fleet-wide pairing is not well-supported.

Per-item, raw paired benefits varied: **Red Fox +3, Jaguar +2, Lion +2**, but **Chamois -3, Stingray -2, Monkey -1** (small, correlated hourly issue samples; not independent flights). V156 did not discriminate them, even when stocked/depleted lifetimes clearly differed. Its rank-correlation and chronological half requirements are also unidentifiable on nearly constant or provider-resolution-quantized cycle lengths. Simply lowering rho after seeing these results would overfit to outcomes. Do NOT do that.

Observed median stock/depleted characteristics across original issue cohorts:
- Standard plushies: generally ~25–32 min stocked, ~15–16 min depleted (some travel times span multiple cycles).
- Common flowers: often several hours stocked, ~60 min depleted, with high restock-onset errors for a few items.
- Japan Xanax: ~12 min stocked, ~120 min depleted with zero conservative V151 recommendations; all 24 sampled issues had <0.60 peak scenario stock-at-landing support despite first-restock onset error around 4.7 min. No legitimate reason to reduce thresholds or claim certainty.

## Actual V157 work, not another global threshold change

New `research/v157_prequential_stock_survival_router.py` implements a strictly chronological proper-score comparison on fully **completed adjacent LOW→HIGH episodes**. For each held-out complete episode, it calculates stock ≥30 at 25%, 50%, and 75% of an earlier-only typical cycle interval, with a paired joint distribution versus a Cartesian-independent LOW/HIGH distribution fitted to **only preceding** episodes. Brier loss uses the held-out episode as future truth, not an input. Each item's stock/depletion length determines its own three elapsed evaluation horizons. This is a *first-cycle survival proxy*, not 1–3 hour multi-restock flight proof or a calibrated probability.

Predeclared, conservative hypothesis gates: at least 9 complete pairs, at least 5 initial training pairs, 4+ chronological held-out complete episodes, diversity of both stock and depletion lengths, >=0.02 average paired-vs-independent Brier advantage, paired improves at least 3 separately held-out episodes. Any failure or lack of evidence retains **independent V151**. Missing/contradictory boundaries fail closed; V145 provider continuity is preserved.

`research/v146_v145_same_issue_replay.py` calculates V157's frozen route **before** assessing subsequent stock-at-landing proxy observations. Its research candidate comes from the pre-existing independent or paired V151 forecast; it must not create additional unsupported flights. The same exact issue-time and mature arrival evidence is used to compare routed outcomes versus independent V151 and leaving immediately. It also continues reporting the original V156 choice, raw paired, V148, 1min resolution, and all 24 items.

`research/v149_v146_compact_report.py` now prints V157 paired choices, mature matched improvements and reasons for abstention (sparse/constant/not-better/paired evidence), keeping the short report. Deprecated V153 recency comparison data remain validated in result structure, but verbose recency console listing was dropped to make room for the more relevant item-specific test.

Added `tests/test_v157_prequential_stock_survival_router.py` and expanded V146 replay regression checks for no-lookahead selection, true heldout scoring, constant-interval abstention, invalid timestamps, and exact same issue/arrival comparison. A failed V157 candidate is not a game-stock miss; it is an abstention. Existing V151 default remains unchanged.

## Decision gate and next research

1. Run the pinned, bounded VM audit (once final CI passes) to confirm whether V157 now selects a genuine subset of items and whether those choices improve *matched* arrivals and waiting versus independent V151.
2. Check 24 per-item statuses and reasons; if most episodes are constant, independent sampling is a valid outcome. Do not force paired candidates, and do not select models because of their observed future result within the same evaluation window.
3. Even with favorable 600 hourly issue observations, validate on **independent completed restock episodes** and prospectively issued predictions, using source freshness and no-backfill provenance, before calling an item champion.
4. Expand beyond the two V151 sampling methods only after comparable out-of-sample metrics are grounded. Eventually restore selected improvements to experimental view **additively** with rollback while preserving original V2 stock graph, existing specialists and both website views.

## Protection

Everything remains on research branch `research/v38-full-roster-live-prep-20261009`. No production deployment, DB writes, website replacement, timer changes or purchases. Simulation fraction is not a calibrated probability.
