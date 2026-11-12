# Controlled source synchronization release — Nov 12, 2026

## Evidence and scope

R2 operator staging passed all five native publishers: first-ten 10 items (9.1s), challengers 6 (16.7s), next-six 6 (17.8s), final-pair 2 (40.1s), private Japan 1 (2.2s). Existing model identities were retained. Production code/services/ledgers were not changed by those tests. Actual bot unit is `torn-fren-bot.service`, active.

A final storage compatibility check found the generic evidence writer could repeat pending outcomes every poll. Retain the first PENDING outcome and immutable issue; suppress further PENDING duplicates, but allow final SUCCESS/FAILURE/UNKNOWN outcomes. Added a real SQLite regression verifying original issue preservation and final resolution. No historical rows are deleted or compacted. The installed first-ten reporting wrapper remains unchanged.

Versioned release health can read its immutable DEPLOYED_RELEASE.json when .git is absent; real Git identity retains priority. Added metadata validation tests. This keeps the admin page's source identity meaningful after a versioned cutover.

## Reproducible operator source

- `deploy/scripts/build_source_sync_bundle.py`: pin a public commit, exact four private overlay Git blobs, and the read-only baseline report. Private source/data are not committed to this repository.
- `source_sync_candidate_stage.py`: disposable copied-input native publication check; no service/source/state cutover.
- `source_sync_final_pair_entry.py`: source-checksum-pinned public final-pair 200000-row reader override; private Japan retains its original bound.
- `source_sync_cutover.py`: template with source, bundle and merged-main identities bound by the generated operator artifact.

## Cutover behavior

1. Verify bundle and current critical source hashes, effective launch identities, state/model arguments and external wrapper identity.
2. Run the final candidate on disposable copies before changing live settings. Fail closed if any publisher fails.
3. Install separate public and private immutable source directories. Shared data and .env are links to the existing /opt/torn-fren paths; no data copy or migration. Preserve all old release directories and original /opt source.
4. Smoke-test the candidate website locally before live switching. Use the existing interpreter and web environment without exporting credentials.
5. Back up previous per-service override files, launch definitions and installer in a root-only operations directory; record an explicit rollback command before touching schedules.
6. Pause only affected publisher/audit/recovery timers, wait for in-progress workers to finish, and install one reversible source-path override per unit. Existing service users, sandbox limits, source/state/model arguments and other drop-ins remain unchanged.
7. Restart collector/web/bot against the pinned public source; use the private source only for public final-pair/private Japan publishers. Run all five publishers once using the existing live inference/evidence paths and unchanged model identities.
8. Verify three pages, served assets, 24 unique public items, four fresh public feeds, collector freshness, active main services and original collector path. Restore timers and verify all five publishers advance on a subsequent scheduled tick.
9. On verification failure, restore old override definitions and restart the original launches. Never restore/delete live databases, caches or ledgers as part of source rollback. Forecasts and observations collected during deployment remain intact.

The release does not reset the user's Windows worktree, delete old data, merge private research into public Git or expose private Japan forecasts publicly. Main integration preserves both historical parent lineages. A clean main clone for VS Code follows verified VM deployment; existing local data and uncommitted edits stay untouched.

Local cutover tests cover override argument preservation, original drop-in/timer restoration, public/private source separation with shared data links, and archive traversal rejection. New evidence and metadata tests run in the production reconciliation workflow. The operator artifact must be executed as a real file so its backup installer and rollback path remain usable.
