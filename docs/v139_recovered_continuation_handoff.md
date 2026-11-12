# Recovered continuation handoff — V132 through V139

Date: 2026-10-12

This document corrects the user-facing handoff that stopped at V131/V134.
Repository history proves the prior conversation continued further overnight.

## Recovered pre-existing work

The research branch already contained and tested:

- V132 `research/v132_departure_timing_quality_audit.py`
  - audits V128 time-to-leave coverage, future WATCH versus near-term readiness,
    same-observed-state departure drift, and fresh near-departure reconfirmation.
- V133 `research/v133_private_departure_panel.py`
  - safe private 24-item display contract; stale snapshots expire; future watches
    are not labeled GO; original public graph remains untouched.
- V134 `research/v134_original_graph_v2_audit.py`
  - read-only original Prediction V2 persisted restock-window / target-cycle audit.
  - its historical `arrival_hit` means arrival fell between target restock and
    depletion; it is NOT direct proof of >=30 stock at landing.
- V135 `research/v135_morning_departure_brief.py`
  - one compact report combining V134 old graph evidence, V131 old V75 direct
    arrival proxy, V128/V129 arrival proxy, and V132 timing quality.
- V136 `deploy/scripts/v136_run_leave_quality_morning.sh`
  - one-time pinned VM operator for V135. It stages immutable research code and
    does not enable/start/stop services or write model/collector databases.

The recovered pinned CI-green baseline was commit
`0a48218c0fbd48e51d6c056c421de376b47bc521`.
The V136 operator was added immediately after that baseline and pins it.

## Original Prediction V2 time-to-leave behavior

The original public graph is not V128. Its logic lives in
`services/prediction_v2_live.py`, `web/app.py`, and
`web/static/index.html`.

### Restock forecast

When stock is zero, V2 anchors to a clean observed depletion and estimates the
next depletion-to-restock wait using the selected historical model. A restock
window comes from historical error coverage when available; otherwise it uses
a labeled fallback spread.

When stock is active, V2 projects the next cycle from the actual restock plus
an estimated stock lifetime plus the median zero-to-restock wait. Japan Xanax
has a special active-depletion estimate that blends historical time-of-day
sell rate with the observed live slope.

Future P2/P3/... cycles advance by median stock lifetime + median zero-wait,
with growing uncertainty. The system selects the earliest cycle whose
departure remains reachable.

### Arrival and departure window

V2 persists a recommended arrival based on:
- a learned arrival offset when calibration exists, or
- a midpoint-of-typical-stock-lifetime fallback.

The browser then builds the displayed lower arrival edge as:

`max(recommended_arrival, late/restock window end)`

so it does not intentionally arrive before the late side of the predicted
restock window.

The displayed upper arrival edge is approximately predicted depletion minus
a buffer of 10% of expected lifetime, bounded to 60–300 seconds. If that bound
collapses, the page falls back to the available restock/arrival point.

The departure window is the arrival window minus the country-specific PI +
pilot flight duration. The ticker labels the state TOO EARLY, GOOD TO LEAVE,
or LATE and client-side rolls to the next reachable cycle as the clock passes
the current target.

Therefore original V2 is a *restock-window + arrival-window planner*, whereas
V128 is an *earliest qualifying arrival-availability grid search*.

## V128 contract

V128 remains the enabled private 24-item experimental recorder:

- exact current 24-item roster;
- country-specific flight times;
- five-minute departure grid;
- at most eight hours ahead;
- 128 Monte Carlo scenarios;
- arrival threshold modeled around >=30 stock;
- raw scenario availability fraction >=0.60 for two consecutive grid points;
- choose the earliest qualifying departure;
- abstain when source/phase evidence is insufficient.

The 0.60 score is not a calibrated 60% success probability.
Future departures more than five minutes away are WATCHes requiring fresh
near-departure reconfirmation.

V130 phase-pinned Monte Carlo remains tested but not deployed.

## New recovery work after inspecting the branch

### V137 direct original-V2 stock-at-arrival benchmark

`research/v137_original_v2_stock_at_arrival_audit.py`

This closes the gap left by V134. For the FIRST archived V2 issue per item per
UTC hour, it evaluates:

1. the frozen persisted V2 recommended arrival;
2. the reconstructed earliest lower edge of the old displayed departure
   window (depart then, or issue-time if the window was already open);
3. matched leave-now from the same issue timestamp.

All three are scored using the same V88 successful-poll >=30 stock proxy used
for V75/V128 research. Original V2 departures more than eight hours after issue
are reported and excluded from the current-contract matched comparison.

The old exact *latest* browser departure bound cannot be fully reconstructed
because old audit rows did not persist target depletion / lifetime. V137 says
this explicitly and does not claim otherwise.

### V138 enhanced morning evidence brief

`research/v138_enhanced_departure_evidence_brief.py`

Keeps all V135 metrics intact and adds V137 direct original-V2 arrival truth as
a separate section so restock-window/cycle metrics are never conflated with
direct >=30-at-arrival proxy evidence.

### V139 one-shot VM operator

`deploy/scripts/v139_run_enhanced_departure_morning.sh`

Stages pinned read-only modules and runs V138 once under low priority and a
timeout. It does not modify production services, public website behavior,
timers, collector writes, or gameplay.

## What historical tests can and cannot prove

Can measure:
- whether a frozen recommended arrival is bracketed by successful global polls
  whose carried-forward item state is >=30;
- matched model-versus-leave-now outcomes on the same issue cohort;
- restock-window error and target-cycle membership for original V2;
- departure waits, abstentions, forecast churn, and whether far WATCHes later
  receive fresh near-departure confirmation.

Cannot prove:
- exact in-game stock at the instant a real player lands;
- purchase success;
- per-country upstream feed freshness, because only global heartbeat/provider
  evidence is persisted;
- independence of repeated five-minute/hourly forecasts within the same
  underlying restock cycle.

Unknown or censored evidence must remain UNKNOWN/PENDING, not be counted as a
failure.

## Still needs VM data

GitHub can validate the evaluator logic, but only the VM contains the live
collector and private ledgers. We still must verify:
- V128 actually kept recording after the first confirmed 24-row batch;
- how many V128 arrivals have now matured;
- V128 direct >=30 arrival proxy versus leave-now;
- V128 future WATCH -> fresh near-departure reconfirmation rate;
- original V2 direct >=30 arrival proxy via V137;
- archived V75 comparison and optional older sidecar inventory.

## Single next VM action

From Windows PowerShell:

```powershell
$key = "C:\Users\fungb\Desktop\.ssh\torn-fren.key"
$remote = "ubuntu@150.136.108.146"

& ssh -i $key $remote 'cd /home/ubuntu/torn-fren-v38-probe && git fetch origin research/v38-full-roster-live-prep-20261009 && git show 112d574d9767912367fb8fcaf0870828f1de0e82:deploy/scripts/v139_run_enhanced_departure_morning.sh | bash'
```

The operator itself pins the audit modules to commit
`142f10363037b31fc299183c7cfb0734cf7df50c`.

Do not restart or replace V128, deploy V130, or alter the public graph before
the real matured evidence is interpreted.
