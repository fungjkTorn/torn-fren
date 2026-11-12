# TORN-FREN dual-view beta readiness — 12 October 2026

## Product decision (user-confirmed)

**Keep BOTH visuals as first-class interfaces.**

1. **Existing /experimental** is the item-overview board. The original
   private preview used `/api/experimental/v41/predictions`: initially
   21 published private-study incumbents, with three V87 preview entries
   proposed for Panda, Lion and Japan Xanax (24 total). Fields include
   `item_key`, `model_family`, `model_config`, `status`, `computed_at`,
   `stock_as_of`, `valid_until`, `departure`, `arrival` and
   `actionable`. The user wants item, model, time to leave, arrival ETA,
   and explicit next replan/expiry. Keep categories, country filters, sorting
   and links to each item's graph.
2. **Original V2 graph /** is the detailed per-item view. Preserve the
   actual stock graph, restock window, predicted depletion/stock lifetime,
   reachable forecast cycles, departure window and countdown.

They must share identities, source freshness and explain why old V2's
restock-window estimate may differ from an item's experimental departure
challenger. Do NOT silently replace one model with another or pretend
distinct predictions agree.

## Source discrepancy — don't overwrite the VM

The GitHub research branch's `web/static/` has `index.html` and
`admin.html` only. `web/app.py` in that checkout does not define
`/experimental` or `/api/experimental/v41/predictions`.

**But**:
- `deploy/scripts/v77_experimental21_source.sh` explicitly interrogates
  that EXISTING route on the deployed VM; the experimental site used a
  V75 21-row prediction sidecar.
- `deploy/scripts/v87_web24_preview.sh` guards a 21-to-24 preview
  integration that retains the original 21 and adds three unvalidated
  forecasts from separate sidecars.
- `research/v97_experimental_dashboard_state.py` already distinguishes
  far WATCHes from READY and model snapshot TTL from departure time.
- Therefore the live VM deployment and checkout have meaningful source
  divergence. Do not create another beta UI and do not run git checkout or
  overwrite deployed `/opt/torn-fren/web/app.py` until exact files and
  services are inspected and rollback is established.

The VM experimental page's CURRENT implementation and whether the V87
overlay actually remains installed are not verified in this chat. Don't
state that the current site has 24 active models until probed.

## Work completed on isolated research branch

- `research/v140_existing_experimental_beta_board.py` implements a
  **pure, non-mounted 24-item beta display contract** that preserves each
  existing experimental incumbent row and adds V128 as a *separate research
  challenger*. All 24 items receive a direct link to their V2 graph.
  Snapshot expiration, provider uncertainty, no-baseline and missing V128
  batch are first-class statuses. The V128 raw scenario fraction is
  explicitly NOT a calibrated success probability.
- `tests/test_v140_existing_experimental_beta_board.py` checks
  all-24 integrity, original 21+3 missing, graph link, divergent models,
  expired/late/stale state, no fictional GO, duplicate items, and complete
  V128 batch requirement.
- `research/v141_v2_feasible_departure_window.py` is a **pure guard**
  for the original V2 graph. Unlike current browser/server fallback,
  if forecast depletion (minus buffer) is <= safe earliest arrival,
  there is NO feasible departure; missing lifetime is not filled from
  restock-window end. Nonzero stock now never implies >=30 at landing.
- `tests/test_v141_v2_feasible_departure_window.py` covers feasible,
  impossible, zero-width, expired and no-lifetime cases.
- CI workflow `.github/workflows/v85-japan-forward.yml` runs the two
  new test suites on this branch. None of these files is a web endpoint,
  sidecar-writing worker or deployment action.

## Beta quality gates (not yet satisfied)

[ ] Run prepared V142 read-only audit for live /experimental fields and\n    exact HTML code fingerprint WITHOUT clobbering deployed files.
[ ] Verify exact existing API roster: 21/24, no duplicates, appropriate
    specialist per item, fresh valid_until and actual status labels.
[ ] VM V139 combined frozen outcomes: original V2 next-restock &
    direct >=30-at-arrival proxy vs V75 and V128; censored unknowns.
[ ] VM V128 scheduled timer health and repeated full 24-item saved issues.
[ ] Integrate V140 into existing experimental UI through reversible opt-in,
    keeping V2 graph untouched. Do not mount automatically.
[x] Prepare NO_WINDOW semantics in BOTH research branch server+browser,
    with JS/Python parity regression tests.\n[ ] Inspect current VM graph source, reconcile drift and apply this change\n    only behind reviewed reversible canary. NOT deployed yet.
[ ] Verify model-specific error metrics per item, especially weak and
    abstaining items; require honest minimum evidence bar for calling beta.
[ ] Browser QA: desktop/mobile, 24 rows, long item names, filters,
    graph navigation, update timer, clock rollover, stale/offline cases,
    no graph/network performance regression.
[ ] Reversible web-only beta/canary, health checks and verified rollback.
[ ] User authorization before any production site change.

## Resuming when user returns to PC

`docs/home_vm_actions_20261012.md` preserves the original V128 recorder
health check and combined V139 evidence run. Add a read-only inspection of
the deployed /experimental API+HTML before integration; prefer a single
compact command and no secrets. The V139 private data MUST be evaluated on
the VM; CI/synthetic tests cannot substitute real arrival evidence.

## No more research drift

A task must materially move either (a) the existing multi-item experimental
board toward useful, reliable 24-item beta, (b) V2 graph accuracy/feasible
flight guidance, or (c) the later travel planner that consumes exactly
those forecasts. Otherwise deprioritize it.
