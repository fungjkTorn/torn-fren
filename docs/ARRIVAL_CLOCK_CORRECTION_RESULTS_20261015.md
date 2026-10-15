# Long-lead past-error clock correction results — 2026-10-15 UTC

Numerical source `a73adb6d786e0e7e710fcc99ec8c70e9e8319885`; private [run38678053922](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38678053922). All95 source tests, browser and compatibility workflows passed.

Four variants were fixed before results: rate_recent, rate_stable, hybrid_recent and hybrid_stable. Each learns a correction from31 fixed one-minute offsets in[-900,+900]s, using only fully matured past UTC-hourly counterfactual forecasts in the same lead bucket. Deduplicate by observed physical phase and lead bucket. Recent uses up to32 trials with12 paired-known labels/80%coverage and5-point net gain; stable uses up to64 with24 paired-known, plus12 paired/80%coverage and2-point gain in EACH chronological half.

Training labels describe fixed hypothetical departures requiring later source rechecks, not player execution or the replanning objective. Reported arrival performance uses the same five-minute replanning evaluator,180s source expiry and8h maximum wait. All2016 five-minute starts per item overlap heavily; counts are NOT independent flights, purchases or calibrated prospective probabilities.

Physical depletion remains positive→exactly0 and replenishment0→positive. These are departure-only corrections, not independently validated restock/depletion timestamps. Baseline event streams remain references. Current observed-stock survival stays separate. No production route, publisher, collector or frozen future-window source changed.

Reference policies were selected from the previous all-start report before retrieving this run. Chamois uses the preceding aligned70 balanced lead, Camel the aligned50 speed/day-floor lead; other items keep their previous references. All comparisons below use the same current snapshot, so differences versus older snapshots must not be assigned solely to code.

Snapshot cutoff1792035740 (2026-10-15T03:42:20.000Z; October14 23:42:20 EDT). Seven-day replay,33 focused policies,24 items. Entire private run SUCCESS. Results were recovered from private artifact11947722641 after large-log retrieval closed; archive SHA2568c335f5785fe384e2ccd2f44a4b82480a03becf28fb84e660c563f26fbf8b153 verified and JSON model_sha matched the pinned source. No raw stock database is in the published scorecard.

## Japan: reject the correction family

| Policy | Successes / resolved | Arrival success | Departure coverage | Wait min | Worst day |
|---|---|---|---|---|---|
| zero_rate_current_quarter | 705/1878 | 37.54% | 99.85% | 71 | 8.68% |
| zero_hybrid_current_rate_current_quarter | 632/1859 | 34.00% | 99.85% | 71 | 8.68% |
| zero_path_residual_rate_recent | 285/1931 | 14.76% | 99.85% | 79 | 2.08% |
| zero_path_residual_rate_stable | 628/1878 | 33.44% | 99.85% | 78 | 8.68% |
| zero_path_residual_hybrid_recent | 478/1883 | 25.39% | 99.85% | 76 | 8.68% |
| zero_path_residual_hybrid_stable | 606/1859 | 32.60% | 99.85% | 71 | 8.68% |

The same-snapshot rate reference scored37.54%; these new variants scored14.76–33.44%. Against their own underlying reference: rate_recent27 wins/473 losses on1878 matched starts; rate_stable0/77 on1878; hybrid_recent52/182 on1809; hybrid_stable0/26 on1859. Reject all four as Japan improvements.

Both learners enrolled132 unique phase/lead trials and matured128, with4 pending. Nonzero correction usage: rate_recent894/2016 issues(44.35%); rate_stable155/2016(7.69%); hybrid_recent966/2016(47.92%); hybrid_stable226/2016(11.21%). This was an active failed experiment, not merely insufficient data or universal fallback. These are issue counts, not executed-trip counts.

The final rate_recent >=4h fit still reports a600s correction and13.79-point training gain on29 paired known trials. That local training statistic is NOT evidence of reliable future departure outcomes. Stable gates reduced the damage but did not produce an improvement. As-issued scores also fell(rate_recent24.87% vs37.85% rate); replanned score fell further to14.76%. These observations do not establish a single cause. The potential mismatch between fixed counterfactual training and repeated decision updates remains a research concern. No claim that a constant timing offset solves Japan's long-flight uncertainty.

## Plushie findings

- **Lion rate_recent**:1314/1865=70.46% vs69.22% shared-regime70;99.85% vs100% departure coverage;11vs17min wait; worst day60.22% vs55.99%. Paired333 wins/302 losses on1794 matched starts against regime70;193/167 on1808 against rate. Small balanced research lead, not a reliability breakthrough.
- Lion rate_stable:69.80%,99.95% coverage,9min wait,60.66% worst day; paired276/270 against regime70 and80/62 against rate. The earlier aligned50 remains a separate faster/lower-average alternative; no universal replacement is selected.
- **Chamois aligned70 remains preferred** at70.47%,100% coverage,36min wait and55.59% worst day; corrections reach at most60.11%. **Camel aligned50 remains preferred** at66.05%,100% coverage,4min wait,62.99% worst day; corrections reach at most63.35% with11min wait and52.82% worst day.
- **Panda shared-regime80 remains86.31%; Nessie shared-regime70 remains77.08%; Monkey local70 remains71.85%; RedFox hybrid remains73.11%.** No correction variant beats those references. Some stable variants exactly reproduce their underlying reference, which is not a new gain.
- Preserve strong existing alternatives. Tribulus rate_recent's apparent100% score has92.56% departure coverage and119min wait, versus local80's99.63%,100% coverage and52min wait; do not replace the faster broad-coverage reference on headline percentage alone.

## All24 fixed comparisons

Each cell is resolved historical arrival success / departure coverage. References were fixed before retrieving this experiment; they are research choices, not deployed assignments. Exact counts, every day/offset, paired outcomes, fit maturity and issue-level correction counts are in [the machine-readable scorecard](ARRIVAL_CLOCK_CORRECTION_RESULTS_20261015.json).

| Item | Reference policy | Reference | Rate recent | Rate stable | Hybrid recent | Hybrid stable |
|---|---|---|---|---|---|---|
| arg:Ceibo Flower | zero_path_analog80 | 99.45% / 99.75% | 84.06% / 98.26% | 84.64% / 98.26% | 83.88% / 87.55% | 83.88% / 87.55% |
| arg:Monkey Plushie | zero_path_analog70 | 71.85% / 96.28% | 63.40% / 99.75% | 64.05% / 99.75% | 59.46% / 99.75% | 60.65% / 99.75% |
| can:Crocus | zero_rate_current_quarter | 100.00% / 90.77% | 100.00% / 90.77% | 100.00% / 90.77% | 100.00% / 87.30% | 100.00% / 87.30% |
| can:Wolverine Plushie | zero_path_analog80 | 96.70% / 99.80% | 82.20% / 99.80% | 83.72% / 99.80% | 89.62% / 99.80% | 88.81% / 99.80% |
| can:Xanax | zero_hybrid_current_rate_current_quarter | 96.49% / 99.50% | 96.13% / 99.50% | 96.13% / 99.50% | 96.49% / 99.50% | 96.49% / 99.50% |
| cay:Banana Orchid | zero_path_analog80 | 99.84% / 95.39% | 98.62% / 95.93% | 98.62% / 95.93% | 98.35% / 95.93% | 98.35% / 95.93% |
| cay:Stingray Plushie | zero_path_analog80 | 98.23% / 100.00% | 92.41% / 100.00% | 92.57% / 100.00% | 90.31% / 100.00% | 92.33% / 100.00% |
| chi:Panda Plushie | zero_path_regime80 | 86.31% / 96.88% | 64.16% / 100.00% | 65.12% / 100.00% | 65.25% / 100.00% | 65.38% / 100.00% |
| chi:Peony | zero_hybrid_current_rate_current_quarter | 96.40% / 100.00% | 85.48% / 96.03% | 85.48% / 96.03% | 96.40% / 100.00% | 96.40% / 100.00% |
| haw:Orchid | zero_hybrid_current_rate_current_quarter | 99.79% / 97.52% | 99.78% / 97.27% | 99.78% / 97.27% | 99.79% / 97.52% | 99.79% / 97.52% |
| jap:Cherry Blossom | zero_path_analog80 | 96.66% / 100.00% | 80.08% / 100.00% | 80.08% / 100.00% | 93.36% / 97.02% | 93.36% / 97.02% |
| jap:Xanax | zero_rate_current_quarter | 37.54% / 99.85% | 14.76% / 99.85% | 33.44% / 99.85% | 25.39% / 99.85% | 32.60% / 99.85% |
| mex:Dahlia | zero_rate_current_quarter | 100.00% / 98.96% | 100.00% / 98.96% | 100.00% / 98.96% | 100.00% / 94.84% | 100.00% / 94.84% |
| mex:Jaguar Plushie | zero_path_analog80 | 98.81% / 99.80% | 97.08% / 99.95% | 96.46% / 99.95% | 97.17% / 99.75% | 96.90% / 99.75% |
| sou:African Violet | zero_path_analog80 | 98.80% / 96.28% | 88.84% / 91.07% | 88.84% / 91.07% | 96.50% / 94.10% | 96.50% / 94.10% |
| sou:Lion Plushie | zero_path_regime70 | 69.22% / 100.00% | 70.46% / 99.85% | 69.80% / 99.95% | 68.06% / 99.80% | 67.94% / 99.90% |
| swi:Chamois Plushie | zero_path_aligned_analog70 | 70.47% / 100.00% | 60.11% / 100.00% | 59.36% / 100.00% | 58.81% / 100.00% | 57.52% / 100.00% |
| swi:Edelweiss | zero_path_analog80 | 97.52% / 100.00% | 80.21% / 99.75% | 80.21% / 99.75% | 87.30% / 99.75% | 87.30% / 99.75% |
| uae:Camel Plushie | zero_path_aligned_analog50 | 66.05% / 100.00% | 61.46% / 99.95% | 63.35% / 99.95% | 59.92% / 99.95% | 62.88% / 99.95% |
| uae:Tribulus Omanense | zero_path_analog80 | 99.63% / 100.00% | 100.00% / 92.56% | 95.38% / 92.61% | 84.66% / 100.00% | 84.66% / 100.00% |
| uni:Heather | zero_path_analog80 | 99.72% / 97.32% | 99.44% / 92.26% | 99.44% / 92.26% | 81.76% / 94.79% | 85.38% / 94.79% |
| uni:Nessie Plushie | zero_path_regime70 | 77.08% / 99.95% | 71.82% / 99.95% | 71.70% / 99.95% | 68.88% / 99.95% | 68.88% / 99.95% |
| uni:Red Fox Plushie | zero_hybrid_current_rate_current_quarter | 73.11% / 100.00% | 72.03% / 100.00% | 72.14% / 100.00% | 72.78% / 100.00% | 73.11% / 100.00% |
| uni:Xanax | zero_hybrid_current_rate_current_quarter | 99.94% / 88.59% | 99.94% / 85.47% | 99.94% / 85.47% | 99.94% / 88.59% | 99.94% / 88.59% |

## Interpretation, reproducibility and next work

Timing corrections are rejected for Japan; retain the small Lion lead for a separate fresh-data test. Chamois/Panda/Nessie/Monkey/Camel/RedFox and the strong items retain their prior research references. No production route, publisher, collector or gameplay behavior changed. All timing still anchors physical depletion at exactly0; departure-only policies do not inherit independent event-timing accuracy.

Each replay starts correction history EMPTY at its issue-window start; the first part is a cold start. The fitted state is not persisted as a live worker. Window length/warmup must be specified for any subsequent future validation. Reconstructed labels and overlapping cohorts are not pristine holdouts or independent player flights. Unknown, pending and abstaining outcomes remain explicit. The extra stability gates are heuristics, not statistical certification.

Next Japan research should measure forecast-error/phase uncertainty conditional on phase and future-cycle lead, and evaluate learners against the actual replanning objective. These are unimplemented directions, not accuracy claims. Source-country upstream freshness remains unverified by global successful-poll heartbeats; sampled event clocks are not exact game-event seconds.

The ongoing fixed_forward_v1_20261015 stays on original source87f4c6ee34f6ee598cbcc7daf93b9355f46bbd04 and original dates; it does NOT validate this new family. No model/window changes were made. New variants need a separate predeclared period.

An optional repeated --item-key filter was added afterward in source0130d8af1b756e8bcad596e7dc7c849d24d7ea33, with96 tests plus browser checks. It preserves default full-roster behavior, validates exact unique identities, retains all24 peers for shared context and explicitly labels subsets. Subset/prefix results match exactly in the regression. The private numerical experiment above used full24-item sourcea73adb6d786e0e7e710fcc99ec8c70e9e8319885,95 tests; the filter is not enabled by that workflow and did not change these results.
