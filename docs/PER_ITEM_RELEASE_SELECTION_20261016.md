# Per-item release selection and integration audit — October 16, 2026

User direction: retain each item's stronger model, prioritize flowers/plushies, and keep Japan Xanax research separate. A research winner must fit the graph, countdowns and departure system before release. No production assignments or frozen protocols changed.

## Verified forward results

Run [38925288000](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38925288000) completed at 15:51 UTC. Compact artifact 12056389503 SHA256 `389a5553447392752ce23dcbd094d8c8002583eddfc1ed06aaa5c42d61ce5162` was verified. Source `87f4c6ee34f6ee598cbcc7daf93b9355f46bbd04`; 288 five-minute starts/item for the predeclared October 14 22:30–October 15 22:30 EDT issue window. Outcomes are reconstructed sampled stock >=30 at simulated arrival, not purchases or actual live issuance. Starts are correlated. Physical depletion remains positive to exactly zero.

The fixed regime70 comparison improved 4 items and worsened 19; Japan Xanax made no departures. Regime80 improved 3, worsened 18, tied 2, with Japan unscored. Do not replace all references. These comparisons do not evaluate the newer Camel tree or Chamois cycle candidate.

| Item | Analog70 → regime70 success | Coverage % → | Wait minutes → | Matched wins / losses |
|---|---:|---:|---:|---:|
| arg:Ceibo Flower | 100.00% → 95.77% | 100.0 → 100.0 | 43.7 → 42.0 | 0 / 12 |
| arg:Monkey Plushie | 75.52% → 45.71% | 100.0 → 100.0 | 30.1 → 67.1 | 9 / 92 |
| can:Crocus | 98.26% → 96.86% | 100.0 → 100.0 | 14.5 → 10.3 | 0 / 4 |
| can:Wolverine Plushie | 96.49% → 94.76% | 100.0 → 100.0 | 14.8 → 15.0 | 7 / 12 |
| can:Xanax | 97.39% → 96.27% | 94.4 → 94.4 | 106.0 → 104.7 | 1 / 4 |
| cay:Banana Orchid | 100.00% → 96.88% | 66.0 → 67.4 | 126.1 → 122.3 | 0 / 3 |
| cay:Stingray Plushie | 97.83% → 95.82% | 100.0 → 100.0 | 7.6 → 10.4 | 1 / 7 |
| chi:Panda Plushie | 70.36% → 68.93% | 100.0 → 100.0 | 10.7 → 8.0 | 25 / 29 |
| chi:Peony | 100.00% → 90.75% | 100.0 → 100.0 | 22.3 → 12.9 | 0 / 26 |
| haw:Orchid | 93.33% → 94.74% | 100.0 → 100.0 | 36.5 → 38.0 | 5 / 1 |
| jap:Cherry Blossom | 100.00% → 92.01% | 100.0 → 100.0 | 84.4 → 79.9 | 0 / 23 |
| jap:Xanax | unscored → unscored | 0.0 → 0.0 | — → — | 0 / 0 |
| mex:Dahlia | 99.65% → 98.60% | 100.0 → 100.0 | 6.3 → 5.5 | 0 / 3 |
| mex:Jaguar Plushie | 97.86% → 97.50% | 100.0 → 100.0 | 6.9 → 9.4 | 0 / 1 |
| sou:African Violet | 100.00% → 94.41% | 99.7 → 99.7 | 122.4 → 117.2 | 0 / 0 |
| sou:Lion Plushie | 85.66% → 70.71% | 100.0 → 100.0 | 13.8 → 21.3 | 1 / 44 |
| swi:Chamois Plushie | 83.03% → 87.86% | 96.9 → 100.0 | 90.8 → 97.7 | 21 / 14 |
| swi:Edelweiss | 88.42% → 83.16% | 100.0 → 100.0 | 32.3 → 28.3 | 1 / 16 |
| uae:Camel Plushie | 75.09% → 81.21% | 100.0 → 100.0 | 18.0 → 42.7 | 39 / 22 |
| uae:Tribulus Omanense | 98.95% → 93.33% | 100.0 → 100.0 | 55.3 → 52.3 | 0 / 16 |
| uni:Heather | 98.93% → 92.23% | 100.0 → 100.0 | 43.4 → 35.9 | 0 / 19 |
| uni:Nessie Plushie | 56.52% → 57.95% | 100.0 → 100.0 | 15.4 → 18.7 | 33 / 27 |
| uni:Red Fox Plushie | 95.02% → 71.02% | 99.3 → 100.0 | 87.5 → 19.0 | 4 / 72 |
| uni:Xanax | 71.93% → 65.85% | 100.0 → 100.0 | 43.1 → 22.6 | 18 / 36 |

The four regime70 gains are Orchid, Chamois, Camel and Nessie. All add waiting. Chamois adds unknown outcomes (2→8), Camel reduces them (7→6), Nessie reduces them (12→5); Orchid remains 3. Regime80 Camel reaches 100% resolved success but covers only 51.4% of starts with 166.1 minutes average waiting. It is not a universal default or guarantee.

## Integration finding

`build_travel_event_snapshot.prepare` accepts explicit per-item event histories and flight adapters. Default physical-zero history is `true_zero_all`. It does not bind detached zero_path/tree policies into live departure generation. `travel_read_model.build_board` consumes event forecasts and derives departures through the flight adapter. An arrival-only model cannot be relabeled as that full event stream, and its arrival rate must not be presented as restock/depletion timing accuracy.

`per_item_readiness` previously assessed nine legacy event/adapter policies while the focused benchmark often contained only one of those nine. It now exposes evaluated/missing/outside-map coverage and separate all-five-minute arrival evidence, including unknown, pending, abstention, waiting and chronological slices. Existing legacy gates and keys remain for compatibility. A legacy status is explicitly not a complete arrival ranking. No new automatic assignment or model selection threshold was added.

## Concrete release path

1. Preserve item incumbents where challengers regress; retain rejected models in the comparison record. Do not select the highest inspected percentage automatically.
2. Separate default fast departures from optional patient alternatives; disclose added wait, missing coverage and unknown mass. Evaluate complete event timing separately.
3. Integrate an explicitly selected departure policy into a precomputed shared snapshot with source SHA, item, issue time and flight duration. Its adapter must carry real model-issued departures/arrival windows, abstentions and freshness; it must not fabricate restock events from departure scores. Keep event graph/timer provenance distinct and verify landing = departure + flight.
4. Exercise original V2, experimental board and Travel Decisions consumers on that exact snapshot. Reject stale data, expired departures, incompatible flight overrides and mixed model/issue evidence. No fitting per HTTP request. Only then stage the selected item as an actionable canary.
5. Preserve frozen Camel tree and Chamois cycle protocols. They can confirm/reject their own candidates tomorrow; this report does not substitute a different model.
6. Treat flowers/plushies as the release scope, with per-item unavailable/research labels where necessary. Japan Xanax must not block their progress or inherit their performance claims. HTTP reachability does not establish release readiness; a continuously fresh feed and actual deployment integration remain outstanding.

## Validation

Six readiness unit tests passed, including detached model visibility without event promotion, no-departure null accuracy, missing-policy coverage, preserved existing gates and unchanged input. The updated helper successfully processed all 24 items in the verified forward report. Reporting changes do not alter numerical models or routine research source pins.
