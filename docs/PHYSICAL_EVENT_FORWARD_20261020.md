# TORN-FREN physical-restock-first: immutable forward evidence

Research branch: `research/v38-full-roster-live-prep-20261009`. This is not
a deployment note and it does **not** certify 90% accuracy.

## Required behavior

1. Predict each chronological **physical zero-to-positive restock** in an
   eight-hour lookahead; do not replace a missed event with a closer future one.
2. Estimate separately when item quantity goes below **30**; a physical
   restock can be real but unsuitable for purchase.
3. Evaluate the current stocked window and each future restock **in order**.
   If a restock cannot be reached by plane with stock remaining at **landing
   and landing +10 seconds**, select the next reachable physical restock.
4. Report an estimated departure and leave-by time; a departure more than the
   original issue's validity interval away is tentative and **requires a new
   issue-time reconfirmation**, not a currently actionable proven flight.
5. Prefer high-confidence accuracy and meaningful opportunity coverage across
   plushies; treat Japan Xanax as a distinct difficult specialty. Never invent
   an actionable Japan flight to increase recommendation coverage.
6. Keep three UI surfaces (original V2 graph, experimental all-items dashboard,
   Travel Decisions) intact. No production changes without owner approval.

## New, explicitly opt-in forward measurement

`research/physical_event_forward.py` uses the existing
`research/build_travel_event_snapshot.prepare()`, the shared
`services/travel_decision_contract_v166.build_item_travel_decision()`,
the independent `research/physical_restock_identity.match()` and
`research/v88_poll_state_forward_report.observation()`. It adds no
parallel collector, production timer, gameplay automation or website writes.

- `issue` prepares a true **24-item** batch from a read-only SQLite source.
  It rejects missing/stale source poll evidence, model timestamp mismatches,
  mismatched physical/purchase ordinals, and an issue that became stale while
  computations were running. The recorded issue timestamp is the **actual
  readiness/publication time**, never the start time of a slow forecast.
- `--record` must be explicitly requested. It writes to a separate
  `physical_event_forward.db` in an existing writable research-sidecar
  directory. The primary key prevents retroactive overwrite; `--preview`
  is no-write by default. The ledger keeps **all forecast physical events**
  and the selected ordinal, arrival, departure, deadline, grace, model SHA,
  current stock status, and issue freshness.
- `report` reads the sidecar and stock snapshot in **query-only** SQLite.
  It freezes the **first item/hour issue** before looking at later outcomes.
  For each first physical event and each chosen physical event, it compares
  the exact event ordinal (including small refills), not a nearest-time
  resynchronization. It excludes ambiguous gaps/provider switches.
- Restock-time error is a **lower/upper bound** from successful poll
  observations; certain vs possible errors within 15s/60s/5m/10m are separate.
  Report both correlated item/hour cohorts and **distinct actual physical
  restocks**. Arrival +10s outcome is a V88 poll-state stock proxy, not
  proof of a player's flight or purchase. Matched depart-now estimates
  use the same frozen issue and travel duration.
- Scoreboards mark future departures that were **not actionable at original
  issue**, even if the eventual hypothetical landing found stock.

## Isolated research execution

Private repository `fungjkTorn/torn-fren-research-private`:
`.github/workflows/forecast-research.yml` now has two explicitly
resource-bounded, low-priority phases using the already approved pinned public
source and **sanitized** stock-only database. The only new persistent sidecar
is `/var/lib/torn-fren-research-runner/research-state/physical_event_forward.db`.
The collector is never opened writeable; the runner's filesystem ACL does not
permit it to read the live production collector.

The private runner tries a forward issuance only if sanitized poll age is
at most 160 seconds at the initial freshness gate. Snapshot `prepare`
and `freeze` recheck freshness at readiness; otherwise the attempt
abstains. The issue pass is capped at 100 seconds, the evaluator at 75
seconds, both using `nice -n 19` and single-threaded math. Failure
is summarized as `INCOMPLETE_RESOURCE_BOUNDED`, not a fake success.

Per-run artifacts:
- `physical_event_forward_issue_status.json`: recorded, stale skip,
  or incomplete; includes 24-item count and actual issue timestamp when
  successful.
- `physical_event_forward_score_status.json`: read-only evaluation status,
  first-item-hour samples, distinct physical restocks, arrival proxy
  outcomes, and reconfirmation counts.
- `physical_event_forward_score.json`: full aggregate/per-item research
  scoreboard when scoring completes.

**Important operational limitation:** the sanitized source may refresh less
frequently than five minutes. No old snapshot may be backdated to fill
missing issues. Genuine 5-minute forward evaluation will require a
sufficiently fresh research-only source and measured runner latency. Any
change to production collectors or services still requires approval.

## Test coverage and criteria for next decision

`tests/test_physical_event_forward.py` exercises 24-item immutability,
skipping unreachable first stock, selecting second restock in true ordinal
order, landing and +10s deadlines, correlated-versus-distinct counts,
poll-provider ambiguity, read-only separation, future reconfirmation, and
correct publication timestamps. The existing Full24 GitHub safeguard suite
runs it on push; the last verified run before this doc update passed.

Next decision is evidence-driven: first check that **real** 24-item frozen
batches and later resolved outcomes exist. Then compare restock timing,
threshold-30 survival and earliest-actionable departure against the V151
paired/independent, specialist and leave-now baselines *on matching issued
windows*. Track abstentions, source freshness, and real target restock
identity per item. Retain Japan Xanax as a separate specialty track. Promote
nothing automatically. 
