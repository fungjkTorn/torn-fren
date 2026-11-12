# V151 actual 24-item results and V152 direct same-issue/next-restock follow-up

## User VM output: V151 run completed read-only

At the logged as-issued first UTC item-hour cohort: 576 item-hours (24 items), V145 recovered 228 previously discarded eligible issue checkpoints, 413 V145-eligible checkpoints unscored due to fixed MC cap, 96 V145 models evaluated. The source is the supplied successful VM compact output, not synthetic CI examples.

- V151: 486/576 provisional departure candidates (84.4%), 310/401 mature known stock-at-arrival proxy hits (77.3%), 27 exclusive wins vs leave-now and 12 exclusive losses (net +15) among **386 matched, mature, same-issued** candidate/leave-now pairs.
- V148: 486/576 candidates, 289/399 known hits (72.4%), 53 exclusive wins vs leave-now and 58 exclusive losses (net -5) among **374 matched, mature** pairs.
- V145: 92 limited candidates (4 MC replays per item), 71/85 known hits (83.5%) and matched net 0. Its conditional rate is not a representative challenger ranking.
- The ORIGINAL V149 compact report had a **labeling bug**: it printed 374 'pending' V148 and 386 'pending' V151, when those numbers were matched cohort counts. From the full denominators, pending = **44 V148**, **37 V151**; unknown = **43 V148**, **48 V151**. The replay's matched counts and hit/miss totals remain valid; source code corrected and regression tested.
- Japan Xanax: 14 newly eligible V145 issue hours, still zero V151 departure candidates. This is a score/stock-survival issue, not zero observed restocks.

The two conditional observed proxy rates (77.3% vs 72.4%) are NOT yet the precise direct V151-vs-V148 head-to-head because matured outcomes can differ by recommendation time. Hourly issue hours can reuse actual stock cycles; no real flight or purchase confirmed. DO NOT promote V151 to public recommendation or claim production game accuracy.

## New independent improvements on research branch

1. `research/v146_v145_same_issue_replay.py`: exact **same item and issue time, matured both models** V151-vs-V148 wins/losses, with same-departure consistency fail-fast; splits V151 leave-NOW versus V151 FUTURE and its delayed-only incremental wins over leaving now. This isolates whether delayed departure logic adds value.
2. `research/v149_v146_compact_report.py`: now explicitly distinguishes pending vs matched counts and includes the direct V151-vs-V148 comparison, future/now counts, and individual net differences within concise 24-item output.
3. `research/v151_stable_earliest_departure.py`: adds peak scenario-stock support, timing to first maximum, count of >=.60 bins and supported adjacent five-minute bins to locate Japan Xanax's specific remaining gate without lowering it blindly.
4. `research/v152_first_restock_timing_evidence.py`: measures the **first subsequent fully observed >=30 stocked period with a verified start AND end**, skipping invalid cross-provider threshold jumps or collection gaps. Reports absolute timing error and <=1/5/15 minute rates. The future stock records are held out of the candidate model and used only for the later outcome audit.
5. `research/v146_v145_same_issue_replay.py`: loads later observed stock changes in a separate outcome-only query per item, then compares V151's first-restock median forecast to the next completed stock period. Keeps later observations OUT of issue-time model inputs. Aggregates event-level MAE and per-item MAE.
6. Added unit regressions and wired the V152 module into V85 CI. Production website pages, existing V75 specialists, graph, collector and V128 shadow have not been changed.

## What must be tested before recommending deployment

- First rerun the pinned one-shot **read-only** VM research comparison when CI for the final commit is green. The new report will include direct paired V151 vs V148; mature outcomes vs leave-now for delayed recommendations alone; observed next-restock timing MAE against completed cycles; and exact 24-item roster consistency.
- Audit unresolved/pending statuses and source freshness before treating poll-state data as in-game evidence. Ensure no lookahead or post-issue model inputs.
- If direct V151 wins on sufficient independent stocked/depleted restock events AND waits stay sensible, then conduct a private as-issued prospective trial before item-by-item deployment. Preserve both original V2 graph and current experimental 24-item dashboard.

## Safety

All new work is on branch research/v38-full-roster-live-prep-20261009. Bounded read-only VM operator stages research .py files from a pinned SHA under a private research tree only; no DB mutation or public website deployment. A future WAIT is a watch to re-confirm near departure, not an immediate instruction to fly.
