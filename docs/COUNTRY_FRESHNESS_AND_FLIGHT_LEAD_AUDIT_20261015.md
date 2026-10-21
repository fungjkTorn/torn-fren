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

The refined probe also preserves Japan Xanax quantity and a parseable,
timezone-qualified provider `nextRestock` value when present. This is an
unverified external value, not an observed game event, depletion anchor or
model input. It is captured separately to determine whether an independently
issued comparator is available for later forward validation. Raw strings are
not retained, and absent or malformed values stay missing.

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

The refined timing audit separates next-after-clock comparisons from ordinal
event comparisons. A forecast falling just before a target clock can make
the next-after-clock selection jump one cycle; that is not a large error for
the same event. Ordinal pairing preserves the forecast's event number after
issuance. It follows existing V145 continuity rules across same-phase provider
switches, while gaps and physical phase conflicts remain unknown. The strict
cycle-count diagnostic separately reports gaps, switches and phase conflicts;
rejecting every switch there is deliberately more conservative than V145 and
does not prove all switched observations are wrong.

## VM activation boundary

The tested collector/export payload is source commit
`5a4d546a7e17d3766ac503765373f2bdb3f3342c`. A minimal
`deploy/research_runner/country_clock_activation.patch` is also prepared. It
changes only the collector's history service and preserves unrelated edits;
patch application was verified against the previous public source with an
additional unrelated host edit.

Activation requires the VM owner because the research account cannot read or
modify `/opt/torn-fren/data`, install `/usr/local/lib` exporter code or restart
the collector. Do not grant it those permissions.

The reviewable activation consists of checking the patch against the actual
`/opt/torn-fren/services/history_service.py`, backing up the affected code,
installing the new `services/country_freshness.py`, applying the collector
patch, and updating `/usr/local/lib/torn-fren-research/export_snapshot.py`.
Preserve existing owner/mode and unrelated changes. Restart only
`torn-fren-poller.service`, then run `torn-fren-research-snapshot.service` after
new polls arrive. Verify successful collector heartbeats, new per-country
receipt rows, nonzero exported clock rows, and continued research isolation.
No web/bot restart or prediction-source promotion is required. If activation
fails, restore the backed-up code and original exporter and restart the poller;
retain any clock observations already collected.

A source commit or successful public probe does not mean this activation has
happened. Historical labels remain unchanged and country-clock history absent
until the collector and installed exporter actually produce it.

This host preflight prepares and checks the exact tested collector diff and
reports the active service configuration; it does not apply the patch or
restart anything:

```bash
git -C /home/ubuntu/torn-fren-v38-probe fetch origin research/v38-full-roster-live-prep-20261009
git -C /home/ubuntu/torn-fren-v38-probe diff 846376743e8284396b95081a4326ae62a2fa6ac0 5a4d546a7e17d3766ac503765373f2bdb3f3342c -- services/history_service.py > /tmp/torn-country-clock.patch
git -C /opt/torn-fren apply --check /tmp/torn-country-clock.patch
systemctl show torn-fren-poller.service -p ExecStart -p WorkingDirectory -p User --no-pager
sha256sum /usr/local/lib/torn-fren-research/export_snapshot.py
```
