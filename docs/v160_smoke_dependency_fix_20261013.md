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
