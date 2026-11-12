# TORN-FREN product UI contract — V171

Date: 2026-10-23  
Status: research branch only; not deployed

## Product structure

TORN-FREN keeps three first-class views with one shared navigation shell.

1. **Overview** — `/experimental`
   - Scan supported foreign items.
   - Show concise guidance: current status, leave time, land time, recheck time.
   - Search/filter the supported roster.
   - Open an item's detailed graph or the travel planner.
   - Do not run a forecasting model in the browser.

2. **Item detail** — `/`
   - Preserve the original V2 stock-history graph.
   - Preserve V2 lifecycle telemetry: current stock, last restock/depletion,
     stocked lifetime, zero-to-restock wait, valid/excluded cycles.
   - Make the travel decision prominent without hiding model/history context.
   - Keep graph timeframes and country/item browser.

3. **Travel decisions** — `/travel-decisions`
   - Search, country/category filtering, sorting and browser-local watchlists.
   - Show the earliest currently supported trip.
   - Allow a player-specific flight-duration override.
   - Show restock-event timeline and evidence for the selected trip.
   - No Torn API key is required in this release.

Global navigation labels are **Overview**, **Item detail**, and **Travel decisions**.
All views are explicitly labeled **Research preview** until release gates are met.

## Stable frontend status vocabulary

The additive `services/product_ui_contract_v171.py` contract exposes:

- `LEAVE_NOW` — the supported departure window is open.
- `LEAVE_IMMINENT` — departure is within 60 seconds.
- `LEAVE_SOON` — departure is within 15 minutes.
- `WATCH` — supported departure is farther out; continue replanning.
- `NO_SUPPORTED_TRIP` — no currently supported departure.
- `WINDOW_PASSED` — previously modeled window is no longer usable.
- `STALE` — source/snapshot freshness is insufficient.

User-visible copy uses **Leave**, **Land**, **Leave by/Recheck by**, and
**Target stock window**. Research-internal version names should not be the
primary user-facing status.

## Additive item contract

Existing API fields remain intact. The new `ui` object contains:

- `item`
  - key, name, country, country name, category, graph URL
- `live`
  - observed quantity, last quantity change, source poll age, freshness
- `decision`
  - status + label
  - departure, arrival, departure deadline
  - leave-in seconds
  - player flight duration
  - selected restock event
  - source of the recommendation
  - explicit recheck-before-departure flag
- `forecast`
  - event timeline
  - departure/event model provenance
  - policy
  - research quality label
- `evidence`
  - historical successes / resolved arrivals when policy/model/flight match
  - explicit flags that the result is not a guarantee and not a calibrated
    per-flight probability
- `copy`
  - primary UI action
  - standard recheck note

The travel read-model attaches this contract without removing or renaming old
response fields.

## Data semantics

The UI must keep these distinctions visible:

- **Observed**: actual collected stock quantity/history.
- **Modeled**: future restock, depletion and travel windows.
- **Historical evidence**: replay performance for a matching model/policy/flight.
- **Not calibrated**: replay success must not be displayed as a guaranteed
  per-flight probability.
- **Freshness**: heartbeat/poll freshness is separate from how long a future
  departure remains scheduled.
- **No arbitrary time horizon**: future travel is event-driven; distant
  restocks may be shown when they are the earliest supportable event.

## Visual hierarchy

### Overview
Primary information per item:
1. item + country/category
2. guidance state
3. leave time
4. land time
5. recheck/freshness

Model name remains visible but secondary.

### Item detail
Primary order:
1. item identity + navigation
2. travel/departure guidance
3. observed history + lifecycle metrics
4. restock forecast/evidence
5. stock graph

### Travel decisions
Primary order:
1. search/watchlist/filter controls
2. list of candidate items
3. selected-trip countdown
4. leave / land / leave-by
5. flight duration
6. evidence and event timeline
7. detailed graph link

## Responsive behavior

The shared shell collapses to a menu on narrow screens. Item detail retains a
single-column mobile layout. Travel Decisions moves the selected trip below
the item list. Overview retains its table-to-stacked-row behavior and adds
search/guidance filtering.

## Production safety / release sequence

The deployed VM `/experimental` source is known to differ from the GitHub
checkout. Do **not** copy the research `web/app.py` or experimental fixture
over production.

Before deployment:

1. Read-only fingerprint the deployed `/experimental` HTML/API and current
   static assets.
2. Verify the SHA-guarded experimental transformation still matches the
   deployed owner page, or create a new reviewed transformation for the actual
   production fingerprint.
3. Run Python tests for the product contract, travel read-model, router and
   experimental patcher.
4. Run browser QA for desktop/mobile navigation, filters, long names, stale
   data, no-trip, leave-now and distant-watch states.
5. Deploy web assets/routes only behind the existing beta/canary controls.
6. Verify `/`, `/experimental`, `/travel-decisions`, and their APIs.
7. Keep an exact rollback copy of changed web/static files.
8. No collector, model roster, timer or prediction-worker change is implied by
   this UI branch.

## Files added/changed

- `services/product_ui_contract_v171.py`
- `services/travel_read_model.py`
- `web/static/site_shell.css`
- `web/static/site_shell.js`
- `web/static/index.html`
- `web/travel_decisions.html`
- `deploy/scripts/prepare_shared_experimental_page.py`
- `tests/test_product_ui_contract_v171.py`
- `tests/test_site_shell_v171.py`

This branch prepares the product surface. It does not certify model accuracy
or authorize production deployment.
