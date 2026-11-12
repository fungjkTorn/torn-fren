# Torn-FREN checkpoint 6 — extended CI and final-pair source provenance (2026-11-12)

**Review-only.** No merge to `main`, no live VM changes, no service/timer restarts, no database modifications, no legacy deletions.

## Completed, tested changes

1. Extended GitHub Actions review workflow to run active first-release publisher/scheduler/source tests, first-release graph/history APIs, admin live beta, travel routing, 30-second collection/heartbeat, catalog/revision caches, immutable native-history acceleration, V2 browser/server departure parity and opt-in timeline tests.
2. Python 3.13 CI installs pinned project dependencies plus the research-model requirements needed for publisher tests. A fully separate profitability/private-canary compatibility workflow remains enforced.
3. **Bug found and fixed:** `web/app.py::_latest_safe_leave_timestamp` previously synthesized a latest-departure deadline from a restock window even if depletion was missing or occurred before the earliest usable arrival. It now delegates to `services.v2_departure_window.departure_window`, matching the browser's fail-closed geometry. All seven V2 browser/server parity regression tests passed on the latest green run.
4. **Publisher compatibility found and fixed:** the final-pair launcher supplies `current_stock_leave_now=True` to `first_release_live.publish`, but the reconciled public publisher had lost this keyword. It is now an explicit **off-by-default** option, passed through to the published decision. Existing next-six leave-now and combined Monkey behavior remain retained.
5. **Model timestamp metadata:** restored `prediction_v2_checked_at` as an HTTP response-check timestamp, clearly separate from model issue/computation provenance.
6. Updated first-ten publisher regression to assert that if the publisher abstains, the public API must not invent old V2 departure advice; if advice is available, its first-release provenance must be present. This is stronger than blindly expecting advice on every valid publication.

## Verified review CI status

Review branch head `07d651072264e2348c5a27e3f48bf966686f1392`:

- [Production reconciliation review — PASS](https://github.com/fungjkTorn/torn-fren/actions/runs/43240111061): **111 tests** across 23 isolated suites, Python compilation, middleware HTTP smoke checks for `/`, `/experimental`, `/travel-decisions`, and inline browser JavaScript parse checks.
- [Profitability VM private-canary compatibility — PASS](https://github.com/fungjkTorn/torn-fren/actions/runs/43240111077).

These are offline GitHub tests **not** a verified end-to-end VM deployment or proof of runtime equivalence.

## Private final-pair source captured and preserved

Private repository branch `sync/final-pair-runtime-20261112`, commit `b44965df2d863c9c592eb23d1a30a50340aa3707`:

- `services/final_pair_live.py`
- `services/checkpoint4_state.py`
- `services/daily_forward_report.py`
- `research/remaining_three_policy.py`

Each of the four files exactly matches the Git blob of the previously captured final-pair release. This includes the public Canada Xanax / Chamois publisher and a **separately flagged private Japan** recorder. The private overlay is a **staged source record**, not integrated into public `main`, not an executable merged release, and not deployment-ready.

The public repository already contains most transitive model dependencies (`v169_incremental_checkpoint_selector`, `v45_online_template_probe`, `v46_fast_template`, etc.). The missing public entry point is intentionally kept private pending configuration verification and source-ownership approval.

## Remaining non-negotiable gates

- Capture the **actual enabled VM systemd service/timer metadata**, including module entry points, release working directories and whether the final-pair 200,000-row override remains installed. The prior inventory had 18 installed timers, 12 enabled, but was not a full source/override map. Use a *sanitized read-only* capture; never expose `Environment`, tokens, raw `ExecStart` arguments or secret files.
- Validate final-pair/Chamois and separate private Japan publisher startup and output against the current public publisher API in an isolated staging release, and preserve all dynamic imports.
- Identify which enabled timers are still required and which research/legacy modules are actually unreachable. Historical branch presence does **not** authorize deletion.
- Create separate legacy-retirement PR with proven non-use, preserve release tags/rollback, then approve deployment + merge into `main` and local VS Code sync.

**No claim of complete GitHub/VM parity until systemd and publisher staging gates are satisfied.**
