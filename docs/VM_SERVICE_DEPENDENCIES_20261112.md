# VM service dependency checkpoint — 2026-11-12

**Read-only evidence; not deployment approval.** Source: owner's sanitized `TORNFREN_SANITIZED_SYSTEMD_DEPENDENCIES_V1` snapshot at **2026-11-12 15:04:02 UTC**. Raw service arguments, secret-bearing environment, database contents, and SSH credentials were deliberately excluded.

## Observed service inventory

- **23 services**, **18 timers**; **12 timers enabled**, **6 disabled**.
- Website, Discord bot and poller were running in `/opt/torn-fren` at observation time.
- The enabled 5-minute physical forward research timer was installed; this does *not* prove each prospective sample is fresh or every run succeeds.
- Enabled first-ten, next-six and challenger timers have service entry points in *versioned release directories* rather than the main web working directory. Preserve these roots until reproducible deployment is verified.

| Timer / unit family | Schedule status | Associated service at capture | Runtime source or concern |
| --- | --- | --- | --- |
| `torn-fren-first-ten-beta` | enabled | inactive, last result successful | versioned first-ten release; reporting wrapper outside public checkout |
| `torn-fren-next-six-beta` | enabled | inactive, last result successful | `services.next_six_live` from next-six release |
| `torn-fren-challengers-beta` | enabled | activating | `services.challenger_live` from challengers release |
| `torn-fren-final-pair-beta` | enabled | **failed (exit-code)** | external recovery `final_pair_entry.py`, versioned final-pair release |
| `torn-fren-japan-private` | enabled | **failed (exit-code)** | `services.final_pair_live`, separate private Japan recording path |
| `torn-fren-v48-cache-warmup` | enabled | activating | `research.v48_cache_warmup`, research working directory |
| `torn-fren-routine-audit` | enabled | inactive, last success | `services.durable_audit_queue_v39` in web root |
| `torn-fren-gap-recovery` | enabled | activating | `research.v38_gap_recovery` in web root |
| `torn-fren-research-physical-forward-5m` | enabled | inactive, last success | separate research-runner shell working directory |
| backup / forward snapshot / research snapshot | enabled | inactive, last success | independent archived/research scripts |

Other installed timer families (`shadow-capture`, `v128-full24-shadow`, `v160-forward24`, `v38-private-shadow`, `v82-pair-forward`, `v85-japan-forward`) were **disabled**. Disabled is a retirement candidate, not evidence a module's shared source can safely be deleted.

## Japan distinction: old V85 vs current private recorder

- `torn-fren-v85-japan-forward.timer` was **disabled and inactive**; the static service was inactive and launched `research.v84_japan_forward_canary`. Its residual systemd unit files are retirement candidates.
- `torn-fren-japan-private.timer` was **enabled** but its service **failed**; this is **not** the same as the V85 historical canary. It uses `services.final_pair_live` in the recent final-pair release and selects `JAPAN_QUANTITY_RATE / strict31` (Japan Xanax) in its captured source.
- The redacted unit capture does *not* establish whether the runtime command includes `--private-japan`, whether recent valid evidence was recorded, or the failure cause. Do not characterize this as a functioning current Japan model until verified.
- A separate operator-only script `Cleanup-TornFren-LegacyJapanV85.ps1` was prepared to archive then remove **only** the V85 service/timer definitions. **VM execution is unconfirmed**; this document must not mark the retirement as completed.
- Retain the V84 Python module in the shared research checkout pending code-level dependency review. Archiving/removing the unit files does not itself clean all source from the VM.

## Final-pair and 200,000-row reader

The final-pair unit has the `96-bounded-history-reader.conf` drop-in **installed** as well as a recovery wrapper under `/usr/local/lib/torn-fren-publisher-recovery/`. The snapshot's `chamois_200000_row_override_present=false` result is **not conclusive**, because the detector inspects a limited unit-configuration surface. The actual row limit may live inside the wrapper. Both the public final-pair publisher and private Japan service were failed at the capture, so no live-success claim is appropriate.

## Source-retirement and merger gates

1. Keep every **enabled timer target** and its transitive imports as active dependency roots. Do not infer roots solely from static Python imports.
2. Keep the external wrapper files, feature-gated public routes and versioned release dependencies until their source and purpose are documented.
3. Preserve old unit files in a VM-local backup, with reversible uninstall, before decommissioning a disabled legacy timer. Never run the older migration/repair script for this narrow task.
4. Diagnose current final-pair and Japan service exit causes through sanitized logs, inspect whether the actual final-pair 200,000-row override is effective, and verify fresh publisher records.
5. Test all needed web/bot/collector/publisher/source contracts before merging `main`, then synchronize the local VS Code checkout. Do not overwrite live databases or private research state.

The `tools/audit_source_references.py` inventory now supports `--vm-unit-report` using the sanitized schema. It adds enabled VM timer targets and their active service modules to conservative reachability roots, and explicitly records absent public source/external wrappers. Its output remains **review-only; automatic deletion is always forbidden**.

**Status:** `main` and production untouched. Source PR #17, integration PR #18 and historical removal PR #19 remain separate review paths.
