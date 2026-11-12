# V159 — Phase-episode robustness audit, NOT another model to deploy

## Observed V158 read-only VM report

The user reported a successful (SSH 0), database-write-free 24-item replay of 600 first-issued item-hour cohorts. Independent V151 generated 507 proposals, 326/425 mature stock>=30 arrival **poll-state proxy** hits (76.7%); always-paired V151 generated 507 proposals and 344/430 mature hits (80.0%, **different** denominator), with directly matched 18 paired-only HIT vs 4 independent-only HIT among 421 mature comparisons (**net +14**).

V158 flight-horizon router finally selected paired on **74/507** proposals and independent on 433, and scored 329/426 mature hits (77.2%). Among **424 directly matched** V158-vs-independent issue observations, V158 had 4 exclusive wins vs 1 exclusive loss (**net +3**). This is a smaller realized gain than the full always-paired challenger. Do **not** conclude that always paired dominates, because pending/unknown samples, correlated issues, historical backfill provenance, actual stock depletion after provider poll, and varying wait times all matter.

V158's realized per-item paired selections: Monkey 8 (net +2); Wolverine 3 (+1); Nessie 4 (+1); Chamois 8 (net -1); UAE Camel 4 (net 0); Chi Panda 2 (net 0); Lion 4 (0); Haw Orchid 16 (0); Uni Xanax 21 (0); Red Fox 4 (0). Notably Jaguar raw paired net +2 but V158 picked paired on zero issues, and other raw paired wins may likewise be concentrated in a few unique phases. Japan Xanax retained 0 proposals (about 12 min HIGH, 120 min LOW), and all reported conservative V151 issue forecasts lacked the .60 peak stock-survival threshold. No reason to force a recommendation.

## Why count source phases, not just hours

A new item-hour issue, a new forecast, and an independently observed depletion/restock episode are different things. Even an apparently significant increase such as 18 vs 4 *hourly* matched exclusive successes may come from repeated measurements within a small number of underlying episodes. Without measuring that concentration, choosing a champion on hourly counts overstates evidence.

## Implementation in the research branch

- Added `research/v159_issue_phase_episode_audit.py`, a **pure read-only post-replay validation pass**. Groups each mature, mutually scorable pair of forecast outcomes by `(item_key, phase_at_issue, observed_phase_onset_at_issue)`. Phase and onset come from the frozen issue-time V145 observed state; if unknown or not time-consistent, the row is unscorable for episode claims, not a loss.
- For each item the audit returns number of distinct supported phase groups; groups with more paired HIT-only vs independent HIT-only issues, groups favoring independent, groups tied/mixed, and same comparison for V158 vs independent. It also counts paired-only successes V158 missed and independent-only successes V158 exposed itself to.
- `research/v146_v145_same_issue_replay.py` adds a no-future issue phase anchor and produces `issue_phase_episode_audit`. Routing itself is unchanged. Raw issue records remain private in memory, not written to the production collector/sidecar.
- `research/v149_v146_compact_report.py` reports episode groups and per-item phase clusters, replacing the older verbose V156 branch narrative while preserving all 24 rows and V151/V158 direct matched proxy totals.
- `tests/test_v159_issue_phase_episode_audit.py` checks that two hourly wins within the **same phase** count as one episode-level paired advantage; that unknown/missing phase or pending outcomes do not become losses; and that source-phase grouping is never claimed as independent future arrival restock proof. Existing V146/V149 reports and no-write tests still apply.

**This is stricter evidence grouping, not a new arrival forecast, trained selector, threshold change, or 24-item performance claim.** As-issued phase clusters are still not independently verified future-restock events or real flights, particularly if later backfills can alter historical snapshots. Stronger proof requires a genuinely prospective, timestamp-locked shadow with truthful provider provenance and event-group holdout.

## Next empirical gate

Run the source-pinned bounded read-only VM comparison **after CI passes**. Inspect item-by-item cluster win/loss concentration, V158 paired selection misses and harms, and grouping coverage. If most exclusive gains concentrate in a few phases, do not promote. If recurring independent phase episodes substantiate item-specific lift, launch a private **prospective** issued-shadow, not the live public website or production V75 model.

Keep original V2 graph and experimental multi-item dashboard, V75 specialists, V128 shadow and collector untouched. No Torn API actions or automated flight activity.
