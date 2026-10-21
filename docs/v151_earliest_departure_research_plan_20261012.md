# V151 continuation — earliest viable flight departure, item-specific beta

**Research only, 2026-10-12. No production deployment or VM DB mutations.**

## User-accepted product rule

Use each reliably OBSERVED start/end of an item-stock period as valid history even if the collector changes providers mid-period without contradicting the same >=30 status (V145). Show the first REACHABLE next >=30 stocked opportunity and earliest reasonable time to fly, not the highest-score future opportunity. Outbound flight time varies by country (17 min–197 min); frequent 30-minute plushie replenishments must not lead to unexplained multi-hour waits. Replan every five minutes, eight-hour departure horizon, arrival >=30 criterion with +10s grace. The original V2 graph and experimental 24-item dashboard BOTH must survive unchanged until authorized deployment.

## Grounded evidence, not guesses

Completed real VM V146 replay: 552 first-issued item-hour records; V145 recovers 217 historically excluded eligibility starts. V148 proposed 463 times but on 346 matched mature leave-now pairs, it had **48 exclusive wins vs 54 exclusive losses**, net -6. V148's 269/370 known successful proxy arrivals are conditional and not evidence of better departure choice than now. V145 was capped to 96 MC computations (four/item), so 71/85 hits cannot be compared naively to all-start V148. Japan Xanax had 13 recovered eligible hours but 0 V148 conservative windows; the separate Japan-specialist model still requires forward validation. See docs/v146_complete_24_item_results_20261013.md.

## V151 new model and actual code changes

- `research/v151_stable_earliest_departure.py`: deterministic whole-stock-cycle HIGH/LOW scenario simulations from V145 completed source episodes, conditioning on known current phase age and restock/depletion duration history. Uses country outbound flight seconds + 10s grace, eight-hour 5min departure grid, 96 default scenarios and bounded transitions. Predicts both the first next replenishment time distribution and stock >=30 at candidate arrival. Emits a provisional earliest departure when supported by its scenario gate; does NOT claim its raw scenario fraction is calibrated probability.
- The pseudo-random seed depends on actual completed item phase history instead of issue timestamp, preventing artificial five-minute forecast changes due solely to reseeding. Real age progression and genuinely new stock history may still change the projection.
- Avoids V148's false 'no reachable window' when separate conservative restock-start and stocked-lifetime quantiles do not overlap, while preserving explicit uncertainty / low-sample flags.
- If the NOW arrival scenario clears the (as-yet-uncalibrated) threshold, it ALWAYS wins; do not postpone a viable immediate flight just to get two contiguous 5min bins. A future flight requires two supported adjacent bins; a short-lived single-bin future opportunity remains visible as non-actionable research evidence.
- An observed cadence below an offered long wait triggers `LONG_WAIT_NEEDS_NEARER_CYCLE_AUDIT`, not an unqualified instruction to wait.
- `research/v146_v145_same_issue_replay.py` now also evaluates V151 against exact same original first-issued item-hour checkpoints, scores matured poll-state arrivals versus leaving NOW, counts pending and unknown results, tracks median wait and long-wait flags per item.
- `research/v149_v146_compact_report.py` prints the new V151 metrics next to V128, V145 and V148 in under 45 lines including all 24 roster items. `tests/test_v151_stable_earliest_departure.py` and expanded replay/report regressions guard timing and no-lookahead behavior. V151 research model IS NOT deployed.

## Next exact action if/when CI green

One safe research-only VM operator command; prints compact report, executes bounded read-only V128/V145/V148/V151 cohort audit against approved historical collector and V128 sidecar. Reuses the pinned private stage. No model worker/timer or public website modified.

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"
$report = Join-Path $HOME 'Desktop\torn-fren-v151-matched-24-item.txt'
& ssh -i $key $remote 'set -o pipefail; cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin research/v38-full-roster-live-prep-20261009 2>/dev/null && git show c35415d4672c52612ea930a15e16f75f6af150a0:deploy/scripts/v146_replay_v145_from_existing_stage.sh | bash' | Tee-Object -FilePath $report
Write-Host "SSH exit code: $LASTEXITCODE"
```

We require final `===== V146 REPLAY DONE; NO COLLECTOR, SIDECAR OR WEBSITE CHANGES =====` and SSH exit code 0. On failed run do NOT interpret incomplete output. The source file is saved separately so console truncation cannot destroy audit evidence.

## Decision gates and future milestones

1. **Same-issue predictive lift:** V151 must beat leave-now on matched mature >=30 arrival proxies, controlling for source ambiguity, sample selection, and wait; compare exactly which items win, lose or abstain. Raw proposal coverage or best-score percentage is insufficient.
2. **Restock/depletion anchoring:** measure first upcoming observed restock timing error, inability to catch stock before depletion, and next-cycle skipping; this remains further research beyond the simple current V151 score.
3. **Forward as-issued shadow:** after bounded historical improvement, run private read-only comparative research shadow on original collector for more independent cycles. Reconfirm a departure near takeoff and measure <=30s / 1m / 5m timing plus >=30-at-landing. Do not fabricate player purchases from poll snapshots.
4. **Preserve incumbents and both pages:** do not alter production/default V2 graph or 24-item experimental dashboard without source-pinned regression, rollback, and explicit authorization; best specialist should remain selected per item rather than a fleet-wide swap.

Neither V151 history nor V146 score is a certified game flight instruction. All percentages are conditional historical collector proxies.
