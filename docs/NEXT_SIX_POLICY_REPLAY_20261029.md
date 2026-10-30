# Next six: corrected scheduling and historical replay

The five-day V174 tournament includes all six requested items. Their selected
challenger configurations are available; raw collector observations for five
items are absent from the current local exports. No model needs to be selected
again. The tournament archive contains result JSON, not a stock database.

| Item | Selected candidate | Corrected test configuration | Current replay status |
| --- | --- | --- | --- |
| Camel Plushie | v19 dyn3 | v19 dyn3, full causal history | Needs raw-history export |
| Nessie Plushie | v19 dyn8 | v19 dyn8, full causal history | Needs raw-history export |
| Red Fox Plushie | v18 dyn1 | v18 dyn1, full causal history | Needs raw-history export |
| Panda Plushie | v19 dyn1 @48h | v19 dyn1, 48-hour and point lookbacks removed | Needs raw-history export |
| South African Xanax | v19 dyn6 | v19 dyn6, full causal history | Needs raw-history export |
| UK Xanax | v19 dyn8 | v19 dyn8 future-window timing; current-stock continuation | Available older week completed |

## Operation sequence

1. With fresh observations, test whether current stock's estimated buying window
   can accommodate the flight. If yes, recommend leave now. Native timing must
   not introduce hours of waiting within reachable current stock.
2. Otherwise enumerate future restocks chronologically. Skip only an unreachable
   buying window and select the first reachable one. The pinned native model can
   refine timing only inside that selected window; its advisory score cannot
   suppress the event or authorize skipping ahead.
3. Refresh recommendations before departure. At the exact recommended departure,
   freeze the simulated departure and arrival. Revisions cannot replace a miss.
4. Apply the live V5 evidence policy: quantity >30 at exact arrival, zero grace;
   <=30 fails. Inadequate arrival evidence is unknown, immature arrival pending.
5. Classify zero-stock misses by the nearer clean boundary: prior depletion to
   zero means late; next qualified normal refill means early. Keep positive
   quantities 1–30 and uncertain boundaries separate. Report every miss and the
   distances to both candidate boundaries.

All native training uses all available earlier observations, never future rows,
48-hour restrictions, or point-count lookbacks. The historical 300-second issue
sampling is not a departure eligibility filter and does not invent intervening
refreshes; expiry is preserved. It remains a historical approximation to the
minute live publisher. Final rates come from `rescore_saved_challengers` with V5,
not the old ordinal diagnostic emitted by the raw replay runner.

## UK long-stocked phase experiment

A phase surviving beyond all historical completed phases previously yielded
CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS. The research-only fallback estimates
the remaining buying window as current quantity above 30 divided by the median
observed depletion rate from all causal history. Provider-switch pairs, gap
pairs, positive refills and learned surplus-to-base resets do not contribute
consumption rates. No phase clock is reset and no future restock is fabricated.

This is a median quantity-rate fallback, not a rolling model or validated
probability. It is enabled only for UK, only where the original event forecaster
has no current-stock window because its phase overran or lacks bounded history.
Fast modeled depletion can still make the current window unreachable. The
pinned v19 dyn8 remains the timing refiner for future windows.

The available week is October 21, 11:20 PM through October 28, 11:20 PM Eastern.
It contains 2,017 issue clocks. Advice was available at 1,949 (96.63%), compared
with 460 (22.81%) under the prior policy. The fallback covered 1,489 previously
withheld clocks. Of the revised recommendations, 1,907 were leave now and 42
future departures; 68 clocks were withheld for stale country evidence.

V5 records one independent frozen trip, one known success, zero failures,
unknowns and pending outcomes; zero qualified restocks occur in this test week.
Repeated advice during one continuous stocked period is not counted as thousands
of independent successes. There are no misses to classify early/late. This is
an advice-continuation check, not evidence of a dependable 100% arrival rate.
The replay recorded zero model errors and retained the source and saved advice
unchanged through rescoring. Detailed results are in the adjacent JSON file.

## Data and production boundary

`Export_Corrected_Challenger_History.ps1` now exports only these six items,
all available history plus poll/gap/country evidence, with hard row-count limits
that fail rather than silently truncate. It opens the collector read-only and
downloads a new sanitized SQLite file. No live service is changed.

The live sixteen remain pinned to their deployed releases. These changes are
research-only; no next-six item has been activated. Full six-item week/miss
analysis remains pending the new export.
