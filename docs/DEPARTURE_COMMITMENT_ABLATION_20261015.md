# First-proposal commitment execution ablation — October 15, 2026

**No clear replacement for the established item choices.** Replanning hurts this direct classifier on several plushies, but freezing its first target does not fix Japan. Selective gains come with long waits and reduced coverage.

Private run **38742078917**, source `6a9f2bd1d11b7bfffe17972cee3db9c75fcad794`. Same sanitized cutoff **2026-10-15 12:47:58 UTC** as direct-model run 38740796747. Every primary policy result was compared and found identical across the two artifacts. This isolates the added execution diagnostic from source-data movement or model changes.

## Protocol

All 2,016 five-minute starts per item; same eight-hour deadline. Freeze the first healthy proposal whose target is within the deadline. At departure use the heartbeat age recorded by the latest available five-minute issue, and cancel if that age plus elapsed time exceeds 180 seconds. No later model advice selects or moves the frozen target. No future arrival outcome chooses a commitment.

This is a counterfactual diagnostic, **not a recommended travel policy**: later stock/model advice is intentionally ignored. Heartbeat checks do not establish country-provider freshness. Exact departure clocks can fall after the 180-second validity of the latest five-minute issue; these are explicitly counted as cancellations. In particular, reduced coverage for committed rate/hybrid policies is partly this execution rule, not evidence that the provider was stale. Never drop these cancelled journeys from coverage.

## Direct70: replanning versus commitment

Each outcome cell is conditional success / departure coverage / mean wait. Paired wins/losses compare commitment against replanning on jointly resolved starts; abstentions, unknowns and pending journeys remain in companion JSON.

| Item | Replanned | Committed | Committed worst day | Paired wins / losses (matched) |
|---|---|---|---:|---:|
| arg:Monkey Plushie | 63.81% / 71.33% / 120m | 70.84% / 79.71% / 151m | 65.49% | 152 / 60 (1192) |
| chi:Panda Plushie | 84.34% / 71.18% / 115m | 71.53% / 81.40% / 143m | 62.67% | 28 / 181 (1323) |
| jap:Xanax | — / 0.00% / — | — / 0.00% / — | — | 0 / 0 (0) |
| sou:Lion Plushie | 78.85% / 68.75% / 115m | 65.97% / 87.05% / 148m | 58.91% | 107 / 241 (1259) |
| swi:Chamois Plushie | 56.76% / 58.93% / 142m | 67.89% / 65.23% / 172m | 55.50% | 210 / 115 (1044) |
| uae:Camel Plushie | 61.73% / 66.91% / 126m | 72.94% / 77.53% / 153m | 68.00% | 225 / 97 (1144) |
| uni:Nessie Plushie | 60.45% / 76.59% / 106m | 71.60% / 87.65% / 132m | 65.59% | 212 / 48 (1261) |
| uni:Red Fox Plushie | 77.95% / 78.17% / 106m | 71.48% / 86.16% / 130m | 67.51% | 55 / 116 (1323) |

## Diagnostic peak policy

| Item | Replanned | Committed | Committed worst day | Paired wins / losses (matched) |
|---|---|---|---:|---:|
| arg:Monkey Plushie | 63.65% / 76.98% / 108m | 68.42% / 97.02% / 174m | 58.43% | 181 / 113 (1479) |
| chi:Panda Plushie | 77.23% / 76.39% / 110m | 71.84% / 96.43% / 158m | 64.31% | 69 / 141 (1416) |
| jap:Xanax | 37.49% / 80.95% / 139m | 27.00% / 93.35% / 175m | 6.40% | 70 / 250 (1499) |
| sou:Lion Plushie | 70.34% / 83.83% / 96m | 67.72% / 96.18% / 129m | 56.30% | 140 / 186 (1550) |
| swi:Chamois Plushie | 52.92% / 75.99% / 110m | 68.05% / 94.49% / 170m | 59.06% | 261 / 61 (1341) |
| uae:Camel Plushie | 56.96% / 76.93% / 110m | 68.55% / 96.58% / 157m | 61.62% | 275 / 85 (1443) |
| uni:Nessie Plushie | 70.65% / 74.85% / 111m | 73.78% / 96.28% / 178m | 66.19% | 152 / 94 (1371) |
| uni:Red Fox Plushie | 52.11% / 75.69% / 109m | 72.62% / 96.68% / 174m | 66.78% | 261 / 18 (1284) |

## Findings

- Japan: direct peak falls 37.49% → 27.00%; paired 70 wins versus 250 losses on 1,499 jointly scored starts, with a 175-minute average wait. Established rate remains 39.48% with 71-minute wait and 99.95% coverage. Direct70 still makes no departure. Replanning churn is not a general explanation or cure for Japan.

- Chamois: freezing direct peak improves 52.92% → 68.05%, but established aligned70 remains 69.59%, 99.36% coverage and 32-minute wait versus 94.49% coverage and 170-minute wait for committed peak. This execution gain does not beat the reference.

- Camel: committed direct70 offers 72.94% success and 68.00% worst day at 77.53% coverage and 153-minute wait. Established aligned50 offers 65.81%, 62.23% worst day, 100% coverage and 4-minute wait. Keep this as a selective exploratory tradeoff; it deliberately ignores later stock advice and needs a realistic cancellation policy and a new fixed forward protocol before consideration.

- Monkey and Nessie benefit from freezing the new classifier, but still trail their established references in overall accuracy, coverage and waiting time. Panda and Lion lose substantial accuracy under commitment. Red Fox committed peak recovers much of the new model’s replanning failure, but remains below the hybrid reference average and waits almost three hours.

These results argue for item-specific execution analysis rather than combining rejected models on headline percentages. Future work should measure country-provider freshness and long-lead phase uncertainty, and only test a guarded commitment policy with rules fixed before evaluation. This ablation does not establish that ignoring new information is safe or improves future performance.

## Validation and persistence

100 CI tests passed, including commitment target freezing, replacement behavior, stale issue evidence cancellation, unknown arrivals, pending outcomes, wait limits, and full replay regressions. Chromium and compatibility workflows passed.

Artifact 11976472627, 276,715 bytes, SHA256 `f343c6c33bacd2f5b801731b6499624281cab6026494ef218d9a609761c70291`, verified before extraction. The companion JSON retains all eight items, four execution ablations, matching replanned reference summaries, seven daily slices, raw counts and paired comparisons. Primary UTC offsets remain available in the direct-model companion and full private artifact.

All counts are correlated historical cohorts, not actual player flights or confidence certification. No production changes, no automatic promotion, no changes to the routine approved source or original frozen forward protocol.
