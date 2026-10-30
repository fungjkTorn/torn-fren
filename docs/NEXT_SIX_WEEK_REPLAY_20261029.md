# Corrected next-six weekly replay

Period: October 22, 2026 10:00 PM EDT through October 29, 2026 10:00 PM EDT.

All six selected tournament challengers were checked against the first-reachable-window sequence before the replay. Training uses all available causal history. Panda has no 48-hour restriction. Current reachable stock gives leave now; native timing refines only the first reachable future window. These are historical results, not live accuracy certification. No live services or metrics were changed.

## Known arrival results

Rates are successful frozen arrivals / known frozen arrivals. Quantity >30 at exact arrival succeeds; <=30 fails, with zero grace. Unknown and pending arrivals are excluded from the percentage but shown below.

| Item | Success / known | Rate | Failed | Unknown | Pending | Advice clocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Camel Plushie | 89/121 | 73.6% | 32 | 8 | 2 | 1762/2017 |
| Nessie Plushie | 108/145 | 74.5% | 37 | 9 | 1 | 1786/2017 |
| Red Fox Plushie | 89/116 | 76.7% | 27 | 6 | 1 | 1782/2017 |
| Panda Plushie | 94/128 | 73.4% | 34 | 10 | 2 | 1814/2017 |
| South African Xanax | 25/35 | 71.4% | 10 | 4 | 1 | 1849/2017 |
| UK Xanax | 1/1 | 100.0% | 0 | 0 | 0 | 1947/2017 |

UK has only one independent trip and zero qualified restocks in this week. Its numerical 1/1 result is not evidence of a dependable 100% success rate. Repeated leave-now forecasts in a continuously stocked period do not create independent successes.

## Every failed arrival accounted for

For zero-stock arrivals, compare minutes since the prior clean depletion to zero with minutes until the next qualified normal restock. The nearer boundary determines late or early. Small sellbacks are excluded from qualified refills. Ties and uncertain boundaries remain explicit. Positive stock 1–30 remains a purchase failure but is separated from zero-stock timing misses. A failure with uncertain early/late classification stays in the failure denominator.

| Item | Early | Median early min | Late | Median late min | Other failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Camel Plushie | 17 | 2.78 | 7 | 1.92 | 8 |
| Nessie Plushie | 16 | 3.82 | 16 | 4.51 | 5 |
| Red Fox Plushie | 9 | 3.40 | 12 | 5.38 | 6 |
| Panda Plushie | 16 | 3.12 | 15 | 2.78 | 3 |
| South African Xanax | 3 | 43.38 | 6 | 28.26 | 1 |
| UK Xanax | 0 | — | 0 | — | 0 |

There are 140 failures: 61 early, 56 late, 7 positive-stock failures, and 16 with uncertain timing classification. `all-misses.csv` has one row for every failure, including departure/arrival in Eastern time, both boundary distances where observable, observed quantity brackets, and the original predicted window. `trips.json` retains the complete frozen-trip details.

## Interpretation and next work

- **Camel:** 14 of 17 early misses were within five minutes of restock, but all seven late misses were also within five minutes of depletion. A small later target is worth testing inside suitable windows; applying one blanket delay could worsen the existing late cases.
- **Nessie:** 16 early and 16 late misses. Median distances are 3.82 and 4.51 minutes. This needs better placement/calibration of the selected window, not a universal shift in one direction.
- **Red Fox:** strongest regular-cycle result, 89/116 (76.7%). There were nine early and twelve late misses, with medians 3.40 and 5.38 minutes. It clears the earlier 75% screening level, while remaining below the desired high-success target. It is the strongest forward-beta candidate from this batch.
- **Panda:** 16 early and 15 late misses; medians 3.12 and 2.78 minutes. Twenty-four of the 31 direction-classified misses were within five minutes of a boundary. Preserve full-history training for this baseline; separately test arrival-window calibration before drawing conclusions about rolling training.
- **South African Xanax:** three early and six late misses, with medians 43.38 and 28.26 minutes. Only one of those nine misses was within five minutes of a boundary. This calls for investigation of phase/restock timing rather than a small timing offset.
- **UK Xanax:** the quantity/median-rate continuation provided advice at all 1,947 fresh-country sampled clocks; 70 clocks were withheld for stale country evidence. This is an advice-availability result. Continuous stock prevents a useful restock-success estimate. A rolling or rate-based continuation study should be assessed separately, including depletion/quantity calibration when informative observations occur.

## Withheld forecasts and uncertainty

The regular items sometimes have an unknown current phase onset (for example after an evidence gap/provider transition), or an ongoing phase beyond all completed historical survivors. These are forecast-availability limitations distinct from known arrival failures. They should be addressed in the shared event-window logic, alongside per-item timing improvements.

| Item | Unknown phase | Phase outlasted history | Stale country |
| --- | ---: | ---: | ---: |
| Camel Plushie | 92 | 31 | 132 |
| Nessie Plushie | 143 | 18 | 70 |
| Red Fox Plushie | 127 | 38 | 70 |
| Panda Plushie | 101 | 23 | 79 |
| South African Xanax | 121 | 0 | 47 |
| UK Xanax | 0 | 0 | 70 |

Arrival unknowns arise from unavailable country evidence at landing or stock availability changing inside the confirming poll bracket. Boundary timestamps also have polling uncertainty; minute-distance labels describe the observed evidence, not exact hidden game event times.

## Audit and limitations

- 12,102 sampled forecast times; 10,940 contained departure advice. No model errors, wrong model identities, missing full-history flags, altered flight geometry, or threshold/grace mismatches.
- All V5 target-identity audits report zero duplicate target groups. Scoring is idempotent; frozen geometry matches the saved recommendation and source/archive hashes remain unchanged.
- The initial three-item scoring agrees with the completed six-item scoring.
- Historical forecasts are sampled every 300 seconds, while production refreshes each minute. This is sampling, not a departure eligibility filter. Advice expiry is preserved, and unrecorded refreshes are not invented.
- Publication is represented by the sampled issue time; real server latency is not measured in this replay. Late-week unconfirmed arrivals remain pending.
- Native configurations are Camel v19 dyn3, Nessie v19 dyn8, Red Fox v18 dyn1, Panda v19 dyn1 (full history), South Africa v19 dyn6, and UK v19 dyn8 with the documented current-stock continuation. No automatic promotion or deployment was performed.
- UK uses a research median quantity-depletion fallback when its original event forecaster lacks a current-stock window. This is uncalibrated and does not invent restocks or reset the observed phase onset.

## Files

- `results.json`: all per-item metrics, source identity, code fingerprints, and latest-ten metrics.
- `miss-analysis.json`: per-day frozen outcomes, near-boundary counts, and withheld-forecast causes.
- `all-misses.csv`: every failed frozen trip with early/late evidence.
- `trips.csv` / `trips.json`: all 590 simulated trips, including unknown/pending outcomes.
- `policy-audit.json`: sequence/identity/geometry checks.
- `archive/`: exact saved forecasts and the replay contract, permitting rescoring against the supplied source.
