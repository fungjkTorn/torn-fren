# Home VM command queue — 12 October 2026

The user is currently away from their PC. Do not instruct them to run anything
until they say they are home. Keep these exact instructions accessible on the
research branch for continuation and in-chat copy/paste.

## Historical unfinished actions and current replacement

- The earlier V131 standalone read-only old-V75/new-V128 arrival audit was
  **not executed** when the user went upstairs. It remains pending evidence.
- The older original-V2 graph inspection / V134 + V135 morning combination also
  was not executed on the VM.
- **Do not rerun all those individually.** The current V139 one-shot operator
  already stages V129, V131, V132, V133, V134, V135, V137, V138 and invokes
  V138, which composes the relevant previous reports. This supersedes the
  older manual V131 and V136 operator instructions.
- V130 Monte Carlo challenger is still NOT deployed; do not deploy.
- Production, V38, V128 timer, original public graph and collector untouched.

## Windows PowerShell commands, when home

### 1. Verify recorder and timer health (read-only)

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"

& ssh -i $key $remote 'echo "===== TIMERS ====="; systemctl is-active torn-fren-v128-full24-shadow.timer; systemctl is-active torn-fren-v38-private-shadow.timer; echo "===== V128 LAST SERVICE ====="; systemctl show torn-fren-v128-full24-shadow.service -p Result -p ExecMainStatus -p ActiveState -p SubState --no-pager; echo "===== RECENT V128 RUNS ====="; journalctl -u torn-fren-v128-full24-shadow.service --since "12 hours ago" --no-pager -n 35'
```

This shows timer state and most recent job history, without running any
service. The one-shot service can be inactive between successful scheduled runs.

### 2. Run the enhanced historical accuracy audit (read-only)

```powershell
$auditLog = Join-Path $HOME "Desktop\torn-fren-v139-audit.txt"

& ssh -i $key $remote 'cd /home/ubuntu/torn-fren-v38-probe && git fetch origin research/v38-full-roster-live-prep-20261009 && git show 112d574d9767912367fb8fcaf0870828f1de0e82:deploy/scripts/v139_run_enhanced_departure_morning.sh | bash' 2>&1 | Tee-Object -FilePath $auditLog

Write-Host "Saved audit output to $auditLog"
```

If the output finishes with an error, capture the error. Do not run extra
`systemctl` or alter pinned research stage manually. V139 itself pins audit
modules at commit `142f10363037b31fc299183c7cfb0734cf7df50c`.

### 3. Give assistant evidence

Upload `torn-fren-v139-audit.txt` from the Windows Desktop or paste the
text; include timer/health output. Do not post API keys, tokens or contents
from any secrets files.

## How to read the evidence

V139 reports:
- Old original Prediction V2 archived restock/window/cycle results (V134).
- Old original Prediction V2 actual frozen arrival >=30 stock poll-state
  proxy and earliest-browser departure vs same-issue leave now (V137).
- Older V75 as-issued arrival >=30 proxy and matched leave-now (V131).
- New V128 first-issued hourly arrival proxy, pending/unknown and matched
  leave-now (V129/V131).
- V128 five-minute timing drift, WATCH-to-near-departure confirmation and
  abstentions (V132).
- Per-item metrics and source-coverage caveats (V135/V138).

The previous first verified V128 database status was just one 24-row batch
(issue timestamp 1791773040). Continuous overnight V128 recording has NOT
been verified by the assistant; VM logs/ledger must confirm it.

None of these audits certify exact in-game stock or successful purchases.
Global collector heartbeat cannot prove fresh per-country stock timestamps.

## Product direction after data

Refer to `docs/v2_first_product_recenter_20261012.md`: preserve the V2 graph
as the primary product, use the experimental work to improve restock/depletion
and departure predictions, then build a travel assistant as a consumer of the
same shared forecasts. No further aimless version/model tournaments.
