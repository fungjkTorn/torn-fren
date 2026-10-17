# V159 second read-only replay: why every episode column was zero

## Observation

At **fixed cutoff `REPLAY_ASOF_EPOCH=1791896383`**, the user reran the V159 historical as-issued 24-item/576 cohort replay after the initial source phase-onset duplicate-key correction. The historical model comparisons were the same as prior: 486/576 independent V151 proposals, 319/413 scorable poll-state arrivals, and 409 mature **directly matched** independent-versus-fully-paired V151 comparisons with 17 paired-only hits and 4 independent-only hits. Nevertheless the compact console printed zero V159 phase clusters for every item.

This console output is **not evidence of zero independently observed phases**. The V159 event audit was placed correctly under the top-level `replay_result["issue_phase_episode_audit"]`, but `research/v149_v146_compact_report.py` mistakenly requested the audit from its derived `source` dictionary that only contained cohort/eligibility counters. `source.get("issue_phase_episode_audit")` always returned None; the reporter then silently substituted empty totals and item maps.

## Actual code fix

- Use `result.get("issue_phase_episode_audit")` (not `source.get(...)`).
- Validate method name, top-level totals, per-item sums, and an episode-to-mature-pair upper bound. Missing or mismatched evidence throws ValueError instead of displaying fake zero wins/losses.
- In a proper frozen issue-time V151 comparison with a mature paired outcome, V151 requires a currently known HIGH/LOW onset. A nonzero mature paired count alongside zero scorable as-issued phases is now a **hard audit failure**, not an acceptable console result.
- `tests/test_v149_v146_compact_report.py` now contains nonzero simulated phase groups whose expected win/loss counts must appear in both summary and per-item console rows. It also verifies missing top-level evidence raises an error and cannot be bypassed with similarly named nested summary keys. Other tests verify inconsistent phase denominators and nonzero paired outcomes with zero grouped evidence are rejected.

## Evidence and safeguards

The previous V159 replay is **invalid for episode-level conclusions**; it does not invalidate the separate historical same-issue V151/paired/V158 hit/miss counters. Grouping by as-issued stock phase is a stricter description of *correlated historical checks*, **not** independent future-stock events or confirmed travel purchases.

Re-run using the **same** `1791896383` cutoff to prevent the hourly cohort window from moving. Preserve original V2 graph, experimental multi-item dashboard, V75 specialists, production database, sidecar, services, and timers unchanged. Do not promote paired models by a per-hour score without distinct event-level and prospective validation.
