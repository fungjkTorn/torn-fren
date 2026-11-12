# TORN-FREN — Oct 13 handoff reconciliation and forward readiness

This supplements `WORK_MODE_MASTER_HANDOFF_20261013_LATEST.md` and the Oct 12 master. It was checked against previous TORN Projects conversations and the current isolated research branch. **It is not new VM evidence.**

## Corrections to older "not yet run" statements

The Oct 12 and Oct 13 handoffs retain some older pending language for V128/V139/V142. The Oct 12 conversation *later reported* the following successful VM checks:

- V142 returned HTTP 200 for both original `/` (V2 graph) and `/experimental`; existing `/api/experimental/v41/predictions` reported **24/24 expected items, zero missing, zero duplicate keys** and the V87 21+3 expansion was present. This is a point-in-time 2026-10-12 observation, **not proof of today's deployed source or continued correctness**.
- V128 emitted multiple 24-row five-minute snapshots; one prior SQLite exception and subsequent successful runs were discussed. This is not a fresh Oct 13 timer health check.
- V139 was reported completed in that prior conversation. Its non-head-to-head, differently sampled historical proxy figures were V75 **86.7%** (814 evaluated), V128 **72.5%** (160), V2 **65.6%** (2,013), original V2 restock-window hit **36.0%** with about **130.05 minute MAE**, and **30.6%** of evaluated arrivals in stock. Never compare these as a controlled model tournament, and never treat them as actual player purchases.
- The preceding conversation discussed copies/review of deployed `app.py`, `experimental.html`, and `index.html` and matching fingerprints for at least the first two. **These live deployed files are not assumed to be present in the research GitHub checkout**. Do not copy the checkout's `web/app.py` over production or replace either web view.

Historical V142/V139 need not be rerun just to reconfirm the handoff happened. Actual current deployed-source drift remains to be checked before an additive web patch.

## Oct 13 repository engineering after the handoff

V160 and V161, including an isolated private forward ledger, guarded VM operator and systemd unit files, were **already built** before this continuation. They are not automatically installed or enabled by GitHub.

After auditing the V161 reporter, the continuation changed:

1. Separate `*_pending` from `*_unknown` from `*_miss` for independent, paired, same-issue leave-now, and real near-issued V75 candidates. A not-yet-arrived flight was previously merged into unknown.
2. Distinguish `*_future_reconfirmation_pending` while WATCH departure is still in the future from actual mature `*_future_unreconfirmed`. A future departure cannot be condemned before its recheck deadline.
3. Keep zero-valued counters stable in the output schema.
4. Add all 24 item-level incumbent **roster metadata** and explicit forward evidence readiness states. `incumbent_source_verified` only describes source integrity metadata, not a live recorded V75 forecast or certified successful flight; `model_promotion_authorized` is always false.

Tests are in `tests/test_v161_prospective_v151_forward_report.py`. CI results at each commit must be checked before modifying the pinned V160 operator source. **An existing pinned VM stage can remain on the original V161** until the operator PIN is deliberately updated and safely smoke-tested. No VM commands or production mutations occurred in this repository-only correction.

## Safe next steps

1. Check current isolated-branch CI and explicit pinned bundle SHA. Do not mix an updated live reporter with stale untested modules.
2. From authorized VM access, run `status` and one `smoke` using the exact tested operator from GitHub. Smoke stages private research code, reads the collector only, and does **not** install a timer or write forward issues.
3. If the user *explicitly approves* the NEW V160 private five-minute timer, enable that isolated service; verify complete 24-row repeated real-time issuance, latency and resource constraints.
4. Run V161 only on real, mature prospective issue rows. Count pending, unknown, not-yet-due WATCH, model abstentions and missing incumbent predictions separately. Compare same-issued V151 independent/paired/leave-now and valid near-issued V75 on matched arrivals; use replenishment episodes to flag correlated samples. No player-flight success claims.
5. Use deployed-source snapshot/reconciliation, additive opt-in flags, identical V2 and experimental semantics, canary and rollback before any authorized public integration.

**Still unverified:** V160 VM installation/state, genuine forward ledger data, accurate per-item champion choices, source freshness per country, current deployed HTML/source hashes, Japan Xanax credible threshold-30 arrivals, and release of the 24-item beta. Both established website views and all incumbent champions must stay intact.
