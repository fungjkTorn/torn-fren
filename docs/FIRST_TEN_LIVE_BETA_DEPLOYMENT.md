# Ten-item live beta release

This is an owner-authorized live beta, not a certified-accuracy release. It
uses the ten frozen identities in FIRST_RELEASE_OPERATION_SEQUENCE.md.

## Site integration

The audited VM app is based on the older V41/V87 deployment, with local changes.
The installer checks its exact preflight SHA256 before adding one middleware
hook. Its original bytes are backed up and restored if staging, publication,
restart or API smoke checks fail. It does not replace the local history service
or the graph's stock/profitability data.

- `/experimental`: ten-item overview from the beta snapshot.
- `/travel-decisions`: the same forecast and evidence feed.
- `/`: original stock graph with the new feed in its prediction fields and
  an explicit beta result card. The old browser cannot independently roll to
  a later event or add a different flight buffer to first-release predictions.
- `/api/first-release`: precomputed feed, model provenance, freshness and
  recent publication timestamps. No fitting or collector access per request.
- Items outside the first ten show under-review status, not old accuracy
  figures or unapproved departure recommendations. Their stock graphs remain.

## Publication and evidence

One dedicated, low-priority systemd service runs every minute. The source
is the existing sanitized forward export. The new service makes its own
consistent read-only copy for inference; it does not write the collector.
It runs the ten fixed models only, not a tournament. Per-item timeouts, a total
budget, a shared lock and source/publication freshness gates prevent overlapping
or stale success claims. An incomplete batch cannot replace the prior feed.

Issued revisions and outcomes are append-only SQLite records in a new state
directory. Actual landing is departure plus flight duration. Mature outcomes
need a successful poll bracket, no gap/provider ambiguity and stock >30.
Exactly 30 fails. Pending and unknown remain distinct from failure.
The permanent ledger keeps each selected opportunity, its timing bounds,
depletion prediction and provenance. It does not duplicate all 64 projected
future events every minute; the public snapshot retains that full calendar.
Observed openings without a matched forecast are counted separately and are
not automatically labelled reachable or missed trips.

For the recent-results scorecard, immutable event ordinals are matched to
observed >=31 buying-window openings, not whichever event is nearest to a
prediction. The first published forecast per observed opportunity is scored;
later revisions cannot replace an earlier miss. Repeated issue rows are not
ten independent trips. The full revision log remains available for analysis.

Unmatched rows are disclosed. A displayed percentage is withheld while
unmatched failed/unknown rows would otherwise be outside its denominator.
This avoids advertising a high rate by dropping difficult forecast misses.
Opening times are poll-observation brackets, not exact game timestamps.
Buying-window openings need not be physical zero-to-positive refills, for
example if stock is replenished while still nonzero. The UI labels them as
observed opportunities.

Global successful polling is corroboration, not per-country freshness proof.
If country observation clocks exist, an explicitly stale/invalid latest report
suppresses that country's recommendation. Missing clock coverage is retained
as an unverified limitation rather than fabricated. No actual user flight is
needed and historical rates are not included.

## Guarded admin activation

The ZIP contains a pinned full source tree and per-file checksums. The installer
uses the existing research Python runtime and staged source; it installs no new
Python packages on the VM. It stages one real ten-item publication, validates
the service/timer with systemd, checks all three views on a temporary owned
loopback server, then starts a real systemd invocation before switching the
website. The temporary server is always terminated. No process is left detached.

Initial success requires fresh data, at least one available recommendation,
the exact release revision, all ten item rows and a graph API bridge check.
The output lists any unavailable item recommendations rather than claiming
that every model produced a usable current estimate. The timer's scheduled
cadence and live accuracy remain unverified at initial activation.

The rollback command is printed and retained in the deployment report. It
disables only the new timer, stops its service, restores the original app,
removes the new hook/assets/drop-in, and restarts the old website. It refuses
to overwrite newer edits. Evidence and source releases are preserved.

Existing collector, bot, arbitrage, backup, recovery and old research services
are not stopped by this installer. Further retirements follow verification
that the new feed is working and no remaining consumer needs an old producer.

## Validation scope

Local tests cover native model operation, full ten-item publication without
source writes, immutable issues, arrival evidence, duplicate grouping,
stale-feed suppression, partial-batch failure, all three HTTP routes and
installer success/rollback in a fake VM filesystem. Tests use deterministic
fixtures; they do not establish live accuracy or actual VM performance.
Actual admin installation, systemd execution and external HTTPS verification
must be confirmed from the returned deployment report and the published site.
