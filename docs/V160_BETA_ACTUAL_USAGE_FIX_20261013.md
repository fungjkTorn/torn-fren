# Oct 13: V160 private beta is running, but first user screenshot showed only 3/24 future proposals

## What user observed
The user opened the actual localhost-only private beta in the browser and supplied two screenshots. Example: displayed **3/24 items with fresh proposed departures**, 1 model agreement, most items labeled `No departure · provisional scenario supported departure` even when observed last quantities were well above 30. Three visible upcoming WATCHs were:
- Switzerland Chamois Plushie: independent proposed wait ~2m30s; paired no visible future
- Mexico Jaguar Plushie: independent and paired proposed ~12m30s, agreeing
- Argentina Monkey Plushie: paired proposed ~27m30s; independent no visible future

The exact local times/quantities in screenshots were only momentary and must NEVER be treated as current forecasts after the issue has passed. A high *last observed* stock does not imply stock ≥30 at landing (flight may be 17m–3h+). `3/24` was **a misleading viewer coverage metric**, not underlying V160's actual as-issued model coverage.

## Root cause
Original private beta `snapshot()` hid any model `departure_epoch < now-30` by setting `departure = None`. Research V151 often recommends `departure_epoch = issued_epoch`, i.e. leave immediately at the snapshot time. After just 31 seconds, these authentic as-issued NOW proposals disappeared from the browser and were mislabeled `No departure` while the preserved model status remained `PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE`. It collapsed three distinct outcomes: true model abstention, just-issued-now-but-expired forecast, and future WATCH. A no-model case is NOT the same as a recent forecast requiring reconfirmation.

## Research-branch fix, designed for immediate usefulness
`deploy/scripts/v160_private_beta_board.py` now retains immutable, **as-issued** departure and arrival plus scenario fraction, and separately computes strict UI state:
- `FUTURE_WATCH` or `DUE_NOW`: actual forthcoming time from a fresh recorded issue
- `RECENT_ISSUED_NOW_RECHECK`: V151 supported immediate flight on the latest issue, but it was issued >30s ago and is NOT a newly calculated departure
- `DEPARTURE_PASSED`: original timestamp passed and is outside the reasonable current issue recheck window
- `NO_MODEL_CANDIDATE`: genuine abstention/no eligible departure
- `STALE_RESEARCH_ISSUE`: always hide the active departure recommendation when ledger capture/source age is stale

An entirely redesigned decision-first board presents **Upcoming departure opportunities**, **Recently indicated leave now (recheck)**, a separate true-no-support count and all-item evidence beneath, plus latest source observation age and flight durations. It is impossible to convert an expired as-issued signal into a fake valid-now departure. The page stays private loopback; V160 recorder is untouched.

Regression tests now reproduce the screenshot's precise failed-NOW-after-130s case, assert the timestamp remains visible as evidence but never reclassified as executable, verify it expires after 300s, inspect the real 22+2 roster, parse the new JavaScript with Node, verify live HTTP/stale/unknown integrity, and verify dedicated viewer-only upgrade rollback.

**All four CI workflows passed at source revision `b98d1e92166dcfc1e0c0fd0d2043e16c18e337e5`** including [V85 isolated 24-item beta tests](https://github.com/fungjkTorn/torn-fren/actions/runs/38440212808). Separate guarded, rollback-safe `deploy/scripts/v160_beta_safe_upgrade.sh` pinned to tested source; operator Git commit `c6afa5c12e87c785f3a1a7727a03dfd5978e9f58`. It upgrades ONLY the isolated beta viewer and restarts ONLY `torn-fren-v160-beta-board.service` after verifying the actual 24-row ledger and checking the new HTML and API over localhost. Restores the old viewer if smoke/HTTP fails. No collector or production website writes, V160 recorder remains independently active.

## User can update existing private beta using ONE complete PowerShell block

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$branch = "research/v38-full-roster-live-prep-20261009"
$pin = "c6afa5c12e87c785f3a1a7727a03dfd5978e9f58"
$script = "deploy/scripts/v160_beta_safe_upgrade.sh"

if (-not (Test-Path -LiteralPath $key)) { throw "SSH key missing" }
$cmd = "cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin $branch && git show " + $pin + ":" + $script + " | bash -s"
& ssh -i $key $remote $cmd
if ($LASTEXITCODE -ne 0) { throw "Private beta upgrade failed: $LASTEXITCODE" }
Write-Host "Refresh your existing http://127.0.0.1:8765/ tab."
```

Keep the existing SSH tunnel open. If closed, reconnect separately using the previously documented one-line port forward. This repo commit DOES NOT remotely upgrade the user VM; output confirming upgrade is still required.

## Product gap that remains
The CURRENT recorded V160 forecasts only freeze a single first reachable departure per model on a five-minute issue cadence. That does NOT validate departure at arbitrary points BETWEEN issues, and already-issued NOW opportunities still need a fresh causal check. The reader must not fake a mid-interval stock probability. To get true useful departure guidance, next build a resource-bounded opt-in **on-demand single-item recompute** using pinned model code on the private loopback viewer, or enrich future V160 issues with as-issued support windows (careful tested versioning; no rewrite of immutable historical records), and compare against the existing V2 specialist view with real time-to-leave geometry. Then safely integrate into existing deployed V2 and /experimental only after deployed-source parity and rollback checks. Retrospective ≠ forward verified arrival success.
