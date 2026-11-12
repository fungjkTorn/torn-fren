# Torn-FREN sync checkpoint 5 — 2026-11-12

**Scope:** read-only classification of actual November VM source captures versus draft [PR #17](https://github.com/fungjkTorn/torn-fren/pull/17). These findings **do not authorize deployment, merger, or deletion**.

## Goal and source boundaries

- `main` is currently an older October commit; `sync/production-reconciliation-20261112` is the candidate code branch based on the November 10 release.
- The active web service uses `/opt/torn-fren`, while the enabled next-six publisher uses a separate versioned release. The production VM's own databases, credentials, state, scripts, and systemd units are **not** continuously synchronized with GitHub.
- Keep historical experiments, secret-bearing deployment packages, and non-production evidence separate from current public source. Historical archive branches are **not** replacements for working model dependencies.

## Classification of all nine remaining VM source differences

| Source path | Verified change in PR #17 relative to the captured production file | Decision |
| --- | --- | --- |
| `web/app.py` | Retains current light-graph/live bridge and adds optional V38 sidecar, shared-travel API, beta-timeline routes from the November release. Feature gated. | **Keep reconciled GitHub version**, test flags and route behavior |
| `web/first_release_assets/board.html` | Final line-ending/newline only; otherwise same page. | **Keep**; no functional gap |
| `web/static/admin.html` | Review branch has updated beta/clock cards, HTML escaping, oldest-backup metric and clearer runtime labels. | **Keep** newer health UI |
| `web/static/index.html` | New navigation shell, explicit (max 10m) legacy-V2 backup, and stale-freshness/zero-width travel safety checks. | **Keep merged version**; do not revert to old VM page |
| `services/admin_health.py` | Adds live-beta publisher status, backup-age and disk/collector health fields. | **Keep** newer API fields and admin widget |
| `services/frozen_candidate_worker_v31.py` | Adds transient SQLite read-only retry protection for living WAL collector database. | **Keep** retry safeguards |
| `services/history_service.py` | Adds provider export clock metadata, bounded efficient cycle counting, and transactional durable audit queue integration. | **Keep merged version**; add broader queue/clock regression tests |
| `services/prediction_v2_live.py` | Adds fail-closed expiry/depletion departure eligibility, model issuance provenance and time-bound validation. | **Keep** safety/provenance logic |
| `services/private_v18_champion_worker_v35.py` | Adds explicit isolated research allowlist while retaining frozen legacy pilot default. | **Keep** separated research gate |

The table classifies code-level diff, **not live runtime equivalence**. Even a deliberate difference requires integration/CI verification before release.

## Captured versioned publisher source comparison

Compared all available nonbinary files to Git blobs on PR #17:

| Captured release root | Exact same blobs | Intentionally or not-yet-reconciled blobs | Not in candidate repo |
| --- | ---: | ---: | ---: |
| `1781fb8...-next-six` | 335 | 15 | 7 |
| `6e3a5ed...-final-pair` | 331 | 19 | 17 |
| `2fa6365...-original/older release` | 325 | 14 | 0 |

Of the missing next-six/final-pair paths, **most are historical replay or deployment helper files**. However, these are **operationally material** and require explicit source ownership and tests:

- `services/final_pair_live.py` — scheduled final-pair publisher entry point is not yet in the candidate public repo.
- `services/checkpoint4_state.py` — Chamois selector cache dependency.
- `services/daily_forward_report.py` — daily reporting dependency.
- `research/remaining_three_policy.py`, `research/v169_incremental_checkpoint_selector.py`, `research/v45_online_template_probe.py` — private/research model dependencies (some paths may exist in public repo; evaluate import closure and confidentiality before publishing).
- `deploy/scripts/add_final_pair.py` and the special final-pair 200,000-row service wrapper — essential to reproducing the active launcher, but not safe to rerun old installer unreviewed.
- Live systemd unit/drop-in identities and timer-to-source links are **not yet fully captured**. Enabled status does not identify the deployed source version alone.

## Historical deployment archives

- Private November one-off installer ZIP: `torn-fren-research-private@archive/november-installers-20261112`; verified original ZIP checksum/commit.
- The six V39/V40 deploy and rollback scripts captured from production were saved, unmodified in a **separate private archive branch**: `archive/v39-v40-deployment-20261112`, commit `bb4245360e1ef6b056829c1ebdcc66ce0560200d`. These are **not** active deployment scripts and should not be executed on current VM.
- Public `archive/pre-production-sync-20261112` protects the original November release baseline, but is **not yet the complete legacy research archive**.

## Next gates

1. Broaden CI from initial targeted tests to active web/publisher/collector integration regressions. Keep canary and source provenance checks.
2. Determine final-pair and Japan publisher ownership, imports, dry-run behavior, and checked-in deployment configuration. Keep private research in private storage unless expressly cleared for public repository.
3. Obtain an explicit **sanitized read-only service/timer/drop-in manifest** for enabled VM units; no environment variables, bearer tokens, private DB contents or credentials.
4. Build a safe reachability map and list of *actually dead* modules; move historical-only scripts/research into private or archive branches before deleting from public active branch.
5. Verify full staging behavior and rollback, then merge source changes and synchronize `main` + VS Code **only after approval**.

**Never infer production readiness from source blob matches or targeted CI checks alone.**
