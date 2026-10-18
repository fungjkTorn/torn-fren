# Japan training freshness and clean half-phase experiment

The training audit used source3384a04a7e96666554cc2758422b8abf92af185d, private run39090873523, on the same inspected development window1791956700..1792215600 with fixed truth cutoff1792254014. This is an evidence audit, not an accuracy result.

The original model accepted four new full physical-zero/restock/physical-zero cycles over these three days. It started with74 completed cycles and ended with78. At the first issue, the newest accepted whole cycle was56.34h old; at day1 it was80.34h old. The recency-weighted mean whole-cycle age was169.63h at the start and102.17h at the end. A short recency half-life cannot create recent completed training tuples which were never accepted.

There were140 provider-switch resets in the inspected window. These interrupted28 open zero-cycle states and13 open positive-cycle states (overlapping states, not41 independent completed-cycle losses). Original prerequisites reproduce451 READY and413 UNKNOWN_PHYSICAL_PHASE issues. No collection-gap or positive-topup resets occurred in this specific window.

Clean separately observed half phases provided six newly completed zero spells and18 newly completed positive spells, versus four whole tuples. Zero spells require a directly observed positive->exactly0 anchor and same-provider continuity to a directly observed0->positive transition. Positive spells require a directly observed0->positive start, same-provider continuity and no topup until exactly0; their >=30 availability end is stored separately. A positive half can be accepted when its earlier depleted onset was left censored. These halves do not establish complete observed whole cycles and are never relabeled as such. Provider switches and gaps cannot join them.

## Predeclared modeling ablation

Train separate last96 clean zero and last96 clean positive duration distributions. Preserve the joint positive-duration / >=30 availability pair. Model successive low/high durations independently, explicitly an assumption, not an observed pairing. Compare72h and6h recency half-lives, each with original peak and absolute.60 support gates. This is four research candidates. The longer-memory variant separates changed training representation from the shorter recency change.

Require16 clean halves of each type and four phase-age survivors. Keep the original strict current phase and existing180s zero-agreement current-phase handoff. Never infer a new depletion time, bridge providers in training, or hold expired advice. True depletion0, buy quantity>=30 through+10sec, five-minute cadence, publication15sec, forecast/source TTL300/180sec, eight-hour wait and the same864 visitor starts remain unchanged.

Exactly marginalize the empirical alternating process at integer-second resolution: cycle kernel is the product distribution of low/high durations; compute renewal recurrence and convolve with the buy-availability reward. Avoid seeded path selection and accumulated time-grid rounding. Compare original sequence, original handoff, leave-now, plus four candidates; reproduce historical control fingerprints. Report unknowns, daily slices, wait, coverage and distinct departure concentration. Same inspected development days; no independent validation or automatic promotion. Cleaner partial intervals may still have censoring/selection bias and more training rows do not establish better accuracy.

Tests independently enumerate small alternating paths to verify both physical-zero and positive-onset kernels, check the exact buy-end+10 boundary, current phase age, future-completion exclusion, unknown-phase abstention and current-stock<30 handling. The audit has separate tests proving partial intervals never become manufactured whole cycles or cross provider/gap/topup boundaries.

## Completed comparisons: no promotion

Half-phase run39091034626, source1b6c849163e89472589843a027a667beae923345, completed52.24sec; both original fingerprints reproduced. Artifact12121943961, verified ZIP SHA25645d8bd55a861fc4363d3eda660713ef3f672d15731cd0deb3449363daedf911b.

| Candidate | Success/known | Unknown | Coverage | Mean wait, min |
|---|---:|---:|---:|---:|
| Half phases,72h peak |369/800 (46.13%)|53|98.73%|106.0|
| Half phases,72h .60 |0/0|0|0%|—|
| Half phases,6h peak |233/665 (35.04%)|0|76.97%|155.4|
| Half phases,6h .60 |285/745 (38.26%)|0|86.23%|183.0|

Reject all four. Peak72h chronological known success41.70/69.31/27.43%;6h peak0/70.83/10.07%;6h .6040.68/64.80/10.42%. These are correlated visitor-start outcomes, not player flights. More fresh positive halves did not solve a poorly observed depleted duration or loss of cross-phase sequence information.

## Current snapshot corroboration

Run39091175781, sourceeb7fe161da5c6f12550c5449f196a455fc9ed6a1, audits the latest snapshot day1792204200..1792290300 with cutoff1792290465. There are zero new strict full cycles, zero clean completed zero halves and five clean positive halves. Latest strict whole cycle at1792182013 is30.08h old at window end.76 provider resets;129/288 issues READY and159 unknown current phase. This is not an arrival-accuracy test and not a read of the owner's shadow journal.

Artifact12123111050, verified ZIP SHA2562035b2545f0a568d8e5b0f15461de25f38c1c913b668f39f72e53570e390ac08. Its manifest has no country-clock metadata keys. This does not prove whether logging is active in production; the installed exporter may not expose it. Country-specific freshness remains unverified in this research view.

## Single agreeing-zero training handoff: no new cycles or score improvement

Source787f8f908a23c5cb36c67de7c3477e02bf3b97c4, run39091239930. A distinct explicitly relaxed-provenance experiment permits one provider switch per cycle only when both adjacent observations are0, within60sec, healthy global polls and no collection gap. The original positive->exactly0 onset must already have been observed; initial zeros cannot create a depletion anchor. A second switch, positive switch, topup, missing polls or longer gap disqualifies the tuple. Current-phase borrowing matches original handoff180, so training representation is the intended ablation. This is not provider-clock certification.

The guard preserved22 agreeing-zero switches across warmup+development+followup but completed zero bridged training cycles. Accepted counts remained74->78, identical to strict history. Outcomes remained exactly518/659known (78.60%),76.27%coverage,0unknown,21distinct departures. No benefit and no promotion; do not call unchanged cohorts an accuracy gain. It does not justify loosening all continuity guards. Runtime52.38sec, both original controls reproduced.

Artifact12123151034, verified ZIP SHA25687c2bada8d5660dfc3a0a18380f0b99bd8a3a61d8ed2bae019766d2a1402a20c. The three latest runs share sealed snapshot SHA256f30e79bd0881c8e9b7cc2ff69b18dce9368e7f84a410cbf8039cb25ad9ae9e62. Original initial audit artifact12122831950, verified ZIP SHA2566c8016f3eda8247166682e0cd3fb8c5f788c813c7fcd857aefe05078a5feed43.

Six training-audit, five half-renewal and five training-handoff tests pass. Dedicated safeguards and all compatibility workflows for787f8f908a23c5cb36c67de7c3477e02bf3b97c4 passed. Existing owner journals and production services were not changed.

Next engineering target is observing provider-specific clocks during unchanged zero quantities and establishing defensible continuity, not assuming global poll success certifies a provider. The Oct15 country-clock implementation and minimal activation patch are already prepared; production activation/export installation has not been established here and requires host preflight and the owner's collector-change approval. Do not silently restart the collector, broaden research ACLs, infer country clocks from receipt timestamps, or claim that fixing this learning gap alone will fix149min arrival error. Historical clean-source intervals and the separate long-lead uncertainty problem remain relevant.
