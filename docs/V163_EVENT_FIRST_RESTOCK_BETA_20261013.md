# V163 Event-first 24-item Restock System — Oct 13, 2026

## Why this is the correct product pivot

User's actual V162 collector audit: **7 days** included 182 clean Nessie threshold restocks, 76 Japan Xanax, 189 Jaguar. The newer private V160 recorder logged **79** five-minute 24-item batches (~6h35), not seven days; Nessie had **77/79** V151 departure proposals, while Japan Xanax had **0/79** due to `NO_TWO_BIN_SUPPORTED_DEPARTURE` (not a missing collector restock). V161 scored ONLY the first issued forecast per item and UTC hour, then only matured scoreable proposals. Its 3/4 Nessie result is not a restock count.

The product must **model restock events first** rather than discard any upcoming restock that cannot immediately produce a robust arrival-bin recommendation. A useful board should display the next predicted restock(s) and the associated flight reachability, estimated leave-at/leave-by times and countdowns. A restock may be predicted but already unreachable for a specific country's travel duration.

## Implemented on research branch (NO production model promotions)

1. `deploy/scripts/v163_readonly_event_first_preview.py`: self-contained read-only live 24-item future event baseline. Uses only previously observed threshold durations with V145 benign-provider continuity; conditions on the current censored HIGH/LOW phase; emits **each modeled replenishment within 8h**, including unreachable events, from repeated phase duration estimates (not random unsupported waits). Predicts early/median/late onset estimates, stocked-end estimate, first and latest expected departure considering PI+pilot and 10-second arrival grace. Flags conservative model-estimate window when one exists, incomplete observation history, overdue phase lacking survivor analog, events beyond current flight and forecast-list truncation. Item restocks are not assumed deterministic or 90% accurate.
2. Same CLI `--historical-replay-days 7`: *historical as-of reconstruction* using nonoverlapping four-hour issuance windows (each cohort uses only stock changes <= issue). Reports **ALL** observed clean same-provider <30→>=30 restocks inside the next four hours as the recall denominator, all forecast events as the precision denominator, matches one-to-one within ±10m by default, with **separate strict 15-second and 60-second recall** using the same all-restock denominator, counts actual missed events and false projected ones, plus explicit exclusions of provider-switch/gap crossings. These numbers are a **historical initial challenger benchmark**, **NOT truly prospective 5-minute replanning performance**. Every proposed event within an eligible evaluation period is scored, even if impossible for a specific flight. Use this to decide whether the new baseline improves anything before presenting it as a champion.
3. `deploy/scripts/v160_single_item_recheck.py` now performs the V163 event-first forecast **inside the same pinned read-only transaction** as the existing V151 one-item recheck (one selected item on user click). No new writes to V160 forward sidecar or collector, no background gameplay, no API keys. Also retains V151 independent/paired diagnostics as distinct score-curve projections.
4. `deploy/scripts/v160_private_beta_board.py` adds the full selected-item **restock timeline**, predicted restock and stock depletion, live countdown, estimated earliest departure, latest departure, and explicit `UNREACHABLE for this flight` states. It does not erase early missed opportunities and does not truncate the list (up to 64 events under bounded horizon). For Japan, V151 may still abstain while V163 outputs approximate restocks, prominently **not validated as safe-to-fly**.
5. Existing rollback-safe private beta upgrade, `deploy/scripts/v160_beta_decision_and_recheck_upgrade.sh`, now stages all three pinned files (beta board + selected-item recheck + V163 engine), does a REAL current Jaguar recheck with engine loaded before restart, backs up/restores the engine and prior viewer on errors, waits up to 40s for new localhost 24-item API readiness, and does not touch original V2, /experimental, any collector, V75/V128 timers or active V160 recorder.

**CI:** Four workflows green for source `0bb7210532440faac4d1ec8a8fe3f4833effa3e9` including [V85 run 38486340571](https://github.com/fungjkTorn/torn-fren/actions/runs/38486340571) with event simulation, long flight Japan, no-lookahead, gap, event-level precision/recall, VM fixture, UI JS syntax, API authorization and zero-write tests. Pinned upgrade operator commit `4be871958055ddd06e9e5a1b915c4a8bd45176f6`.

## VM one-block deployment and research audit (must be executed by user)

This uses only the EXISTING VM and SSH credentials and changes only the isolated private viewer service, not website or collector.

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$branch = "research/v38-full-roster-live-prep-20261009"
$sourcePin = "0bb7210532440faac4d1ec8a8fe3f4833effa3e9"
$operatorPin = "4be871958055ddd06e9e5a1b915c4a8bd45176f6"
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

**Latest refinement:** V163 fixed-window historical replay now reports ALL-event recall within 15 seconds, 60 seconds, and ±10 minutes, plus predicted-event precision; report each separately rather than claiming a broad 10-minute result meets the user's 90% high-precision ambition. JavaScript beta event cards now have live restock and leave countdowns and display all bounded future events. Remember the replay issues every four hours, whereas the user's live target is five-minute replans: do not conflate them.


## Oct 13 ~20:01 local: real beta success; event replay failed before any output

The user's COMPLETE Windows PowerShell output confirmed the isolated V163 beta was successfully installed: 24/24 fresh V160 issue rows, Jaguar V163 `EVENT_TIMELINE_FORECAST_AVAILABLE` with **11 future Jaguar event estimates**, `V163 EVENT ENGINE PREFLIGHT PASS`, then private website HTTP readiness `attempts=3, http=200, records=24, source_healthy=true, status=V160_BETA_HTTP_READY` and `SUCCESS: live private beta updated`. Both original web views, collector, and V160 recorder untouched. There is **no live or historical V163 event recall percentage** in this log.

The script preceding the upgrade emitted only `WARNING: Historical replay did not complete`, no table or exception. Possible 150-second timeout; actual remote exit code not supplied. Original replay rescanned all observed rows and recomputed completed phases **at every one of ~42 four-hour issue points per item**, multiplying work across 24 items. This is inefficient.

**Optimization committed to `deploy/scripts/v163_readonly_event_first_preview.py`**: one incremental causal `_ReplayPhases` scan per item, indexed one-time observed threshold crossings, binary-search cohort restock events, and line-buffered per-item progress so next failure localizes the bottleneck. A regression compares all phase fields and durations with `provider_continuous_phases` on mixed-provider changes and an interrupted collection gap, and confirms indexed actual restock truth parity. V85 CI [38489081511](https://github.com/fungjkTorn/torn-fren/actions/runs/38489081511) passed. **This optimization only changes historical replay on the research branch, not the working VM beta.**

For the next historical test, use the passing source commit `f92d7c0b564eea2eb9ab00aed07d15e3de9b2d02`, 180-second upper bound, stderr per-item progress, and show remote exit code. **Do not rerun the beta installer: it succeeded.** Await genuine timing recall / precision output before claiming any forecast accuracy or changing production.

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$branch = "research/v38-full-roster-live-prep-20261009"
$pin = "f92d7c0b564eea2eb9ab00aed07d15e3de9b2d02"
if (-not (Test-Path -LiteralPath $key)) { throw "SSH key missing" }
$cmd = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch && git show " + $pin + ":deploy/scripts/v163_readonly_event_first_preview.py | timeout 180s nice -n 19 .venv/bin/python - --historical-replay-days 7"
& ssh -i $key $remote $cmd
Write-Host "V163 replay exit code: $LASTEXITCODE"
```

A remote exit code of 124 means timeout; other failures require the new stderr output. When the replay completes, evaluate all 24 items against **recall ±15 seconds / ±60 seconds / ±10 minutes**, precision, missed and extra forecast events. Historical four-hour replay accuracy does not equal the desired every-five-minute live forecast coverage.

## V164 challenger after first real replay

The user's V163 7-day/4-hour as-of event replay completed (exit 0). Key 10m results: Nessie 74/179 recall 41.34%, precision 74/188 39.36%; Japan Xanax 42/74 recall 56.76%, precision 42/73 57.53%; Jaguar 104/185 recall 56.22%, precision 104/208 50%; Crocus 6/24=25% recall and Banana Orchid 4/26=15.38%. ±15s and ±60s global figures were not included; only 22 rows were pasted.

New opt-in **all-history vs most-recent 8, 16, and 32 completed cycles** apples-to-apples historical tournament, same 4h issues, same clean restock truth, counts timing errors at 15s, 60s, 10m plus false predicted events, no writes, existing V163 beta unchanged. Pinned source `f47656bdd9290196b010b5ee1e5f6ed3c7381cbc`, V85 passing [38491004953](https://github.com/fungjkTorn/torn-fren/actions/runs/38491004953). Not yet benchmarked against VM data; the winner must not be assumed. To run the research tournament, use existing VM SSH and `git show f47656bdd9290196b010b5ee1e5f6ed3c7381cbc:deploy/scripts/v163_readonly_event_first_preview.py | timeout 300s nice -n 19 .venv/bin/python - --historical-replay-days 7 --compare-recent` from `/home/ubuntu/torn-fren-v38-probe`; pipeline sends source only, VM V163 beta is not modified. We still need five-minute dynamically issued event forecasts and holdout-prospective restock/arrival scoring.
