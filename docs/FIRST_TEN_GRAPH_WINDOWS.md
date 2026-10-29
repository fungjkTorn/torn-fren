# Observed history and travel windows

The compact beta UI hid observed history in a collapsed section below the chart.
The legacy chart also labelled the current-stock forecast's calculation time as
a P1 target drop. That was misleading: recalculating an already stocked item is
not evidence that a new restock occurred.

Observed history is restored beside the travel plan, open by default on desktop.
The same existing stock, price, profitability and historical-statistic DOM nodes
remain connected to the existing API updates. On narrow screens the panels stack;
a phone initially collapses history so the chart remains reachable. Expanding or
collapsing observed history does not enable old V2 calculations. Missing historical
statistics remain unavailable; this update does not invent them or enable heavy
research fitting in web requests.

The travel plan shows two ranges: estimated departure and estimated arrival.
They come from the server-selected departure and its existing deadline. Arrival
bounds equal departure bounds plus flight duration. For current stock the left
bound advances to now while the original selected deadline remains unchanged.
This is elapsed-time display, not a new model, target roll or forecast rewrite.

The chart extends through the latest arrival so both windows can be displayed.
Two coloured bands and labelled time ranges replace the legacy P1 drop overlay
for beta advice only. Current stock is described as already available, without
inventing an observed restock time. Future restock estimates retain their own
separate restock metadata. A Show travel windows control fits both ranges using
an existing chart timeframe. Historical panning and Jump to latest remain
available. The plotted stock series remains observed data; no future stock curve
is fabricated. Stale advice removes the bands and timestamps.

Models, the publisher service, collection, evidence grading and last-ten records
are unchanged. Adapting the model to Halloween or other longer-stock regimes is
explicitly left for a future task, as requested by the owner.

## Deployment

Use the reviewed Git commit with deploy/scripts/update_first_ten_web.py. It reads
only the website files named by deploy/first_ten_web_update.json, checks their
checksums and previous installed versions, backs them up and replaces three
files. It restarts only torn-fren-web.service, checks assets/routes/provenance,
and restores the previous website on failure. A guarded rollback.py is written
to the timestamped backup directory. No ZIP, GitHub Actions, model deployment or
publisher restart is used. The installer is reusable for subsequent reviewed
website revisions through the manifest; its allowed file set remains narrow.

## Validation

Python contract checks verify current stock is not represented as a new restock,
future restock metadata remains explicit, flight geometry and deadlines are
unchanged, and observed history is preserved. Deployment checks cover scoped
writes, newer-edit refusal, rollback and idempotent reruns. Browser checks exercise
the actual audited VM graph HTML and Chart.js with the new bridge contract,
visible observed history, plotted departure/arrival bands, readable labels,
mobile width, keyboard controls and item switching. These are interface and
behavior checks, not a claim about forecast accuracy.
