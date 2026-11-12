# V153: next-restock accuracy and regime-shift diagnostic

## What the read-only V152 VM run actually showed

- 600 issued item-hour cohorts, all 24 items, `SSH exit code 0`, no production writes.
- V151 proposed 509/600 = 84.8%; among 411 mature known poll proxies, 320 stocked-at-arrival hits = 77.9%, conditional on proposed and observable arrivals.
- On same-issued, mature V151-vs-V148: 387 paired, 56 V151-only hits vs 36 V148-only hits (**net +20**).
- V151-vs-leave-now: 396 paired, 28 V151-only vs 12 leave-now-only (**net +16**). Among the V151 proposals, 400 were immediate and 109 delayed. On 73 mature delayed-only pairs, the same 28 exclusive wins and 12 losses (**+16**). Those are not independent player trips.
- **First-next-restock timing remains poor**: 333 matched fully observed complete replenishment periods, V151 first-onset mean absolute error **23.5min**. <=1min 61/333 = 18.3%, <=5min 155/333 = 46.5%, <=15min 233/333 = 70.0%. Examples: Peony 49.8min, Edelweiss 100.0min, Banana Orchid 103.5min versus Monkey 3.6min, Japan Xanax 4.4min. These are per-issue average errors, not independent cycles.
- **Japan Xanax**: 15 recovered previously rejected historical issue opportunities, no V151/V148 candidate; a roughly 4.4-minute restock-onset MAE on scorable occasions does not imply stock survives a flight or that its arrival confidence threshold is satisfied.

## Objective

Improve accurate first reachable >=30 stock arrival/departure timing without speculative long waits. A single fully observed start/end counts as legitimate historical evidence even when a data source switches harmlessly in the middle. Protect both website views: original V2 stock graph and experimental 24-item dashboard. Avoid altering deployed V75 experts or the V128 collector/sidecar.

## New V153 research-only code

- `research/v145_provider_continuous_phases.py` now also returns `observed_bounded_depleted_windows` with DIRECT observed endpoints, in parallel to its prior stocked windows. No new permissive transitions.
- `research/v153_recent_completed_restock_baseline.py` predeclares recent 3, 5, 10 and complete-history duration variants, conditions on known current HIGH or LOW elapsed age, rejects missing source history and known ambiguous stock-state onsets, outputs *only research next-restock forecasts*. No flight actions.
- `research/v146_v145_same_issue_replay.py` scores each predeclared V153 onset forecast against the **same held-out complete next-restock event** as V151, counting pairwise wins/losses/ties and MAE. Absent, unbounded, gapped or conflicting first events are explicitly unscorable; model input never receives post-issue changes.
- `research/v149_v146_compact_report.py` includes V153 matched totals and per-item recency5 MAE next to V151 without hiding the 24-item roster, plus Japan Xanax no-departure diagnostics.
- Regression suites cover changing recent depletion durations, source churn with no threshold change, insufficient completed windows, future-data rejection and event-locked V151-vs-V153 replay. V153 is NOT installed in production; no real VM result yet.

## Next decision

Run ONLY the pinned read-only research audit AFTER CI passes. Compare V153 recent_3/recent_5/recent_10 against V151 using the same bounded first-next-restock event. Look for both lower error and adequate coverage across **independent** restock episodes, not just the minimum mean selected after looking. If one history variant improves selected items without sacrificing robustness, test prospective as-issued forecasts, then consider opt-in item-specific beta promotion after source/website preservation checks. V151 remains the leading research challenger for departure results, not yet the live winner.
