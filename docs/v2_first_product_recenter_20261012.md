# TORN-FREN: V2-first product direction (12 Oct 2026)

## Decision and motivation

User clarification: the original Prediction V2 graph and its behavior are still
the intended product. Extensive item-specific champion research and V75–V139
prediction experiments were meant to **fix Prediction V2's accuracy issues**,
not replace its user experience with a standalone probabilistic departure tool.

**North star:** retain both the existing `/experimental` multi-item board and the original `/` V2 graph as first-class product views. Show, for any foreign item, a trustworthy next restock forecast,
stocked availability/lifetime window, and actionable earliest reasonable
departure/arrival window adjusted for the country's flight time. Present a
clear LIVE/TOO EARLY/GOOD TO LEAVE/LATE/WATCH distinction with uncertainty and
live revision behavior. The existing history graph remains the single-item analytical view, while `/experimental` remains the multi-item opportunity board. Both are retained.

The travel assistant is a second consumer of the same predictions: use stock,
flight duration, return trip, travel timings and economics to plan several
trips in a day without silently initiating gameplay actions.

## Two existing user-facing views

- **Experimental board**: `/experimental` and `/api/experimental/v41/predictions`, historically 21 champion rows plus optional three-item V87 preview. Lists item, existing champion, proposed departure, arrival, expiry/recompute deadline, and future WATCH states. The VM-deployed page source must be audited before patching, because this endpoint is missing from the research checkout's `web/app.py`.
- **V2 graph**: `/` plus `/api/history`. Single-item stock history, restock forecast bands, estimated stocked interval, country flight duration, actionable departure-window visualization, and projected P1/P2+.

New research integration code `research/v140_existing_experimental_beta_board.py` preserves both predictions separately. The feasibility guard `research/v141_v2_feasible_departure_window.py` is intended to fix collapsed impossible V2 windows. Neither is mounted on the public site.

## Retain from original V2

Files:
- `services/prediction_v2_live.py`: stock/depletion anchoring, forecast
  profile, restock error window, target arrival, projected P1/P2+ cycles.
- `web/app.py`: non-blocking /api/history, background profile/cache, source
  revision control, clock-only forecast roll.
- `web/static/index.html`: stock history and event markers, predicted
  restock overlay, target arrival/departure range, flight ticker, NEXT cycle.

Keep public page and production stable until a challenger wins a tested
comparison and user explicitly approves rollout. V128 is research-only.

## What the code currently does, not what we wish it did

- When depleted, predict next restock from observed depletion plus selected
  historical wait, with empirical error-window or labeled fallback interval.
- When stocked, predict current depletion, then next restock; Japan Xanax has
  specialized active-sellout blended slope/history logic.
- Subsequent P2/P3+ restocks advance by typical stocked lifetime plus
  depletion-to-restock wait. Greater depth increases uncertainty.
- Recommended arrival is forecast restock plus learned arrival offset (or
  midpoint lifetime fallback).
- Browser's *earliest* displayed arrival bound is max(recommended arrival,
  late restock bound), with latest from predicted depletion less a buffer.
  Departure range is arrival bounds minus country-specific PI+pilot flight.
- Browser shows TOO EARLY/GOOD TO LEAVE/LATE and updates target as earlier
  cycle departure windows expire.

This is not equivalent to V128:
- V128 samples 128 empirical HIGH/LOW phase paths, scores five-minute arrival
  candidates up to eight-hour departures, requires raw >=0.60 score in two
  consecutive bins, then chooses the earliest candidate.
- V128's score is NOT calibrated to real-game success probability and is not
  itself a restock/depletion forecast. Do not substitute it into the graph
  as a fabricated next-restock timestamp.

## Specific V2 product gaps confirmed by source inspection

- During an active-stock phase, `_build_live_prediction_v2_impl` forecasts a
  *future* P1 next cycle and sets `current_stock_estimated_reachable` from a
  time-to-estimated-depletion comparison. That path does not guarantee or
  explicitly model **>=30 remaining at ETA**; a source showing nonzero stock is
  not equivalent to >=30 stock at landing. Treat current-stock leave-now as a
  separate threshold-aware candidate, alongside future restock candidates.
- The browser's arrival-window fallback can collapse to a point when estimated
  depletion is earlier than the conservative restock/arrival lower bound. The
  UI must distinguish `NO_FEASIBLE_STOCKED_INTERVAL` from a genuinely useful
  departure range rather than displaying a misleading zero-width
  GOOD TO LEAVE moment.
- Mid-stock-lifetime arrival-offset fallbacks are explicitly labeled as
  uncalibrated in the V2 code. The UI needs a stronger evidence distinction
  before representing them as safe departures.

These are candidate product fixes for research/specification and regressions;
they are not authorization to mutate public V2 code or deploy new models.

## Problems to solve in V2 rather than starting a new tournament

1. Next-restock forecast error: wrong depletion anchor, provider discontinuity,
   historical wait shifts, long droughts, model selection uncertainty.
2. Stock-lifetime / threshold-30 sellout error: restock occurrence alone is
   insufficient; forecast a usable duration and estimated quantity floor.
3. Flight/departure reliability: recommend the *earliest reasonable* flight,
   not automatically now and not a distant watch that keeps moving away.
4. Recommendation stability: with unchanged item evidence, avoid artificial
   large Monte Carlo time movements (V130 phase-pinned seed challenger).
5. Evidence quality: global successful poll != country feed freshness;
   carried-forward change-only stock states are supporting PROXY evidence,
   not verified exact landing stock.
6. Performance: avoid 24 heavy computations per HTTP request or multiplying
   full-history scans across 200+ catalog items; precompute/cached revisions,
   bounded workers, SQLite indexes, separate live and research paths.

## Shared prediction interface (design; NOT yet a deployed endpoint)

One item snapshot should supply:
- item_key, model_id/config, issued_at, source/update as-of, evidence tier,
  current observed stock and phase, forecast freshness/expiry;
- predicted **restock** estimate and start/end window, or explicit UNKNOWN;
- predicted stock>=30 **availability interval(s)** (start, end), and
  estimated depletion/sellout timing, with model rationale;
- country flight time and candidate earliest departure, preferred departure
  window, arrival ETA and projected remaining stock, or explicit ABSTAIN;
- next reachable P1/P2/P3 if first restock is too early to reach;
- uncertainty, historical sample size, observed errors, expected staleness,
  current state WATCH / NEAR TERM / READY / EXPIRED / UNKNOWN;
- revision reason (new stock observation / new restock / model selection /
  stale feed), timestamp of last change.

When no explicit restock bound exists in a specialist, keep it UNKNOWN; an
arrival probability/score curve must not be converted into an invented restock.

## Model comparison: outcome-aligned but V2-specific

Compare each incumbent V2 forecast, named per-item champions and V128/V130
challengers only on genuinely comparable outputs. Two independent axes:

A. **Restock/depletion forecast accuracy**
- time error (signed, median absolute, p90) for next observed restock and
  >=30-to-<30 threshold loss;
- actual restock captured by predicted interval (coverage) vs interval width;
- P1 vs multi-cycle P2/P3+ accuracy, sample counts, phase/provider validity.

B. **Trip/departure usefulness**
- frozen as-issued model arrival>=30 stock proxy vs matched leave-now;
- wait-to-depart and total turnaround; decision coverage and abstentions;
- far WATCH that reconfirms to fresh near-term readiness rather than rolling;
- arrival stock margin and surviving time if defensibly estimated;
- same-observed-state forecast jitter, missed opportunities and stale inputs.

Use V131/V132/V134/V135 plus V137/V138 for historical evidence, not as proof
of exact gameplay outcomes. Compare out-of-sample and continue a protected
prospective shadow cohort. Repeated five-minute forecasts in the same restock
cycle are correlated; report events as distinct cycles too.

**Promotion:** no champion/experimental component replaces V2 merely because
it has more historical tests, a high internal simulation score, or a high
restock-window hit fraction. A candidate must demonstrate user-facing lift on
the above relevant metrics with honest cohort/unknown accounting.

## Delivery sequence

**Milestone 0 — collect evidence (VM required).** Check 24-row/5-minute V128
recording health; run one read-only V139 enhanced audit; preserve and report
unknowns. This completes the missed last-night V131 and V135 original-graph
audit in one controlled step.

**Milestone 1 — stabilize the V2 contract.** Identify per-item/phase causes of
old V2 prediction and stock-survival misses. Write regression fixtures and a
shared, read-only forecast contract. Keep the same UI and public route.

**Milestone 2 — improve V2's prediction engine.** Compare V2 vs item champion
for restock timestamp and stocked-interval accuracy, with a separate
departure-decision layer. Adopt only compatible proven components (possibly
a V130-like stabilization) behind a feature flag/canary, not site-wide switch.

**Milestone 3 — V2 page improvements.** Same graph + observed stock, predicted
next restock band, estimated stocked interval, flight/arrival markers,
DEPART window/countdown, P2+, WATCH/reconfirm and evidence text. Test behavior
on stale data, sudden restock/depletion, slow country feeds, missing model,
and long flights. Only modify public site with user go-ahead.

**Milestone 4 — Torn Travel Assistant (planning, not gameplay bot).**
Read versioned forecast snapshots across all supported items, account for
flight+return time, stocks, value/profit per slot and country/item filters,
build a day itinerary of leave/arrive/return/recheck windows, dynamically
replan as new observations arrive. Ensure it can recommend delaying departure
if the resulting trip is more valuable. No automatic in-game travel/purchase.

**Milestone 5 — 200+ items.** Expand catalog with tiered modeling: specialists
where validated, statistical base model for sufficient data, explicit NO
FORECAST otherwise. One cached bounded compute path, not 200 live request
re-fits. Keep expensive research and collector writes isolated.

## Working agreement to avoid drift

- Every new model task must name the **specific V2 field/decision it improves**.
- Favor shipping measurable end-to-end increments over incrementing version
  numbers and endlessly launching more tournaments.
- After each experiment: was restock time more accurate? Was the stock window
  safer? Did it change departure recommendation? Did it help users land with
  >=30? If not, do not promote it.
- Product/website edits require explicit approval. No production service,
  collector DB, or timer changes as a side effect of research.
- One concise VM action when user gets home; do GitHub-side inspection/tests
  independently and wait for genuine private VM evidence for accuracy claims.
