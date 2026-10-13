# V163 Event-first 24-item Restock System — Oct 13, 2026

## Why this is the correct product pivot

User's actual V162 collector audit: **7 days** included 182 clean Nessie threshold restocks, 76 Japan Xanax, 189 Jaguar. The newer private V160 recorder logged **79** five-minute 24-item batches (~6h35), not seven days; Nessie had **77/79** V151 departure proposals, while Japan Xanax had **0/79** due to `NO_TWO_BIN_SUPPORTED_DEPARTURE` (not a missing collector restock). V161 scored ONLY the first issued forecast per item and UTC hour, then only matured scoreable proposals. Its 3/4 Nessie result is not a restock count.

The product must **model restock events first** rather than discard any upcoming restock that cannot immediately produce a robust arrival-bin recommendation. A useful board should display the next predicted restock(s) and the associated flight reachability, estimated leave-at/leave-by times and countdowns. A restock may be predicted but already unreachable for a specific country's travel duration.

## Implemented on research branch (NO production model promotions)

1. `deploy/scripts/v163_readonly_event_first_preview.py`: self-contained read-only live 24-item future event baseline. Uses only previously observed threshold durations with V145 benign-provider continuity; conditions on the current censored HIGH/LOW phase; emits **each modeled replenishment within 8h**, including unreachable events, from repeated phase duration estimates (not random unsupported waits). Predicts early/median/late onset estimates, stocked-end estimate, first and latest expected departure considering PI+pilot and 10-second arrival grace. Flags conservative model-estimate window when one exists, incomplete observation history, overdue phase lacking survivor analog, events beyond current flight and forecast-list truncation. Item restocks are not assumed deterministic or 90% accurate.
2. Same CLI `--historical-replay-days 7`: *historical as-of reconstruction* using nonoverlapping four-hour issuance windows (each cohort uses only stock changes <= issue). Reports **ALL** observed clean same-provider <30→>=30 restocks inside the next four hours as the recall denominator, all forecast events as the precision denominator, matches one-to-one within ±10m by default, counts actual missed events and false projected ones, plus explicit exclusions of provider-switch/gap crossings. These numbers are a **historical initial challenger benchmark**, **NOT truly prospective 5-minute replanning performance**. Every proposed event within an eligible evaluation period is scored, even if impossible for a specific flight. Use this to decide whether the new baseline improves anything before presenting it as a champion.
3. `deploy/scripts/v160_single_item_recheck.py` now performs the V163 event-first forecast **inside the same pinned read-only transaction** as the existing V151 one-item recheck (one selected item on user click). No new writes to V160 forward sidecar or collector, no background gameplay, no API keys. Also retains V151 independent/paired diagnostics as distinct score-curve projections.
4. `deploy/scripts/v160_private_beta_board.py` adds the full selected-item **restock timeline**, predicted restock and stock depletion, live countdown, estimated earliest departure, latest departure, and explicit `UNREACHABLE for this flight` states. It does not erase early missed opportunities and does not truncate the list (up to 64 events under bounded horizon). For Japan, V151 may still abstain while V163 outputs approximate restocks, prominently **not validated as safe-to-fly**.
5. Existing rollback-safe private beta upgrade, `deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh`, now stages all three pinned files (beta board + selected-item recheck + V163 engine), does a REAL current Jaguar recheck with engine loaded before restart, backs up/restores the engine and prior viewer on errors, waits up to 40s for new localhost 24-item API readiness, and does not touch original V2, /experimental, any collector, V75/V128 timers or active V160 recorder.

**CI:** Four workflows green for source `a643dee513b6793bb2c01eb6538092722e5ed64d` including [V85 run 38485969404](https://github.com/fungjkTorn/torn-fren/actions/runs/38485969404) with event simulation, long flight Japan, no-lookahead, gap, event-level precision/recall, VM fixture, UI JS syntax, API authorization and zero-write tests. Pinned upgrade operator commit `7a2f51c1a3a59f09badc6062a872f98bc557f628`.

## VM one-block deployment and research audit (must be executed by user)

This uses only the EXISTING VM and SSH credentials and changes only the isolated private viewer service, not website or collector.

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$branch = "research/v38-full-roster-live-prep-20261009"
$sourcePin = "a643dee513b6793bb2c01eb6538092722e5ed64d"
$operatorPin = "7a2f51c1a3a59f09badc6062a872f98bc557f628"
$work = "cd /home/ubuntu/torn-fren-v38-probe"
if (-not (Test-Path -LiteralPath $key)) { throw "SSH key missing" }

Write-Host "===== HISTORICAL EVENT FORECAST BASELINE (READ ONLY) ====="
$replay = "$work && git fetch -q origin $branch && git show " +
  $sourcePin + ":deploy/scripts/v163_readonly_event_first_preview.py" +
  " | timeout 150s nice -n 19 .venv/bin/python - --historical-replay-days 7"
& ssh -i $key $remote $replay
if ($LASTEXITCODE -ne 0) { Write-Warning "V163 event-level replay did not complete; collect exact output" }

Write-Host "===== SAFE PRIVATE BETA EVENT-TIMELINE UPGRADE ====="
$upgrade = "$work && git show " +
  $operatorPin + ":deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh | bash -s"
& ssh -i $key $remote $upgrade
if ($LASTEXITCODE -ne 0) { throw "V163 private beta upgrade failed: $LASTEXITCODE" }

Write-Host "Refresh your existing http://127.0.0.1:8765/ page"
```

If port 8765 is still SSH-tunneled, refresh. Under `Recalculate this item NOW`, choose Nessie or Japan Xanax to see its full event timeline. Until the user's VM output confirms it, **V163 live beta is NOT verified installed**. A commit does not update VM service automatically. Historical event-precision/recall scores cannot be filled in yet without actual VM replay.

## Honest success metrics and immediate next decisions

Evaluate and optimize all 24 items on:
- **Restock recall**: correctly matched actual observed restock events / ALL clean observed restocks within forecast evaluation windows.
- **Event timing**: timing error against poller-observed threshold restock (e.g. ±5m or ±10m), **plus false forecast event rate/precision**. Don't get 100% recall by predicting restocks constantly with 0% precision.
- **Earliest-departure availability**: eligible stock windows predicted sufficiently early for each country's flight.
- **Stock ≥30 on arrival**: V88 successful poll brackets for genuinely issued departure predictions. Actual flights aren't needed for the chosen stock proxy.
- **Coverage and censoring**: issued model forecasts, abstentions, pending, unknown, provider ambiguity, overdue history, correctly observed threshold depletion. Avoid claiming V161 per-hour proposal hit rates count all restocks.
- **Future reconfirmation**: replan every five minutes, preserve first-issued forecasts, and score each distinct restock event once.

**90% is a TARGET, not an achieved result.** Current V163 baselines cannot be trusted without historical audit then separate genuinely prospectively issued event-level confirmation, particularly for rapid Japan Xanax stock windows. Do not simply loosen the V151 .60 floor to manufacture 90% coverage.

## Public website is still not V163 integrated

Original V2 graph and experimental board preserved. The localhost beta is a research preview. Deployed `web/app.py` and HTML drift from repository; read/compare actual deployed version before additive public feature-flag integration and tested rollback. Never publish the unvalidated event model as confident departure permission.
