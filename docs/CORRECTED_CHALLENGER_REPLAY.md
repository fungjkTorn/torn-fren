# Corrected challenger replay

Research only. No live roster, service, timer, website or collector changes.
The ten live items keep their pinned configurations and defaults.

## Frozen shortlist and full-history overrides

Select the V174 development-screen winner for each of the remaining fifteen
items, then retain those with strictly greater than 75% known filtered-arrival
success. This is the specific metric discussed in the conversation, not an
assertion of independent-restock accuracy. Do not choose a different finalist
because its validation result looks better. Exactly-75% Camel/Nessie excluded.

| Item | Screen winner | Old filtered result | Corrected research configuration |
| --- | --- | --- | --- |
| Monkey Plushie | V20 traj3 | 85.9% | traj3, point-count lookback removed |
| Wolverine Plushie | V20 traj12 | 96.3% | traj12, no rolling restriction |
| Stingray Plushie | V20 traj5 | 100% | traj5, point-count lookback removed |
| Peony | V20 traj12 | 99.7% | traj12, no rolling restriction |
| African Violet | V20 traj11 | 99.8% | traj11, point-count lookback removed |
| Lion Plushie | V20 traj12@48h | 80.0% | traj12, 48-hour restriction removed |
| UK Xanax | V19 dyn8 | 94.3% | dyn8, no rolling restriction |

The user explicitly rejected a 48-hour training restriction for this replay.
Every challenger receives all available causal history. Native historical-point
lookbacks are also disabled using an explicit research-only override. Neither
the old percentages nor frozen-config identity claims transfer to these changed
variants. All results must identify this full-history override, not only the
base configuration name. The native algorithms, neighbor selection, weights,
and causal outcome-maturity rules otherwise remain unchanged.

## Correct logic before replay

research.corrected_challengers calls the existing shared first-release scheduler.
It does not use the old tournament's event_departures, engine_issue_plans,
departure-within-next-five-minutes filter, reconfirmation gate or promotion rule.

Current stock is considered first if its predicted survival window is reachable.
Otherwise enumerate predicted restocks and select the first reachable buying
window. Only then let the selected native V19/V20 engine score departure points
inside that one window. Unsupported, missing, zero-score and out-of-window timing
results cannot skip that event. This is the live architecture: shared empirical
event calendar plus model-specific timing refinement. It is not the old native
tournament planner with a renamed output. No restock-time horizon is added.

Tests exercise each actual native engine and check that it receives the full
training-point list, a config with no point lookback, and zero arrival grace.
Sequence tests cover current stock, unreachable first events, future advice
more than five minutes away, and invalid/missing timing support. Existing live
ten regressions must pass before any actual-data replay.

## Data and execution

The available V174 upload contains completed JSON checkpoints, not the current
collector database. Public chart history lacks the complete heartbeat, gap and
country-clock evidence needed to certify arrival stock. Do not turn it into
synthetic successful poll evidence.

deploy/Export_Corrected_Challenger_History.ps1 fetches this branch, streams the
standalone exporter into the VM over the user's existing SSH key, and downloads
the result to the Windows Desktop. It does not check out or deploy any branch
on the VM, install services, run models there or modify the collector.
The exporter selects only the seven item histories, poll evidence, gap intervals
and country clocks from one read-only consistent transaction. Its 120-day safety
limit includes all currently available project history; the evaluation period
is only the final seven days. A new private filename is required on every export.
No API keys, player data or unrelated tables are copied.

After obtaining the sealed snapshot, run a seven-item one-issue pilot first:

```sh
python -m research.corrected_challenger_replay --source /path/history.sqlite --output /path/pilot --pilot
```

Inspect all statuses, source freshness, timeouts and per-item timing. Estimates
are provisional and exclude mirror-copy and orchestration costs. Only then run:

```sh
python -m research.corrected_challenger_replay --source /path/history.sqlite --output /path/week --max-seconds 1800
```

The week contains 2,017 issue clocks per item at the default 300s cadence.
This is issuance sampling only; all future departures remain eligible.
There is no five-minute departure filter or agreement requirement. Stop after
the resource budget and resume the identical command; completed issues are not
rerun. Each isolated native worker has a 30-second timeout. Do not promise a
short runtime merely because only one configuration is used per item.

Native workers receive an issue-truncated incremental SQLite mirror, never the
truth database. Future gap closures are censored until observed. The truth
database is read-only and used only for outcome scoring and retrospective
ordinal target matching. At least seven days of pre-test evidence are required
in addition to the test week; insufficient history fails explicitly.

## Reporting

Score stock >30 at the exact calculated arrival, no grace. Exactly 30 fails.
Bracket ambiguity, sparse polls, gaps, provider switches, and unverified country
freshness at landing are unknown. Immature arrivals remain pending. A source
country explicitly stale at issue cannot produce a recommendation.

Freeze the first issued forecast per observed ordinal opportunity, using the
same TargetIndex as the live evidence module; do not match nearest predicted
timestamps or replace a poor first forecast with a favorable revision. Report
all distinct-opportunity counts and raw issue counts separately. Report
unmatched forecasts and openings without matched forecasts; the latter are not
automatically physically reachable misses. Withhold the headline percentage
when unmatched failures/unknowns/errors could bias it. Continuous-stock periods
without a known opening remain explicitly unmatched, especially UK Xanax.

Signed forecast-opening error and arrival-minus-opening are diagnostic minutes.
Arriving after opening while >30 stock is still success. Boundary timestamps
are observed poll times with interval uncertainty, not exact game restock times.
There is no deployment, challenger/incumbent comparison or live certification
in this single-model replay. A separate comparison would need explicit pinned
controls and matching sample definitions; this request runs only one corrected
candidate for each shortlisted item.

## Verified execution acceleration

research.cached_challenger_replay retains the identical issue clocks, native
models, full-history override, causal mirror, scoring and opportunity grouping.
It runs one isolated process per item, reuses imports, caches collector queries
over already closed historical intervals, and computes integer leave-one-out
means from an exact sum instead of repeatedly summing the same peak list.
It does not cache predictions, reduce history, skip clocks or omit failures.
Changing source identity, gap metadata or the first heartbeat clears the query
caches. Each native call keeps its 30-second timeout. Process-local patches are
restored when the context exits and never installed on the VM.

Before using it on the uploaded 20261029T032420Z snapshot, complete forecast
payloads were compared to the original worker at three causal issue clocks
for every item (21/21 identical). Unit tests additionally check exact numeric
types/values, metadata invalidation and restoration. Per-item acceleration
sidecars identify the helper hashes alongside the original replay manifest.

The initial switch between runners briefly produced duplicate identical issue
rows. Original files and migration audits were retained. Duplicates were removed
only after comparing every field except execution duration; the first forecast
was preserved. Final reporting must independently require all 2,017 expected
issue clocks exactly once per item and reject nonidentical duplicates.

## Final opportunity audit

The live TargetIndex is intentionally conservative about all provider changes.
The completed replay audit found that this can exclude earlier failed forecasts
even when both providers agree on the same >30 availability state. The primary
research report therefore additionally uses forecast_opportunity_audit's
ProviderContinuousTargetIndex, consistent with the phase forecaster: benign
same-state switches preserve identity; conflicting threshold changes and gaps
still reject it. Every saved landing outcome remains unchanged, and the earliest
issued forecast is selected after sorting by its clock. The strict original
counts are retained as a reference view. Neither this research matcher nor
new models have been deployed into the live evidence recorder.

Tests cover future and current target continuity, conflicting switches, gaps,
mixed-provider arrival grades staying unknown, and an earlier failure winning
over a later successful revision even when input rows arrive out of order.

## V5 rescore of the saved week

The original first-forecast matched-opportunity evaluation remains reproducible above. The completed archive has also been evaluated with the corrected live `RECOMMENDED_DEPARTURE_FREEZE_V5` tracking implementation, without rerunning any model. See [the V5 rescore](CHALLENGER_V5_RESCORE_20261029.md) and `research/rescore_saved_challengers.py`. It retains the sampled issue clocks and validity deadlines, including no-advice withdrawals, and invents no one-minute refreshes. The evaluation unit is the recommendation that freezes at departure, so the old conditional matched-window percentages do not directly measure improvement against the new rates.
