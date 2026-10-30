# Approved overnight cleanup: fixed experiment V1

The user approved the four-part plan October 29, 2026. These choices are fixed
before comparative accuracy results; they are not a configuration tournament.

Source: `torn-fren-challenger-history-20261030T020202Z.sqlite`, SHA256
`543b67f1fe4874961130948ecee1d9df4870efe80599726f13828b19da8a6687`.
Use the identical October 22–29 week and 300-second issuance grid. Preserve the
saved baseline and real raw observations. Recompute forecasts from causal
snapshots and score immutable recommended-departure trips with live V5.

## Comparators

- Saved full-history baseline: existing completed next-six replay.
- `clean-full`: cleanup with all earlier qualified history equally weighted.
- `clean-recent7`: identical cleanup with exponential weights and a fixed
  seven-day half-life for phase durations and signed net stock rates. Older
  samples retain positive weight; no history is cut to 48 hours.

The named native model configurations and their full-history inputs stay pinned.
Recency weighting affects the shared buying-window estimator, not replacement
native models. Full training history is retained.

## Fixed cleanup rules

1. Evaluate actual ten-minute observed-stock blocks. Successful poll coverage
   (<=180-second gaps), fresh country clocks at both endpoints, continuous
   provider and no known collection gap are required. Start quantity must exceed
   30. Include flat and rising quantities. Exclude learned refill/reset boundaries
   from net-rate windows. Refill signatures are learned before the first issue
   of the replay and retained, matching the evidence-profile convention.
2. Estimate median and upper-quartile signed net loss rate. For arrival risk,
   also honor the latest complete block when it is no older than one block plus
   the 180-second confirmation allowance: use the maximum of its loss rate, the
   historical upper quartile, and zero. This lets rapid current depletion affect
   the current-stock estimate without depending on future gains. Labels close at least
   180 seconds before issue, permitting confirming observations without using
   future records. All qualifying older blocks remain available.
3. UK consistently uses current-quantity arrival support, including when the
   phase onset is unknown. Other items can use it when phase timing is unknown
   or has exceeded historical survivors. Project quantity at actual flight
   arrival with the upper-quartile net loss rate, clipped at zero: future gains
   are not required for the lower estimate. A projected quantity >=31 supports
   immediate travel. Do not invent a depletion time or restock onset; issue
   immediate-only advice requiring fresh reconfirmation.
4. For regular items with a known current phase, use the lower-quartile remaining
   phase lifetime and upper-quartile quantity-loss projection to estimate the
   current buying-window end. This directly tests the tiny-headroom South Africa
   issue. It changes the window estimate, not a confidence gate after event
   selection. Keep the original median end in provenance.
5. For the first reachable future window, retain the pinned native proposal.
   Where the upper-quartile restock start overlaps the lower-quartile stock end,
   clamp the native arrival inside that core and the original feasible window.
   If the uncertainty core is empty, retain the native proposal and disclose it.
   Never skip the selected restock on a low score or a lack of core overlap.

No synthetic observations, altered stock records, shifted old outcomes,
post-arrival grace, invented refreshes, or actual-player departures are used.
The newly recommended trips must be generated and frozen by replay.

## Evaluation and checkpoints

Use real-data pilots at the week start, midpoint and end. Verify all six native
identities, full-history flags, exact flight geometry, stale-snapshot behavior,
causal label cutoffs and UK inclusion of flat/rising blocks. Regression-rescore
the saved baseline after the additive evidence representation change.

Run each variant through all 2,017 clocks per item with resumable JSONL archives.
Record code/source hashes and checkpoint commits. Compare known success,
unknown/pending, every early/late miss, advice coverage and distinct opportunities.
Treat the already-inspected week as retrospective research, not a blind holdout.
Forward confirmation remains necessary; no automatic live promotion follows a
higher historical percentage. Record failures and retain the baseline if a
cleanup variant is worse.

## Checkpoint consistency addendum

Refill signature calibration is fixed at the replay start (1792720800), including
on resume. Country clocks are copied by country through the as-of cutoff, with
no later receipts. Twelve real-data midpoint forecasts matched continuous and
resumed execution exactly. This is a reproducibility correction, not a change
selected from accuracy results. The initial unscored partial runs are retained
under `clean-full` and `clean-recent7`; comparative results will use fresh
`clean-full-v3` / `clean-recent7-v3` directories and a single code checkpoint.
No forecast observations or saved forecast rows were edited or re-scored into a
different recommendation.

The V2 partial archives are also retained and excluded from final accuracy
results. The latest-observed-loss response was completed during implementation
review, before inspecting comparative arrival accuracy. No model settings were
chosen from those partial outcomes. Final comparative archives use V3 paths.
