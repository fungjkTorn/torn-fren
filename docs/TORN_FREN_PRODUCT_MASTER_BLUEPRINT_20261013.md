# TORN-FREN — Unified Travel Prediction Product Blueprint
**Status:** accepted goal, NOT a claim existing public views already implement it
**Updated:** 2026-10-13
**Source of truth:** retain original `web/static/index.html`, `web/app.py` and production API behavior; existing `/experimental` experience and private `deploy/scripts/v160_private_beta_board.py` remain available; new code additive and gated. Never replace V2 with a simplified research UI.

## The user-facing promise

**Choose what you want, and TORN-FREN tells you the next realistic time to travel, what stock is likely at arrival, and why it trusts or does not trust the recommendation.** All restock predictions are underlying inventory events. A departure decision is a different, flight-conditioned problem. No prediction creates stock. No user needs a Torn API key to browse public item data.

### 1. Detailed Item Graph (evolve original V2, not replace)
- Item/country picker and search; actual stock history in an interactive, zoomable 24h/72h/7d customizable graph; quantity, source and last successful collection displayed separately.
- Clearly distinguish **observed** restock/depletion markers vs **predicted** event point, estimated early/late uncertainty band, predicted stock duration and multiple later restocks.
- Selected player travel duration, leave-by time, leave-window start/end, arrival estimate, countdown to next estimated feasible departure, restock countdown, expected stock-at-landing and reason for abstention.
- Per-item supporting data: stock source/cross-provider disagreement, quantity on last observation, number of clean cycles, known collection gaps, currently high/low phase, last actual restock, expected stock lifetime, future sequence confidence degradation, model name/accuracy only when out-of-sample.
- Graph predictions synchronized with board; mark when a user-specified flight WOULD land; never draw future actual stock as observed.
- Product bar: Item graph / All items / Travel decisions, without breaking direct links to existing V2 or `/experimental`.

### 2. All-item Dashboard (evolve existing /experimental)
- Every item in searchable, sortable country/category list; initial 24 beta roster then all 200+ as supported and tested, not artificial model completion or per-request expensive Monte Carlo.
- Cards/rows show live quantity and freshness, next confirmed/provisional restock window, **earliest reachable departure for next forecasted stocked interval**, deadline, arrival clock, how many minutes to wait, source health and calibrated confidence (or explicitly `UNCALIBRATED`), and optional predicted resale/profit/ROI if prices are fresh and grounded.
- Filters: country, item type, category, quantity/minimal stock, restock ETA, departure ETA, arrival ETA, confidence/coverage, profitability, unknown/excluded.
- Decision tags: **WAIT**, **DEPARTURE WINDOW ESTIMATED**, **RESTOCK UNREACHABLE**, **NO RELIABLE FORECAST**, **STALE DATA**, and verified current-stock candidates (observed stock and modeled survival distinguished). Do not say SAFE/GUARANTEED.
- If the next restock is too soon for the travel duration, show it but recommend the earliest later **reachable** interval; never omit an event to make model performance look better.
- Virtualized/paginated UI and cheap aggregated read-model, no >200 fresh simulation loops per page request; use batch precomputation and cache by source update revision, per-user travel adjustment at request time.

### 3. Travel Decisions / Item Discovery / Watchlist
- Search/filter by item, country, category (flowers, plushies, Xanax, overseas meds, etc.) and desired amount (default >=30 for current research comparisons), with optional favorite/watch list and multiple selected-item goals.
- For a chosen trip show whether **LEAVE NOW**, **LEAVE IN [countdown]**, **CONSIDER ALTERNATE ITEM/COUNTRY**, or **WAIT FOR RECONFIRMATION**; estimated restock/arrival timing band and expected stock lifetime.
- Decisions rank usefulness by **chance of qualifying stock at arrival**, with historical timing quality and stock survival separately until calibrated jointly. Model cost of missed flight and available alternative items; do not conflate restock recall with flight success.
- Watchlists may be browser-local for anonymous use initially; later encrypted account-bound server storage and optional alerts (watchlist event, entry into departure window, forecast drift, stale-source warning). Alerts are informational, never autonomous gameplay.
- Later optional Torn API-key linkage **only** after confirming Torn rules/permissions: minimal read-only key scopes, never in URL/log/query string or frontend-localStorage, HTTPS, encryption at rest, per-user token rotation/revocation and deletion, key health, API rate limiting, key-specific user identity and current flight/airstrip perks. No API key required to browse.
- Personal departure and arrival clocks recomputed per player's real travel modifiers (plus flight already in progress, timezone/display preferences), item stock threshold, purchasing capacity and budget constraints; never assume the static research flight schedule matches every account.

## Required prediction data contract (shared by all 3 views)

**One event stream per item** from a single as-of timestamp and model version:
`{item_id,country,item_name,item_category,source_revision,source_poll_age,asof,restock_events:[{predicted_epoch,early_epoch,late_epoch,expected_stocked_end_epoch,horizon,calibration_state}],observed_current_quantity,observed_at,source,gaps,model_version,model_status}`.

**Separate per-player travel decision** derived from the same events:
`{item_id,asof,player_travel_seconds,grace_seconds,target_qty,decision_status,next_reachable_event,earliest_departure_epoch,latest_departure_epoch,suggested_departure_epoch,projected_arrival_epoch,expected_stock_window,update_due_epoch,reasons,uncertainty,stale}`.

Restock events exist independently of a flight. If user cannot reach an event, preserve it in the graph but mark it unreachable. Never invent point-perfect timing when model is imprecise. **Unknown, unsupported, stale, and low-confidence cases must abstain** from actionable certainty. Recalculate ETA countdown client-side every second from server-issued absolute epoch; refresh recommendation on new stock change, successful poll or model tick, not by guessing.

## Research / evaluation needed for meaningful claims

1. Model **every observed clean restock**, capture coverage/recall at ±15s, ±60s, ±10m, precision/false-alarm count, timing error, per item/country, leakage-safe time split. Distinguish source disagreement and poll misses.
2. Record **every five-minute as-issued recommendation**, all eligible items and all candidates (including no-action/abstentions), with immutable issue ID, source cutoff, proposed events, departure status, arrival epoch, uncertainty, model SHA, user travel scenario. The worker must never use future data.
3. After real observation covers forecasted arrival, score stock≥requested threshold **AT arrival or permitted 10-second grace**, with clean source heartbeat; classify SUCCESS/FAILURE/UNKNOWN, separately score depart timing and missed restocks. Do not give unobserved rows failures or successes.
4. Distinguish player-personalized airstrip/business/property perks and current state from generic country flight constants. Validate earliest *reachable* departure and latest viable departure, not solely `next restock`.
5. Evaluate all forecasts as-issued and one-to-one restock events, no selective success-only denominator or restock-conditioned evaluation masquerading as a travel policy. Report coverage, abstention, false positives, missed opportunities, calibrated probability (if possible), real arrival success by item and time of day.
6. Use rolling chronological train/validation/test splits and prospective holdout; compare true per-item champs with all-history V163, 8/16/32 complete phases, baseline immediate travel, existing V2 and former tournament champions where code exists. No promotion on a single replay result.
7. Candidate experiments run immediately on new approved model commits; one self-hosted worker at a time to prevent resource contention. Five-minute GitHub scheduler is a *fallback*, not an agent that invents algorithms. Snapshot currently refreshes ~30m, so repeating unchanged reports every 5m does not add information; schedule a separate, explicit VM-owned change to 5m after load profiling. CI and runner workload limited.

## Current verified baselines (Oct 13/14, not production claims)

- [24-item 4-hour history test](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38498702749): 2,315 clean restocks; V163 46.95% recall at ±10m, 7.47% at ±60s, 2.20% at ±15s; event precision 45.90%.
- [V165 last flight-lead frozen 5m checkpoint historical replay](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38499303543): 2,359 hindsight-selected clean restocks; V163 50.57% recall ±10m and 6.36% ±60s; neither genuine as-issued departure policy nor observed arrival success; note outcome-selected issue times.
- Current 24-item beta covers ONLY current vetted roster. Past results DO NOT justify a 90% accuracy badge or a 200-item live promise.

## Build phases and gates

**Phase A — shared event/decision APIs:** Pin schema, explicit uncalibrated estimates, source health and per-user flight derivation; preserve V2 and /experimental, add tested adapters/feature flags; compare current UI capabilities to target.

**Phase B — as-issued 5m shadow:** Record independent candidate times at every cycle; heartbeats, clean stock ≥30 at arrival, one-to-one events; live performance tables and threshold proof; test 24 items.

**Phase C — accuracy & safe item rollout:** Auto-run candidate suites after each new approved commit, record results in private GitHub, model router per item based on holdout performance, abstention/stale policy; scale 24 -> 50 -> 100 -> 200+ with bounded costs.

**Phase D — unified interface:** Enrich existing graph and multi-item experimental UI; build Travel Decisions third view with country/category/watchlist filters; anonymous browser-first.

**Phase E — opt-in accounts/keys:** Torn read-only API key integration only if documented compliant, encrypted credential vault, fine-grained consent, personal travel modifiers, watchlist sync, notification hygiene, rate limits, export/delete.

**Shipping gate:** Both legacy pages unaffected; no raw secret ever in GitHub artifacts; no auto travel/buy game actions; no 90% claim without real holdout/prospective evidence; all timestamps honest UTC epoch/source age; fail-safe when old, not invented countdowns.

## Non-goals
Automatically travel in Torn, buy or transfer items, promise perfect stock on landing, expose player credentials to research runner, or change production on research-branch push. Promoting models and publishing pages require separately reviewed and intentional opt-in deployment.
