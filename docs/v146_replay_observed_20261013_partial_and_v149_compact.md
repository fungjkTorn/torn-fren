# Real V146 as-of replay: preliminary observations, compact reporting

Source: uploaded user V146 terminal excerpt with 1,029 lines. This paste **starts inside Argentine Ceibo Flower** and completely omits Argentine Monkey Plushie. Exactly **22 complete per-item records** are available, along with the complete aggregate eligibility summary. The full Tee-Object log on the user's Desktop may be uploaded directly; do not request another full replay just to read missing lines.

Execution completed with SSH exit status 0, explicit no collector/sidecar/website changes. Results are historical poll-state proxies, not verified player flights, country-provider freshness, independently observed cycles, or prospective frozen provenance.

## Full overall eligibility summary recovered

- 217 issue-hour entries newly eligible for V145 phase model after preserving benign provider switches.
- 56 records already eligible under both methods.
- 389 V145-eligible issue-hours not Monte-Carlo scored because of the **96-evaluation resource budget**. This category includes both newly eligible and previously eligible entries; it is NOT 389 further recoveries.
- 40 newly eligible entries actually scored.
- 67 still sparse history or unknown phase onset.
- 96 V145 model runs total, 4 per item by design.

## Aligned outcomes for the 22 complete items only

- 506 issued UTC item-hours, original V128 proposals 203, V145 budget-capped proposals 84, V148 explicit-restock proposals 424.
- V145: 65 proxy successes, 13 proxy misses, among 78 known outcomes. 75 same-item/issue pairs vs leave-now; V145-only wins 4, leave-now-only wins 3; net +1. Far too small and budget-selected to claim performance lift.
- V148: 246 proxy successes, 91 proxy misses, 48 pending, 39 unknown, 424 total proposals. Mature proxy 246/337 = 73.0%, conditional on scorable proposed flights; NOT overall stock-at-landing certainty.
- V148: 313 aligned matured leave-now comparisons, 45 V148-only successes, 48 leave-now-only successes; net **-3**. No demonstrated improvement over leaving now.
- These cohorts can share the same actual stock cycle, and the local collector may contain post-issue backfills.

Key examples: Japan Xanax old 0, 13 V145 newly eligible but STILL 0 V145 recommended departures and 0 V148 feasible stocked windows (22/23 no conservative reachable window). Peony old 0, 18 recovered, 4 budget-limited V145 proposed, 23 V148 candidates; explicit net -4 vs leave-now. Edelweiss old 0, 10 recovered, 4 V145 proposed, 19 V148 candidates; explicit net -2. UK Xanax old 0, 13 recovered, 4 V145 proposed, 23 V148 candidates; explicit net +3 but V148 median leave wait 9,635s, must confirm reasonable relative to actual cadence/flight uncertainty.

## Product decisions

1. Keep original V2 graph and existing deployed 24-item experimental page, 21 incumbent specialists plus 3 previews. Do not promote V145/V148 based on this.
2. V145 corrects a documented artificial eligibility loss, but more proposals alone does not imply better outcome. Preserve its clean observed start/end and uncertain gap/source boundary handling.
3. V148 needs calibrated restock/depletion anchoring, tested missed earlier cycles, and departure timing improvement against leave-now, particularly Japan Xanax. Results are not yet acceptable.
4. Do not interpret model abstentions as missing stock history: V144 had 355 clean observed stock-crossing events in 24h, with provider churn causing many discarded phase starts.
5. V149 implements a concise under-45-line 24-item result format. VM operator now stages it and prints compact results instead of ~1,000 lines. The existing original full log can be uploaded rather than rerunning.
