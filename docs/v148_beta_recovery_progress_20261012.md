# V145–V148 objective-centered beta continuation — 12 October 2026

## What the user actually wants

Finish the exact 24-item beta while preserving BOTH deployed experiences: the original V2 stock graph and the experimental multi-item dashboard. Show the **earliest sensible departure** to reach a realistically stocked opportunity (>=30 at arrival), skipping next restock only when unreachable. For frequent ~30-minute plushie cycles, never silently recommend waiting hours without checking intermediate cycles or explaining why they cannot be reached. A complete stock start/end is valid historical evidence even when a provider changed benignly in the middle.

## Grounded VM evidence

Uploaded V144 24-hour audit found **355 clean observed >=30 restock threshold crossings**, **3,040 abstentions for unknown current phase onset**, **1,516 provider switches** across 5,856 V128 item-ticks; historic source changes can reset the existing V128 phase start even when a full observed cycle is otherwise available. Japan Xanax 11 observed restocks but zero V128 departures; Peony 5/0, Edelweiss 4/0, UK Xanax 4/0. These are change-only collector observations, NOT exact certified Torn game shop events. A zero forward-scored proposal is NOT zero restocks.

Existing V139 historical proxy shows: V75 matched 86.7% vs 76.3% leave-now (814 cases), V128 72.5% vs 71.3% (160 cases), original V2 65.6% vs 61.5% (2,013 cases). DIFFERENT issue cohorts, not a true direct model ranking. Original V2 restock error 130.05 minutes MAE with 36.04% predicted-window hit rate. Preserve incumbents. No model promotion before same-issue and independent-cycle evidence.

## New research-only code

- **V145** provider_continuous_phases(): retains observed high/low phase onset and bounded historical durations across benign same-threshold provider switches; rejects cross-provider threshold contradictions, collection gaps, and unobserved event boundaries. observed_cycle_evidence_tier() recognizes even one bounded period as evidence without overstating confidence.
- **V146** v146_v145_same_issue_replay.py: read-only same-item + first-UTC-hour issue replay, using actual V128 saved candidate issues. Reconstructs inputs as-of each issue, verifies source evidence fields against saved issued payload, and compares V128 original, V145 MC with recovered phases, and V148 explicit-restock candidate. V88 poll-bracket >=30 arrival proxy is scored separately for new, old, V148, and leave-now; unresolved/pending remain distinct. Includes comparison and wait-time medians per item, a balanced per-item MC budget and warnings on long waits. **As-of historical collector input may have been backfilled after original issue**, so still not proof of fully independent future accuracy.
- **V147** v147_deployed_24_view_preview_patch.py: SHA256-pinned OFFLINE source preview using uploaded actual deployed app.py/experimental.html/index.html; experimental dashboard candidate adds research-only leave-in countdown and fails closed for expired/passed recommendation, while the original V2 index and actual FastAPI server source are BYTE-IDENTICAL. No script runs on live VM. Production routing and model workers stay untouched.
- **V148** v148_observed_earliest_stock_cycle.py: separate next-restock timing model based on *completed observed V145 phases*. Generates transparent P1..P16 stocked interval forecasts, including an active-stock interval when applicable; uses observed stocked duration and depletion-to-restock duration quartile/median, PI+pilot flight time, depletion cushion/grace and 8-hour departure horizon. Searches the first actually reachable forecasted window, so a 106-minute flight can target a later ~30-minute cycle without an arbitrary 3-4-cycle cap. Any source/quantity/probability not certified remains provisional and requires 5-minute replanning.

## Safe targeted VM follow-up: one read-only V146 operator (not yet executed)

User's live VM has /home/ubuntu/torn-fren-v38-probe research virtual environment and the pinned private stage from the successful V139 audit. The operator `deploy/scripts/v146_replay_v145_from_existing_stage.sh` runs as ubuntu, verifies read-only collector and sidecar, stages only three new research modules from pinned commit, runs with low CPU priority, and times out within 240 seconds. It has a 96-model-evaluation budget distributed across items. No production/site/source DB changes.

Recommended in existing PowerShell with $key and $remote:

```powershell
$report = Join-Path $HOME 'Desktop\torn-fren-v146-recovery-comparison.txt'
& ssh -i $key $remote 'cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin research/v38-full-roster-live-prep-20261009 2>/dev/null && git show 2ab84b04942caf44373e25d25cb3dfc71b377fa5:deploy/scripts/v146_replay_v145_from_existing_stage.sh | bash' | Tee-Object -FilePath $report
Write-Host "SSH exit code: $LASTEXITCODE"
```

Output must end with `===== V146 REPLAY DONE; NO COLLECTOR, SIDECAR OR WEBSITE CHANGES =====` and SSH exit code 0. If it fails, retain the log and stop. This is for evidence, NOT promoting or deploying anything.

## Next research decisions after the report

1. Count V145 recovered actual bounded phases and eligibility per item, distinguish recovered *inference eligibility* from newly supported forecasts and from actual >=30 observed arrivals.
2. Compare same-issue V128, V145 MC, V148 explicit next-stock, and leave-now on matching mature observed proxies; keep pending and unknown in denominators, report each model's abstention/coverage and wait times.
3. Focus on Japan Xanax, Peony, Edelweiss and UK Xanax to confirm preserved observed cycles resolve the 0-proposal coverage, or reveal additional confidence/window problems.
4. Improve V148 restock-time MAE against subsequently observed clean replenishments and stock lifetime without lookahead. Test cycle skipping on 30–50 minute intervals and 17–197 minute flights. Do not mislabel synthesized scenario score as calibrated success.
5. Only then prepare reversible integration into EXISTING deployed experimental and V2, preserving the original source, routes and graph. Separate preview is not a live release, and production deployment requires explicit approval.
