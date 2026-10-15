# Country freshness instrumentation and flight-lead uncertainty

The direct-arrival and commitment experiments did not solve Japan. This round
addresses a measurement gap and audits the growth of error before selecting
another prediction model.

## Country clocks

New append-only `country_stock_observations` records receipt time, country,
provider, provider-reported country update time, export time, clock status and
item count. Recording occurs in the same transaction as item saves, including
unchanged quantity/price polls. If an item save fails, its country observation
rolls back. The legacy list-only fetch explicitly records missing clocks.

Missing, malformed, future and empty-payload clocks remain distinguishable.
There is no milliseconds guessing, receipt-time substitution, or retrospective
backfill. Repeated and regressed clocks and provider switches are retained.
Stock-history timestamps, zero-depletion semantics and existing delta behavior
are unchanged. The clock is a provider report, not proof of each item's game
state or exact event time.

The sanitized exporter supports the optional table with explicit columns,
verified country/provider/status allowlists, a bounded row count and the same
atomic read-only source transaction. Old databases export an empty table with
metadata saying instrumentation is absent. No credentials, response bodies,
player data or arbitrary error strings enter this export.

Collector instrumentation and exporter installation require the host services
to run the new source. A research-branch commit does not activate either on
production. The isolated runner intentionally cannot alter the live collector
or its privileged exporter. Until activation, the research snapshot must keep
country freshness unknown.

An independent bounded public-provider probe observes both existing public
endpoints six times, 60 seconds apart. It retains only reported clocks/statuses
for the eleven countries. It uses no Torn/player key and no collector access.
This short sample can reveal current delays, repeated/regressed clocks,
omissions and fetch failures; it cannot establish long-term freshness or
retroactively fix historical evidence.

## Fixed-lead audit

Seven days of canonical UTC hourly issues, ending eight hours before the
snapshot cutoff, prevent choosing issues from outcomes and allow the fixed
forecast horizon to mature. For true-zero, rate and current-rate hybrid
forecasters, inspect leads 0,15,30,60,90 minutes, actual country flight time,
three hours and four hours. This is a diagnostic, not departure simulation.

At each lead, score predicted >=30 availability with poll-backed arrival
evidence. Publish the full confusion matrix, positive precision/recall,
specificity, balanced accuracy and actual available fraction. Japan's large
empty fraction makes always-unavailable accuracy a misleading headline.

Also compare the number of true physical restocks before the lead, revealing
cycle slips. Choose predicted and observed next restocks after that clock
independently; report signed and absolute timing-error quantiles, interval
width and empirical interval capture. Never choose the nearest observed event
to make an error smaller. These next-after-lead events can have different
identities when a cycle slips; this is not event-conditioned recall or flight
success. Collection gaps and provider switches make the relevant intervals
unknown. Forecast abstentions and missing next events stay visible.

No new policy is promoted from these diagnostics. The routine source pin and
existing frozen forward protocol remain unchanged.
