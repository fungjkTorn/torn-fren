# V160 first VM smoke: missing staged dependencies; packaging fix (13 Oct 2026)

## Observed, not inferred
The user executed the pinned `status` and no-ledger-write `smoke` actions on the VM.

- Status returned `not-found`, `inactive`, `0 timers listed`, and **no V160 private sidecar file**.
- Smoke confirmed the research Git checkout and staged pinned files, then failed during module import:
  `v160_forward_shadow_launcher.py -> v125_earliest_credible_shadow.py -> v123_empirical_phase_survival_challenger.py -> research.v110_multicycle_restock_horizon_audit`.
- It ended with `ModuleNotFoundError` for V110, exit status 1. It **never recorded a V160 forecast** or installed/enabled the V160 timer. No evidence of changes to collector, V75/V128 or either website.
- This was an isolated **staging/dependency packaging defect**, not a model accuracy test. Do not call the smoke successful.

## Fixed in research branch
The operator now stages **both missing transitive dependencies**, `v110_multicycle_restock_horizon_audit.py` and `v38_snapshot_schema.py`, from the same pinned source commit as all the V160/V161 modules.

The launcher now limits `research.__path__` to the pinned stage and checks that every transitive `research.*` import loaded from the stage, instead of silently falling back to the mutable VM research checkout.

The new regression tests in `tests/test_v160_forward_operator.py`:
- Recursively inspect Python AST imports for all explicitly bundled `research.*` files and require closure.
- Build a temporary stage containing ONLY the operator-listed modules, actual helper package and roster; run the real launcher import in a new Python subprocess.
- Remove V110 from that stage and confirm the import fails closed even if the checkout contains V110.
- Preserve all existing V160 observer/operator safety tests.

**Four GitHub Actions workflows passed at tested source commit** `0164d64c0c94f045a9e6680054edc780738bcb63`, including isolated packaging tests in V85 research workflow: `38432225629` (success). The corrected deploy operator was committed as `22e45cb287937315b75a463ca4ef0277cae57205`, and pins the tested source SHA `0164d64...`. This GitHub result **does not certify the next VM smoke or enable any service**.

## Safe repeat — smoke only (no private DB writes)

Open PowerShell on the PC with the SSH key:

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$branch = "research/v38-full-roster-live-prep-20261009"
$pin = "22e45cb287937315b75a463ca4ef0277cae57205"
$operator = "deploy/scripts/v160_forward24_operator.sh"
if (-not (Test-Path -LiteralPath $key)) { throw "SSH key missing" }
$cmd = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch && git show " + $pin + ":" + $operator + " | bash -s -- smoke"
& ssh -i "$key" "$remote" "$cmd"
Write-Host "V160 smoke exit code: $LASTEXITCODE"
```

Expected if the environment permits completion: `V160_PRIVATE_PREVIEW_NO_WRITES`, roster 24, `sidecar_written:false`, `collector_written:false`, then `SMOKE PASS; V160 timer is NOT enabled or installed`. Model forecasts may abstain based on actual source state, and this is not a mature forecast accuracy measurement. A smoke can fail for other VM-specific reasons; report its exact output rather than assume success.

**Do NOT run `record` or `enable` without user approval**. Next phase after a passing smoke and explicit approval: enable only isolated five-minute V160 prospective ledger, observe repeated batches, and score mature V161 outcomes by item versus leave-now and genuine near-issued incumbent V75 candidates. No production or deployed UI changes.


## Corrected VM smoke PASSED — verified user output (Oct 13, 2026)

The user ran the corrected operator pinned at `22e45cb287937315b75a463ca4ef0277cae57205`. **The second smoke succeeded (exit 0)**. Its actual compact output:

```json
{"collector_written": false, "decision_statuses": {"RESEARCH_ONLY": 24}, "forward_lookahead_used": false, "issued_epoch": 1791910088, "latency_seconds": 5, "model_candidates": {"independent": 15, "paired_complete": 15}, "real_player_flights_verified": false, "roster": 24, "sidecar_written": false, "source_heartbeat_age_seconds": 27, "specialists_untouched": true, "status": "V160_PRIVATE_PREVIEW_NO_WRITES", "websites_untouched": true}
```

The operator printed `SMOKE PASS; V160 timer is NOT enabled or installed`. The successful smoke verifies the isolated import package and one real VM preview with all 24 item identities, 27s collector heartbeat age and 5s capture latency. Each V151 variant offered **15 model-specific departure candidates** in this preview, with no proof that the two 15-item sets are identical. The 24 `RESEARCH_ONLY` statuses do NOT mean all 24 items had departure recommendations or validated forecasts.

**At the smoke conclusion:** no V160 sidecar rows were written; no V160 timer was installed; no real forward arrivals or player flights were verified. There is still NO prospective V161 accuracy number or warranted model promotion. Preserve the original V2 graph, deployed `/experimental`, V75 specialists and V128 timers.

### Next gate (requires explicit operator authorization)

After the user affirmatively approves NEW isolated five-minute private V160 scheduled ledger writes, use the tested `enable` action only, which runs a second no-write smoke before installing/enabling `torn-fren-v160-forward24.timer`. Then inspect timer, actual `v160_ticks` batches and 24 immutable rows per issued tick. Subsequent V161 read-only reports must distinguish `PENDING`, `UNKNOWN`, `MISS`, abstention and WATCH confirmation, and compare only matched mature pairs. No production site or collector mutation is approved.


## User-approved V160 five-minute recorder ENABLED, first immutable 24/24 issue CONFIRMED

The user explicitly approved starting isolated V160 research recording. The operator `enable` reran the **successful no-write preview**, producing 24 research-only items, source heartbeat age **4 seconds**, **6 seconds** latency, independent V151 **17 candidates** and paired-complete V151 **17 candidates** (proposal coverage ONLY, NOT accuracy).

The operator output then confirmed: `Only new V160 private timer enabled. V75/V128/V2/experimental site untouched.`

The subsequent operator **status** returned `enabled`, `active`, a scheduled next timer occurrence **2026-10-13 17:01:00 UTC**, prior run at **16:56:00 UTC**, and an existing permission mode `-rw-------` **40K** private SQLite database at:

`/var/lib/torn-fren-v38/v160_v151_prospective24.db`

Most importantly, **the first independently issued five-minute prospective batch is verified complete**:

```json
{"status":"V160_PRIVATE_LEDGER_READ_ONLY_STATUS",
 "has_prospectively_recorded_batches":true,
 "last_three_batches":[{
   "issued_epoch":1791910560,
   "captured_epoch":1791910579,
   "issued_age_seconds":25,
   "expected_items":24,
   "recorded_items":24,
   "batch_complete":true
 }],
 "collector_and_websites_untouched":true}
```

This supersedes the earlier section's `timer not enabled` milestone. The earlier section remains to document the historical smoke failure and fixes. **The recorder is NOW ACTIVE**, although one complete batch does NOT demonstrate recurring persistence yet. No player flight, actual Torn purchase, forward stock-at-arrival hit rate, country-specific feed freshness, or V75 model superiority has been verified.

### Low-risk follow-up for the beta

1. On a later VM check, run the pinned operator `status` (read-only) and verify last three batches are timely and have exactly 24 rows each. Watch `journalctl -u torn-fren-v160-forward24.service` for service errors, and `systemctl show torn-fren-v160-forward24.timer -p ActiveState -p SubState` to detect stalled schedules.
2. After flight horizons and stock observations mature, run pinned `report` (read-only V161) and compare *paired vs independent*, actual as-issued *leave-now*, and valid *near-issued V75* only on matched scoreable outcomes. **PENDING, UNKNOWN, future WATCH not yet due, and ABSTAIN are not misses.** Avoid a positive hit-rate interpretation based on very few independent restock/depletion phases.
3. Continue research-branch, rollback-safe work toward adding validated forecast guidance to BOTH existing original V2 graph and `/experimental`. Reconcile actual deployed source drift before touching website assets.
4. Changes to the staged pinned research bundle are **not automatically deployed** by GitHub commits; this running service remains pinned to tested source `0164d64c0c94f045a9e6680054edc780738bcb63` until a deliberate reviewed operator change and operator execution. Do not silently overwrite the operating study.

The user has not approved any production website/collector modification, gameplay automation, or other independent scheduled services.
