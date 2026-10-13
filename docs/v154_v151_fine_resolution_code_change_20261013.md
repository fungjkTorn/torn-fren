# V151 targeted code improvement: finer departure resolution (research only)

## Decision using genuine V153 VM findings

V153 on 600 issue-hour observations (24 items) found that recent 3, 5, and 10 completed stock/depleted periods were worse overall than V151 first-restock median: V151 MAE 23.3m on 337 fully bounded next-restock starts; recent3 29.3m on 316 matched, recent5 28.1m on 329, recent10 28.6m on 331, all bounded 23.2m on 337 (negligible 0.1m). These are historical, correlated, provider-limited proxies, not independent game results. **Do not deploy V153.** V151 departure timing still recorded +20 exclusive hit delta vs V148 on 388 aligned mature cohorts, and +16 net vs leave-now on 399 aligned cohorts. Japan Xanax zero departure candidates because simulated peak stocked-arrival support <0.60 across 24 examined times, despite 4.7m next-restock onset MAE. Do not lower threshold to force a recommendation.

## Actual code adjustment, not another speculative model version

`research/v151_stable_earliest_departure.py` now has a **default-off one-minute departure grid** option through `departure_step_seconds=60` (default remains 300 seconds). It uses exactly the same stable-seeded HIGH/LOW future-stock scenarios, same 10s arrival grace, same 0.60 scenario support floor, same 8h horizon, and same 5min replan cadence. It requires TWO future stock-support checks **300 seconds apart**, independent of the 60s search step, so finer resolution does not quietly weaken the prior stability gate. Immediate leave-now remains eligible on a single supported bin, unchanged. Different output does not establish player flight success.

`research/v146_v145_same_issue_replay.py` evaluates both 5min and 1min variants on each same original V128 item/issue cohort, tests the common 5min grid forecast support for equality, records earliest departure selection and arrival proxy for each, and reports matched 1min-only and 5min-only hits/misses, newly supported 1min candidates, and whether delayed departure improves over leaving immediately. This is the correct comparison; do not just inspect the number of extra departure suggestions.

`research/v149_v146_compact_report.py` now includes a one-line global 1min-vs-5min same-issued comparison and a per-item exclusive-wins delta. Synthetic regression tests assert that `score_bins_5min == score_bins_1min[::5]`, future candidate stock support remains 5min apart, and the 1min candidate cannot be later than the equivalent 5min candidate.

**Production is not modified.** Continue to preserve both deployed original V2 stock graph and experimental 24-item dashboard, their existing candidate sources and V75 specialists. The old V151 5min behavior remains the default until real same-issue and prospective proof.

## Promotion requirements

1. First check all project CI jobs and the read-only VM one-shot replay. Look for paired rather than unpaired lift on mature first-item-hour arrival proxies, count pending/unknown, per-item win/loss/abstention and median waits.
2. Reconfirm results on independent restock cycles and forward issue-time records, not just overlapping hourly snapshots. Check item-specific false confidence and country-provider freshness.
3. Japan Xanax is a separate stock-survival problem; fine grid may or may not help. Its ~4.7m restock MAE does NOT imply an attainable >=30 landing stock. A 0.60 gate remains uncalibrated and cannot be claimed real-world hit probability.
4. If a candidate wins fairly, implement source-pinned *additive* integration into existing deployed V2 graph and experimental page with rollback; no code replacement or production deployment without explicit authorization.
