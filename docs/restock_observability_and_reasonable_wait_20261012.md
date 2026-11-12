# Reasonable waits and observed restock coverage — 12 October 2026

## Product rule

The beta should find the earliest *reasonable, reachable* opportunity with >=30 expected units at landing, not merely the highest simulation score or the next distant restock. For stock that typically refreshes every ~30 minutes, waiting multiple hours needs a credible explanation (missed cycles, flight-time constraints, insufficient threshold-30 lifetime, source uncertainty). Do not impose a hard max wait that hides a genuinely earliest reachable opportunity.

## New isolated research improvements

- research/v2_beta_departure_bridge.py accepts optional observed_median_restock_cadence_seconds and flags modeled cycle gaps > max(15 minutes, twice the observed cadence). It labels a multi-cycle departure wait LONG_WAIT_VERIFY_NEARER_RESTOCKS. It still shows the earliest feasible *modeled* cycle and never asserts actual >=30-at-arrival success. The actual observed cadence must come from completed within-source transitions; do not guess it from a product name.
- research/v144_restock_coverage_diagnostic.py counts last 24h observed clean >=30 crossing restocks, clean 0->positive transitions, positive quantity jumps while still >=30, source switches, known collector gaps and per-item V128 source/decision-status reasons. It is a standard-library-only, bounded, read-only diagnostic with no model or service modifications.
- tests/test_v2_beta_departure_bridge.py now tests unreasonable multi-cycle watches and reasonable short waits.
- tests/test_v144_restock_coverage_diagnostic.py proves six observed actual threshold crossings can coexist with zero V128 recommendations and therefore zero forward-scored V128 arrivals. It also checks provider ambiguity and above-threshold replenishments.

## No scorable V128 arrivals does not mean zero restocks

V128's phase extractor deliberately resets its current phase onset after source switches or collection gaps. A lack of transition *after* that reset can cause CURRENT_PHASE_ONSET_UNKNOWN despite multiple earlier shop replenishments. Other causes include inadequate completed phases, no surviving analogous durations or the score floor. The existing historical V139 audit reports only scored as-issued flights, NOT the number of actual recent restocks per item. The fresh last24h diagnostic can distinguish these issues.

## Newly requested at-home command (PowerShell; keep existing $key and $remote)

```powershell
$coverageLog = Join-Path $HOME 'Desktop\torn-fren-v144-stock-coverage.txt'
& ssh -i $key $remote 'cd /home/ubuntu/torn-fren-v38-probe && git fetch -q origin research/v38-full-roster-live-prep-20261009 2>/dev/null && git show ecc02fa14f2f3b7b53c7fb45e61d3b20ab8bd8ae:research/v144_restock_coverage_diagnostic.py | python3 -' | Tee-Object -FilePath $coverageLog
Write-Host "SSH exit code: $LASTEXITCODE"
```

Expected output: JSON with status READ_ONLY_FOREIGN_RESTOCK_OBSERVABILITY and exact_item_count=24; includes last day's source_status counts and observed restock changes. No raw stock history or secrets are emitted.

## Website source status

User SCP succeeded, copying app.py, experimental.html, index.html under Windows Desktop/torn-fren-deployed-review. These files are still local to their PC, not attached to the conversation. The user should review/redact any hardcoded credentials and then upload these three files (or their ZIP) for reconciliation of the true deployed V41 and V2 frontend sources. Do not replace live app.py using research web/app.py.

## Next steps

1. Inspect V144 counts for Japan Xanax, Peony, Edelweiss, UK Xanax, and all remaining items. If observed replenishments exist but V128 repeatedly abstained, repair the specific cause on a separate tested research path; do not lower certainty blindly.
2. Use true historical restock cadence to evaluate departure wait reasonableness and model cycle coverage. Model-derived unverified stocked windows must remain clearly provisional.
3. Once the deployed source copies are attached, reconcile and build the default-off integration into the EXISTING /experimental and / graph. Test both first; production changes need explicit user approval.
