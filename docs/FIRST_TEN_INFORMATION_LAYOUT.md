# Historical information, planner financials and viewport layout

The lightweight graph previously skipped old history/profile analysis to protect
VM CPU. Restoring its panel exposed empty statistics; displaying dashes did not
restore their data. This update supplies descriptive observed-history summaries
through a separate bounded, read-only endpoint. It does not re-enable V2 fitting.

## History statistics

/api/first-release/history-summary reads the sanitized fourteen-day forward
export, once per item per five-minute cache bucket. Reads run outside the async
web event loop, use SQLite query_only/mode=ro, close connections and have row and
query-time bounds. Only stock states, collection gaps and poll receipts are read.
No collector or model/evidence database is modified. Missing samples remain
explicitly unavailable rather than becoming invented statistics.

Completed purchase-stock periods use >30. Gap-crossing and contradictory
provider transitions reset the phase boundary; incomplete periods do not become
completed durations. The historical panel labels the last >30 opening, average
and median stocked time, average and median wait to >30, completed stock windows,
uncertain boundaries and the sampled peak. True depletion remains quantity=0.
The sample size, duration and evidence time are shown separately from the live
collector verification. These descriptions are not forecast-accuracy claims.

Historical statistics are cached across normal graph refreshes. Older graph
insight updates cannot erase them back to dashes. Unsupported items retain their
live price/stock graph and a clear historical-sample availability message.

## Prices and profitability

The planner joins item names and countries to the existing /api/catalog output.
It displays foreign buy price, Torn market reference, net profit per item,
profit per slot/hour and ROI, alongside stock, flight duration, departure,
arrival, deadline and last-ten evidence. Profit uses the existing server's 5%
Item Market fee and PI + pilot round-trip assumptions. It is per inventory slot;
capacity/person-specific returns are not invented. Details retain the full
financial explanation. Profit/item and hourly-profit sorts are available.

Price/catalog failures do not blank forecast advice. Cached quotes and their
status remain visible; missing prices remain unknown, not zero. The graph reuses
its existing price lookup, avoiding a duplicate catalog request on that page.

## Layout

The graph measures available desktop height after controls, information and
footer, then gives the remaining space to the chart. Spacing and repeated
explanatory sublabels are reduced; values remain readable. Source/fee explanations
remain in tooltips and details. A minimum 300px chart is retained on short screens,
where normal scrolling remains available. Nothing is clipped with overflow:hidden.
Responsive resizing keeps the travel bands in view while that mode is selected;
manual panning preserves the user's history view.

The planner groups related facts into cells instead of appending many columns.
Stock shares the item/country cell, and the leave-by deadline sits under departure.
Pagination adapts to the available desktop height; mobile keeps readable item
summaries and ordinary scrolling. Larger item sets use the same search, filters,
profit sorts and pages.

## Deployment and verification

Deploy from the reviewed Git commit with update_first_ten_web.py. The manifest
now permits the planner HTML as well as the existing bridge, JS and CSS; no other
production file is writable through this updater. The installer verifies prior
hashes, backs up and replaces those four files, restarts only the website and
checks routes, asset/HTML hashes, model/publisher identity and a real historical
summary request. Rollback restores the previous website. Publisher service,
models, collector and evidence series remain unchanged; no GitHub Actions.

Python checks cover phase/gap/provider semantics, literal-zero depletion, future
exclusion, database immutability, HTTP delivery, deployment scope and rollback.
Browser checks cover populated financial cells, history fields, adaptive pages,
mobile width, readable travel windows and the full desktop graph/footer fitting
inside a 1894x958 viewport. Descriptive statistics and screenshots used for QA
are not model accuracy results. Halloween/rolling-model work remains deferred.
