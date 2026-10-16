# Shared departure integration — October 16, 2026

The selected item departure model can now feed Travel Decisions and an additive panel/marker on the original V2 stock graph through one precomputed snapshot. Restock events retain their independent physical-zero model and are not fabricated from arrival support scores. Nothing was deployed or automatically promoted.

## Implemented

- `build_travel_event_snapshot.prepare` accepts explicit per-item `departure_policy` assignments: `zero_path_analog70`, `zero_path_analog80`, `zero_path_recent70`, or `disabled`. Numerical path generation uses the existing `CausalStockPaths`, mature poll-backed training paths, physical-zero state, fixed flight duration and per-issue maturity bounds. It executes offline, never on HTTP requests. Database reads remain one read-only transaction; publication is atomic.
- The new recommendation contract binds item, issue, exact source SHA, policy and flight. It represents a point departure, not an invented safe departure interval. A stale poll, five-minute issue expiry, passed departure, abstention, or unsupported custom flight clears actionable clocks. No silent fallback to an event-adapter departure is allowed once a departure model is explicitly assigned.
- `build_board` keeps departure provenance and event-model provenance separate. Landing is departure plus flight; the additional ten seconds remain an evaluation grace. Historical event evidence cannot be borrowed for a departure policy. No calibrated probability is introduced.
- Travel Decisions displays the independent event timeline and invalidates item-specific clocks client-side, including the deadline field.
- When `TORN_FREN_TRAVEL_DECISIONS_BETA=1`, `/api/history` adds the same selected board row to its response. The original graph has an additive selected-departure countdown and marker, cleared on item changes, request failure and expiry. Stock history and original V2 predictions are preserved. The marker is visible when its point is within the displayed time range.

## Staged item assignments, not a release claim

`deploy/research_runner/flowers_plushies_candidate_assignments_20261016.json` explicitly covers all 24 verified items. It enables 14 candidate policies: all 11 flowers plus Jaguar, Stingray and Wolverine. Cherry Blossom uses analog80; the others use analog70 for the earlier waiting objective. The other seven plushies and all three Xanax entries are explicitly disabled for this preview rather than inheriting an unvalidated fallback.

This is a reviewable candidate profile. It is not a change to the live incumbents. All enabled choices exceeded 90% resolved success in the inspected seven-day and original frozen forward reference results, but this is not an independent selection lockbox: the seven-day report overlaps the forward day and the profile was chosen after inspection. Coverage, unknown mass and day-to-day consistency remain separate. In particular, Banana Orchid covered only about 66% of forward starts, and African Violet analog70 had 28 unknown outcomes. Those limitations prevent calling all 14 release-ready.

The profile excludes the newer Camel tree and Chamois cycle candidates, whose separately frozen forward windows remain unchanged. Rejected regime candidates are not globally promoted. No routine research source pin was changed.

Prepare a candidate snapshot only from a current collector-owner export/source, with the exact integration source SHA and an issue clock consistent with the five-minute replanning protocol:

```bash
python -m research.build_travel_event_snapshot \
  --source /absolute/path/to/current-stock.sqlite \
  --model-sha EXACT_INTEGRATION_SOURCE_SHA \
  --assignments deploy/research_runner/flowers_plushies_candidate_assignments_20261016.json \
  --output /absolute/path/to/candidate-events.json
```

A current heartbeat is mandatory; an old research snapshot is not a continuously fresh public feed. The command installs no service and changes no collector or website configuration.

## Why historical and future tests both exist

Historical replay remains the fast research screen. Repeated tuning on those same days can overfit the inspected stock patterns. The predeclared future windows hold the source/policies fixed and collect later observations before reconstructing issue-time recommendations. They are not actual live issuance, flights or purchases. Final scoring needs the remaining arrival plus evidence lag to mature; it does not block coding or reviewing partial outcomes. The original full-roster report completed October 16 at 11:51 EDT. Chamois and Camel retain their October 17 maturity times.

## Verification and remaining release work

Local tests passed for the shared board, publisher and physical-zero/flight contracts; browser and full compatibility results are recorded after CI completes. Tests include real path generation on a synthetic historical database, per-path maturity bounds, unchanged source bytes, exact geometry, disabled items, wrong flight, stale/expired/passed plans, mixed identities and evidence provenance. Browser cases cover Travel Decisions item expiry and the graph panel/marker lifecycle.

The deployed `/experimental` implementation and `/api/experimental/v41/predictions` are absent from this research checkout. Their integration cannot honestly be marked complete here. Its owner-side implementation must consume the same precomputed row contract and preserve its existing route/row schema. The graph panel and Travel Decisions changes are staged in source, not installed on the VM. A continuously fresh feed, owner-side experimental adapter, staged runtime verification and controlled deployment remain necessary. Existing public pages were not overwritten.

### Completed CI

Implementation source `a793641fe5af207a5b6b844e1a73ee9a600d0550` passed [38930474876](https://github.com/fungjkTorn/torn-fren/actions/runs/38930474876): 148 tests across 30 causal/contract suites and the Chromium interface job, including the selected graph panel/marker lifecycle. V85 forward/graph compatibility, V38 live-inference adapters, V35 private-pilot compatibility, profitability compatibility, and export safety workflows also passed on that exact source. No private protocol pins were advanced.

Point recommendations intentionally expire once their timestamp is missed: this integration does not certify an extra delay tolerance or invent a continuous departure window from one point. Immediate-departure usability under publication/network latency still needs a measured execution-tolerance or explicitly modeled window before release; a fresh poll alone cannot extend a missed point. The profile is therefore staged research configuration, not an actionable public release certificate.
