# V160/V161: actual prospective 24-item departure evidence

## Why this step matters
The V146–V159 comparisons were reconstructed historical as-of evidence, subject to collector backfills and correlated issue cohorts. They provide useful research direction, but are not genuinely *prospectively frozen* recommendations.

## What has been implemented
**V160** (`research/v160_prospective_v151_shadow.py`) captures V151 independent and V151 paired-cycle recommendations for all 24 exact roster items *now*, from one read-only SQLite snapshot. It stores every item, including model abstentions, with issuance, source heartbeat, phase onset, confidence caveats, exact country flight, model proposal and proposed wait. Issuance is immutable, append-only to NEW private `/var/lib/torn-fren-v38/v160_v151_prospective24.db` (only on explicit record); default preview does not write. No forecast is retroactively reconstructed or made with a future timestamp.

**V161** (`research/v161_prospective_v151_forward_report.py`) scores only such already recorded forecasts after flight-arrival maturity using V88 poll-bracketed stock-at-arrival evidence. Unknown and pending are separated from missed and abstained. It compares V151 independent, paired, and the same-issue leave-now choice on *matched* scoring evidence, records whether future waits were reconfirmed by later actual issues, and groups the original issue phases. Scores are not certified player flights or guaranteed country provider freshness.

Where available, the **real V75 private specialist research ledger** is read separately. A V75 proposal qualifies only if actually issued within the 180 seconds preceding V160 issuance and still valid at that moment, with truthful <=180-second stock age and flight duration. These are labeled *near-issued*, not exact simultaneous snapshots. No assumption that a roster specialist name represents a genuine recorded forecast. Missing/invalid V75 comparisons remain absent rather than invented.

No existing V2 graph, 24-item experimental dashboard, V75/V128 services, collectors, sidecars, timers, or live models are changed.

## Guarded opt-in operator
The pinned operator `deploy/scripts/v160_forward24_operator.sh` supports `status` (read-only), `smoke` (no-database-write preview), `record` (explicit one-off immutable V160 sidecar issue), `enable` (a smoke first, then enable only NEW isolated five-minute V160 timer), `report` (read-only prospective V161 two-day results), and `disable` (only V160 timer). The private service runs low-priority with 30% CPU quota, 512MB memory limit, 150s timeout, private network disabled, strict filesystem sandbox and private lock file.

**Nothing has been installed on your VM by committing code.** The operator actions require SSH access; GitHub CI validates code but cannot certify the VM's live heartbeat or Linux permissions.

## PowerShell smoke and activation
This uses explicit variables; it does not depend on a previous PowerShell session.

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
if (-not (Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
$branch = "research/v38-full-roster-live-prep-20261009"
$pin = "ef96aeaa0ec75cf3992ae9e2d77615f34243d3f7"
$operator = "deploy/scripts/v160_forward24_operator.sh"
$prefix = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch"
$command = $prefix + " && git show " + $pin + ":" + $operator + " | bash -s -- smoke"
& ssh -i "$key" "$remote" "$command"
Write-Host "Exit code: $LASTEXITCODE"
```

**Only after explicit user approval for NEW scheduled private ledger writes**, replace the final word `smoke` with `enable` to start the isolated five-minute forward study. For read-only `report`, or `disable`, change that final word similarly. All run against the pinned research code.

## Next validation gates
Collect genuinely frozen issues over multiple complete restock cycles and country flights. Check mature matched V151 paired versus independent and actual V75 private candidates, proper abstentions, and reconfirmation near future departures. Re-evaluate by independent restock/phase episodes before promoting any item to experimental beta. Japan Xanax remains a separate survival/timing problem; never force a recommendation below its confidence gate. Only validated per-item strategies should be promoted by a reversible additive integration to the *experimental* view, preserving the original V2 page and all specialist functionality.


### Oct 13 forward-report integrity correction
The operator at commit `ef96aeaa0ec75cf3992ae9e2d77615f34243d3f7` stages CI-validated research source commit `da6db7cee81588b38cb8ee522be611ad7e173bda`. V161 now counts PENDING separately from UNKNOWN and MISS for all models, leave-now, and V75; distinguishes pending future WATCH confirmation from genuinely unreconfirmed due departures; and includes guarded 24-item readiness metadata (incumbent is roster metadata until a real matched V75 forecast exists). Historical handoff VM-check corrections: [Oct 13 reconciliation](OCT13_HANDOFF_RECONCILIATION_AND_FORWARD_READINESS.md). Neither the operator commit nor this document installs a VM timer.

The updated `status` action now prints the last three actual private issue batches, their expected and recorded row counts and age, querying the V160 sidecar in SQLite **mode=ro**. If the sidecar is absent it reports no verified recorded issues. It never silently treats an enabled timer as proof of complete predictions. This operator enhancement has automated tests on the research branch; the status command is observational and does not install/enable the private timer.
