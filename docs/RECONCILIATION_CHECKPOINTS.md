# Production reconciliation checkpoints

This file is the **durable resume point** for Torn-FREN production-to-GitHub synchronization. Update it with a commit whenever a meaningful unit of work completes. More details: [issue #16](https://github.com/fungjkTorn/torn-fren/issues/16) and [draft PR #17](https://github.com/fungjkTorn/torn-fren/pull/17).

## Checkpoint 1 — 2026-11-12, source and runtime inventory

**Verified / saved**
- Starting repository ref: `release/monkey-combined-20261110`, SHA `4a58ea39d7e82b76a3ed33757464b1419de7ebb2`.
- Local user worktrees: original `torn-fren` remains detached at `5a0c8a6`, local sync `sync/live-website-20261111` started from `4a58ea3` with website JS/CSS edits. No local worktree was modified through the GitHub integration.
- Production: web `/opt/torn-fren`, collector `/opt/torn-fren/poller.py`, publisher under versioned `1781fb8318f9cd943063233b7c2d1eb339b0a5f5-next-six`.
- Read-only inventory captured the website source and release snapshots; 18 installed systemd timers, 12 enabled and 6 disabled. Several older service names are **still scheduled**, so old code must not be deleted by name alone.
- A separate local backup of the live `beta.js` and `beta.css` was checksum-verified by the user against the VM.

**Safety**: no VM restarts, deployments, database changes, public branch merges or legacy deletions.

## Checkpoint 2 — 2026-11-12, review PR created

**Draft PR #17** targets `release/monkey-combined-20261110`, NOT `main`. Source-sync branch: `sync/production-reconciliation-20261112`.

Changes currently on the review branch include:
- Production collector-only `poller.py`; no prediction thread in polling loop.
- Missing production source modules `services/provider_freshness.py`, `web/history_cache_v39.py`, `web/v41_champion_cache.py`.
- Exact source assets `web/first_release_assets/beta.js` and `beta.css`, including the graph **Now** tag.
- Next-six publisher entry point `services/next_six_live.py`, expanded `services/forward_beta_roster.py`, and selected model helpers.
- Reconciled active `web/app.py` and `web/first_release_bridge.py`, preserving opt-in endpoints as appropriate.
- Contract tests for collector, provider freshness, source cache, and champion cache.

**Exact captured production SHA-256 values**:
| File | SHA-256 |
| --- | --- |
| `poller.py` | `3e43d74a5148d00afead8a194872753a825d21a2ca414f22c93fb339b6404396` |
| `web/app.py` | `c7a2066b3afc1a23e97bf7fe4034eaf062d56db869e4d1ab51b856207a3e500c` |
| `web/first_release_bridge.py` | `acfa71ad6b49c4ac5e0c367614df7bea2ed1c1355c0cd8830d679198d6fba8d9` |
| `web/first_release_assets/beta.js` | `ac2b98c86a4d2077558b0a253299ea51d1f931e0c15a31dfe3d76efe64363304` |
| `web/first_release_assets/beta.css` | `9fe8bad697e011e92944b74eb84212fe4ba5166787c4d3a8acfc9254d75f56ef` |

**Local test checkpoint:** 12 targeted tests passed from the captured production helper sources, using isolated module stubs and no VM/network/DB. This is **not** a full GitHub branch test suite pass, not integration validation, and not deployment approval.

## Checkpoint 4 — 2026-11-12, publisher interface reconciliation

**Committed:** `services/first_release_schedule.py` and `services/first_release_live.py` have now been merged on the review branch from the captured active next-six release while restoring November 10's Monkey one-minute timing refinement and Stingray off-grid departure preservation. `next_six_cohort`, full-history and current-stock leave-now handling are retained.

**Review-branch commit:** `d6e7513dc1176bfb4a09e3115cb019264c400eb3` (publisher logic), followed by `b5fefe1c1d407d8901637ae5ea958a0a893ea10b` (contract tests).

**Targeted offline tests:** **15/15 passing** on a local staging copy of the captured source and reconstructed publisher contracts (12 existing isolated collector/cache/freshness checks and 3 additional AST publisher contract checks). This is still **not** full suite or live deployment validation.

**Remaining**: production integration replay/route checks, first-release evidence schema compatibility, next-six batch execution with sample state/DB, bot and runtime timer reachability, legacy archiving classification. No deletes, merges, deployment or VM changes.

---

## Checkpoint 3 — current handoff / outstanding gates

- [x] Reconcile `services/first_release_live.py` and `first_release_schedule.py` publisher interfaces for Monkey one-minute refinement and the next-six cohort (Checkpoint 4). **Still required:** evidence schema integration and actual sample publisher replay before deployment.
- [ ] Verify `services/reviewed_foundation.py` and `research/current_stock_continuation.py` are connected to the correct source-selected forecast chain.
- [ ] Verify the merged web app/bridge imports and routes as a complete package, including `/`, `/experimental`, `/travel-decisions`, and legacy opt-in routes.
- [ ] Run full branch tests / static import checks, inspect missing dynamic imports, publisher model provenance, stale-data behavior, and bot integration.
- [ ] Compare enabled systemd service/timer references and live scripts against actual module paths. **Do not archive any code used by an enabled timer, fallback, rollback, or bot command.**
- [ ] Prepare a **separate** archival/retirement PR with a rollback tag and proven-unreferenced file inventory.
- [ ] Do not merge this PR, update `main`, deploy to VM, or modify user's VS Code worktrees without explicit verified handoff.

### How to resume after an interrupted conversation

1. Open [draft PR #17](https://github.com/fungjkTorn/torn-fren/pull/17) and this checkpoint file on its head branch.
2. Read the latest GitHub commit SHA from PR #17; do not assume a stale SHA in chat is still current.
3. Compare changed-file inventory with the captured source manifest and audit issue #16.
4. Continue from **Checkpoint 3** in small, tested commits. Update this file/PR after each logical change.
5. Preserve uncommitted local `data/` and user historical audit text files; **never** use `git add .` indiscriminately.

**This is intentionally an unmerged, non-deployable work-in-progress.**

## Checkpoint 4 — 2026-11-12, verified review-branch state

**Completed since checkpoint 3**
- Production graph `beta.js` and `beta.css` copied to the remote review branch with exact expected Git blob hashes.
- Production `web/first_release_bridge.py` captured to include next-six and final-pair cohorts; app routes merged to retain production light-graph behavior alongside existing feature-gated research APIs.
- Reconciled publisher and schedule preserve both November Monkey minute refinement and current next-six leave-now model policy. Added the source-reviewed foundation and current-stock continuation helpers.
- Production simulated-trip evidence now treats **quantity >= 30** as successful; added threshold regression tests.
- Added read-only source reference audit tool and two tests; it labels unreferenced candidates as **review only**, never as deletion-approved.
- Created archival checkpoint branch `archive/pre-production-sync-20261112` pointing to the original release commit; no files have been removed.
- Current draft PR: https://github.com/fungjkTorn/torn-fren/pull/17; draft status remains enforced.

**Test evidence:** 15 targeted collector/freshness/cache/publisher checks, 2 reference-audit checks and 3 arrival-threshold checks passed locally (20 total). These are isolated checks against captured production source / test copies, **not** full branch CI or live verification.

**Outstanding:** full branch checkout and tests; all three website pages with current routes and assets; reconcile deployed `web/static/index.html` and bot contract; dynamic dependency analysis including enabled timer unit files; prove non-use before any legacy-code retirement PR. The user has **not authorized a merge or deployment**.
