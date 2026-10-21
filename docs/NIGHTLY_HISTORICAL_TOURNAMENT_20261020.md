# Nightly restock-first historical replay — October 20, 2026

**Owner goal:** predict each chronological physical zero-to-positive restock,
select the first reachable flight while at least 30 units survive through
arrival +10s, and improve specialist accuracy for plushies and Japan Xanax.

## Bounded overnight execution

Private scheduled workflow:
`fungjkTorn/torn-fren-research-private/.github/workflows/nightly-historical-all24.yml`.

* Every night at **05:15 UTC** (01:15 EDT, 00:15 EST).
* The job executes on the existing **isolated research-only VM runner**,
  using the 24-item sanitized stock-history snapshot, **not** the production
  database. It checks the research metadata and verifies no read access to
  the live collector.
* Historical baseline: `python -m research.historical_restocks_all24`,
  exactly 2 historical days of 5-minute decisions, 24 pinned item keys,
  with actual 8-hour flight-maturity cutoff and UTC hourly
  five-minute-reconfirmation cohorts. A 65-minute timeout bounds
  this step; per-item partial checkpoints are retained.
* Historical challenger: existing `research.restock_event_clock` modes
  `phase_empirical`, `interval_median`, `interval_ridge`, and
  `phase_recursive_ridge` on up to eight weak/priority items including
  Japan Xanax. Each gets a 135-second timeout; all four model variants
  are evaluated on the same 1-day period per item when they finish.
* The job is low priority (`nice -n 19`), with numerical libraries
  limited to one thread. GitHub job timeout 110 minutes, independent
  GitHub workflow concurrency serializes nightly runs. No web or
  collector restart, API traffic, in-game automation, cleanup, model
  promotion, or production deployment.
* Initial workflow push runs a two-item Jaguar/Japan integration smoke,
  rather than consuming a full overnight budget before the scheduled time.
* Existing private V160/V161 and other prospective forward tests remain
  separately scheduled. Historical evaluation is **not** a replacement
  for true as-issued forward measurements.

## Leakage / validity rules

All model issuance runs exclusively on item history and poll health
observed by that historical tick. Five-minute recommendations are replaced
by the newest issue before the simulated departure, and source evidence
expires at 180 seconds. Unreachable first physical restocks remain part
of the event identity; no nearest-later-event matching.

Evaluation happens **after all forecasts are generated** and uses
poll-backed quantity observations with explicit unknown and
pending classifications. Physical timing is scored against the correct
chronological 0->positive event using independent poll brackets where
provider continuity can be established. The 2-day baseline includes an
earlier/later temporal split, without optimizing on the later portion.
Repeated hourly recommendations against one underlying restock are
correlated, not independent observations. Stock-at-arrival is a proxy,
not confirmation of a player's actual Torn flight, purchase, or fresh
country YATA observation.

## Read results

- Private `reports/latest_nightly_historical.json`: safe, aggregate
  per-item historical timing, simulated flight coverage/success,
  matched leave-now metrics where present, and a source run ID.
- GitHub Action artifact `torn-fren-nightly-historical-metrics`:
  per-item aggregate report, earlier/later split, bounded challenger
  comparison, and partial results after resource timeouts.
- A GitHub-hosted `publish-nightly-historical.yml` completion listener
  copies **only aggregate** results to the private report. No raw
  stock database, personal API key, or travel history leaves the runner.

If a night is cancelled, has inadequate older historical cycles, hits
resource limits, or provides no model forecasts, the output must say so.
A missing output is **not** success, and training on the later validation
period is not allowed. Don't publish or select winners automatically.

## What should improve after real scores exist

Sort models on the *same item and same test period* by physically correct
restock error, distinct-restock coverage, true earliest-reachable departure,
survival through arrival +10s, unnecessary waiting and matched
depart-now improvement. First prioritize Camel, Nessie, Red Fox, Monkey,
Panda, Wolverine and Japan Xanax. Preserve the original V2 graph, the
experimental all-items board and Travel Decisions.

Next model selection must be evidence-driven, with untouched later data
and separate forward confirmation. No production changes without approval.
