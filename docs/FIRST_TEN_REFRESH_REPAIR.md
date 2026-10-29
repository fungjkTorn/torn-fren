# Live forecast freshness repair

## Confirmed failure

Public API sampling on October 28 US Eastern reproduced repeating disappearance
of advice. A forecast published only 29 seconds earlier became globally stale
because its underlying exported heartbeat was 189 seconds old. Another sample
showed Tribulus suppressed as STALE_COUNTRY_DATA while its event forecast still
contained a current-stock departure. Across successive samples all ten returned
after a new export reached the publisher. This is a delivery/freshness defect,
not evidence that the model could not find a reachable restock.

The existing fourteen-day full exporter waits 90 seconds after completion; the
audited VM export took 37 seconds. Independent export, inference and browser
polling clocks can exhaust a 180-second evidence TTL between updates. Extending
that TTL would hide real missing evidence. Running a full export every minute
would add unnecessary repeated history reads.

## Repair

The publisher first copies the same sanitized historical export. It then opens
the collector read-only and replaces only an overlapping recent tail for the ten
approved items, successful/failed poll receipts, country stock clocks and gap
boundaries in its private inference copy. The source transaction is consistent,
all observations are at or before the issue cutoff, and no keys or unrelated
tables are read. The tail is bounded by ten minutes of export lag, row caps and
a six-second query budget. Missing/old exports, stale collector polls, missing
country clocks and invalid sources still stop publication. The existing total
45-second inference/publication budget is unchanged.

The normal fourteen-day export and existing jobs are not accelerated, replaced
or retired. The collector is not modified. Forecast fitting and grading remain
off the HTTP request path. Previous valid advice remains visible while a refresh
is running or one HTTP refresh fails. Once evidence actually expires, the UI
pauses advice and says "Stock data delayed" rather than implying all models are
missing a forecast.

Frozen timing/event model source remains byte-identical to approved model SHA
45d14b5e931458e41dc31e551310994caf4f8a1d. The installer verifies this against the
installed immutable source before deployment. That model SHA and evidence series
continue, so last-ten results are not reset. The running publisher Git revision
and recent-tail provenance are separately recorded in every issue and exposed
in the public feed. Old issued predictions and outcomes are never rewritten.

## Tribulus investigation

The public seven-day, change-only history contained long recent stocked periods:
about 17.7, 14.2 and 15.3 hours for the last three completed stocked intervals.
The corresponding recent recorded empty periods were about 58, 54 and 59 minutes.
These are descriptive observed transitions, not a historical forecast success
rate; API history alone does not supply complete poll/gap validation. Earlier
intervals in that same week were shorter, so the current regime should not be
assumed permanent. A three-hour flight can fit many positions inside those long
windows, and the existing model did produce a current-stock departure once
freshness gates recovered. The missing UI advice was not a reason to replace its
frozen model or claim near-100% accuracy from three chart cycles.

## Git deployment

No ZIP and no GitHub Actions. Fetch the release branch into the existing VM
research checkout, then execute the installer from the exact reviewed commit
using git show. The installer stages immutable Git source, checks the installed
service/bridge/UI hashes, verifies unchanged frozen model files, briefly pauses
the existing publisher timer, checks an actual publication, updates the same
service and two website files, checks one real systemd run and website routes,
and resumes the timer. It backs up changed code and creates guarded rollback.py.
Evidence records and model identity are preserved even on rollback. The web
service is restarted once to load the updated bridge. The collector and other
research jobs are not stopped.

The VM must already have authenticated Git fetch configured for the private
repository; missing Git access causes the shell command to stop before the
installer starts. It requires the existing admin SSH key, not new credentials.
After execution inspect the JSON report. Initial installation checks do not
claim sustained cadence; verify new public publisher_sha, source_refresh metadata,
source ages and successive publications after the owner's installation.

## Validation

Focused Python checks cover read-only causal merging, future rows, gap closing,
refusal of stale sources, rollback, frozen model source verification, the complete
ten-model pipeline, evidence continuity and website bridge behavior. Browser
checks cover valid cached advice during refresh failure, genuine expiry,
desktop/mobile layouts, 10/50-item pagination, filtering, sorting, keyboard details,
canvas rendering and item switching. These checks establish behavior, not live
forecast accuracy. No broad model tournament was run.
