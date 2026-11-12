# V158 — flight-horizon item-specific model-selection audit (research only)

## Latest actual VM result provided by owner

V157 completed 600 item-hour issued cohorts (24 items) read-only: V151 independent 504/600 provisional departure proposals, 316/413 mature observed >=30 stock-at-arrival proxy hits (76.5% conditional). V151 versus leave-now 26 exclusive wins vs 13 losses (net +13), vs V148 52 wins vs 36 losses (net +16). These are overlapping historical issue checkpoints, not independent player flights or prospectively frozen provider data.

Raw paired V151 achieved 321/414 mature proxy hits, with 12 paired-only vs 9 independent-only wins on mature same-issued opportunities (+3). V156 correlation-based per-item router selected paired on **zero** of 504 flights. V157 first-cycle Brier selector selected paired on **zero** of 504 flights; for all 600 item-hour issues it reported NO validated first-cycle Brier improvement. Its single-cycle 25/50/75%-of-typical-cycle objective does not directly evaluate real flight-time stock across multiple cycles. Do not game its cutoff simply to promote a model.

## V158: direct implementation change

New `research/v158_flight_horizon_router.py` uses only **V145 fully observed, directly bounded consecutive depleted and stocked intervals** available BEFORE each issue. At chronological historical LOW starts, it fits paired and independently sampled LOW/HIGH distributions using only PRECEDING completed cycles. It scores held-out true stock >=30 at the actual country-specific outbound flight duration +10s grace, and flight +5-minute and +15-minute departure offsets. For long flights, the forecast can traverse multiple complete depletion/stocked episodes. Any collector gap, missing future bounded observation or short unobserved tail ABSTAINS rather than fabricates truth. Historical Monte Carlo fractions are not calibrated probability nor player purchase proof.

Frozen research selection gate: at least 6 training episode pairs, 4 distinct evaluable future historical LOW origins, 12 maximum heldout origins, 40 deterministic scenarios per method, at least 0.015 lower mean paired Brier and 3 heldout origins improved. When false, choose independent V151. Do not use the original current issued departure outcomes as model-selection input. This is a more direct proxy than V157 but still not guaranteed player landing outcome; horizontal flight offsets are *hypothetical origins at past depleted onsets*, not guaranteed original V128-issued checkpoints.

The existing same-issue `research/v146_v145_same_issue_replay.py` evaluates V158's chosen model at all original V128 issue times and reports mature matched stock-at-arrival outcomes against independent V151, plus matched versus leave-now. V156 and V157 are retained for transparent comparisons. The compact 24-item report explicitly shows which items V158 chooses as paired, its mature proxy hit fraction, exclusive head-to-head wins/losses, and pending/unknown outcomes. It never rewrites historical V128 issue records.

The model's regularity or lack of selection is evidence. If Brier scores provide no useful difference because cycles are deterministic (typical plushies 25-32min HIGH and ~15-16min LOW, flowers multi-hour HIGH ~60min LOW, Japan Xanax ~12min HIGH ~120min LOW), do NOT force paired. More complicated model selection is warranted only if it lifts independent episode/flight results.

## Next research and product gate

1. CI and bounded read-only VM audit must finish. Do not claim a V158 success percentage from synthetic tests or V157 results. The VM comparison has capped CPU, no production changes, and full item-level metrics.
2. Independent validation **by complete restock episode** or prospective as-issued private shadow. Hourly issues overlap cycles, conditional hit rates are not independent 24-item model rankings.
3. Japan Xanax remains separate: V151 peak >=30 arrival support below 0.60 on 24 issued checks; flight survival on a ~12-minute stocked phase with ~120-minute depleted phase requires specialist timing and credible uncertainty calibration. Do not lower simulation floor for report coverage.
4. Only actual per-item improvements may be added to the experimental website with a reversible bridge, while preserving BOTH the original V2 stock graph and existing multi-item dashboard, production specialists, event collectors and their normal paths.

No production deployment, API calls, DB writes, scheduler changes or purchases in V158.
