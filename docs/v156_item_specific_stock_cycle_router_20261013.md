# V156 — item-specific stock/depletion and flight-regime research router

## Why a global upgrade is inappropriate

The 600-item-hour V155 VM audit shows genuinely different effects item by item. Paired LOW/HIGH V151 added **+6 net wins** versus independent V151 among **421 same-issued mature comparisons** (15 paired-only vs 9 independent-only), but **Chamois -3**, **Stingray -1**, **Monkey -1**, while **Red Fox +4**, **Lion +2** and **Jaguar +2**. Those are historical poll-state arrival proxies on correlated hourly checkpoints, not independent flights. Do **not** enable paired sampling for all 24 items, even though aggregate rate 337/431=78.2% is higher than independent 329/429=76.7%.

Japan Xanax still had zero departure proposals from either sampled approach; its 24 below-.60 peak-scenario supports and first-restock MAE ~4.7 minutes indicate arrival survival/long route rather than no observed stock events. Do not lower the uncalibrated .60 simulation threshold just to produce suggestions.

## Actual added research code

- `research/v156_item_cycle_profile_router.py` computes, **at each recorded issue time only**, observed median stocked lifetime, median depleted lifetime, completed LOW->HIGH pairs, flight-to-cycle ratio, stocked lifetime vs flight, and three mutually exclusive stock/depletion regimes. It does not use later observed arrival outcomes to select a model.
- V151 already supports independent or complete paired LOW/HIGH simulation. V156 makes an item-sensitive predeclared experimental choice: independent is the safe default; paired requires >=8 complete episodes with LOW/HIGH Spearman absolute rank dependence >=.65, nondegenerate durations, and consistent correlation sign in the first/second historical halves. Flights spanning >=3 typical restock cycles require >=10 pairs and rho >=.80. Item stocked lifetime <5 minutes requires >=12 pairs and rho >=.80. Infrequent depleted periods (>=90 min) require >=10 pairs. These conservative policy thresholds are **hypotheses**—not fitted parameters, calibrated success percentages or promised boosts.
- If a provisional item-specific paired model abstains, routing falls back to existing independent V151 without fabricating a below-gate recommendation.
- `research/v146_v145_same_issue_replay.py` now evaluates V156 on the **same original issue-hour** as independent V151, paired V151, fine-resolution V151, and V148, including matured matched wins/losses versus independent and leave-now. No extra simulation runs are required: routing uses existing as-of candidate outputs.
- `research/v149_v146_compact_report.py` now reports both overall routing selection/arrival outcomes and **all 24 items individually**, including observed average stock/depleted minutes and paired-route usage/wins. It will be measured on live VM before any production promotion.
- `tests/test_v156_item_cycle_profile_router.py` tests short stocked periods, multicycle long flights, source-switch-validated completed history, positive/negative interval dependence, sparse/degenerate periods, same-issue fallback and future/invalid timestamp rejection. CI alongside existing V146/V149 ensures other website/project workflows remain intact.

## Next research gate — don't cherry-pick

The correct comparison is **the router chosen before seeing the later stock states** versus always independent and always paired on exact same issued item/hour opportunities, including coverage, pending and unknown outcomes. Report per-item subgroup results and re-evaluate over **independent restock episodes and newly collected forward issue times** before promotion. Correlated 25 hourly checks cannot substantiate a single-item winner. Identify which items have insufficient evidence and retain their existing models.

Evaluate any future stock-survival gate change separately for very short stocked windows and long flights; do not globally shorten 5-minute future-stock support or lower the simulation floor without a direct counterfactual audit.

## Production safety

This is research-only on branch `research/v38-full-roster-live-prep-20261009`. Do not replace V75 champion specialists, the original V2 stock graph, the experimental 24-item dashboard, collector source, sidecar, jobs or production services. Future source-pinned, reversible **additive** integration must preserve both views.
