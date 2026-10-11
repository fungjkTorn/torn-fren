# TORN Fren travel-decision logic — draft (October 2026)

**Design only; not deployed.** The 24-item experimental roster and current public services remain unchanged.

## User need: fastest defensible flight, not merely distant restock predictions

Use a shared **set of candidate opportunities** to support these views:

* **Leave Now:** all items with defensible departures right now or within an adjustable urgency window (suggested default <=5 min). Exclude stale proposals and arrivals projected below 30 units. If none meet the minimum evidence bar, say so.
* **Next Opportunity:** earliest defensible departure per item, with accurate leave-in countdown and separate WATCH state for distant options. Avoid universal 60–90-minute waiting limits; short-flight items need rapid-trip options.
* **Best Chance:** strong evidence for >=30 units at arrival (+10s grace) combined with arrival-stock margin, uncertainty, forecast stability, and time cost. Do not invent calibrated probability percentages.

Current single-output workers cannot supply several genuinely different alternatives. Candidate generation/selection needs independent research and no-lookahead replay before deployment.

## Outcome metrics

1. Direct fresh YATA observation within arrival..arrival+10s (primary observed evidence; inspect per-country provider update epoch).
2. Bracketed arrival state with credible before-and-after observations, carried forward from change-only stock rows using successful collector heartbeats (supporting evidence only).
3. Optional +/-180s analysis separately. No mixing 10s and 180s rates.
4. Unknown if provider stale, collection gap, stock changes through the bracket, or evidence missing. Do not quietly count unknown as success or miss.
5. Track valid as-issued forecasts, exact arrival-target duplicates, and distinct observed restock windows separately. Many five-minute replans are correlated.
6. Decision coverage = share of item-by-five-minute eligible decisions with a qualifying fresh departure in each wait mode. Opportunity capture = fraction of distinct observed reachable stocked windows targeted by a valid proposal.
7. Quantify departure wait in bins 0–5m, 5–15m, 15–30m, 30–60m, 1–2h, 2–4h, 4–6h, 6–8h. Report per item.
8. Forecast stability = material recommendation changes, withdrawn proposals, reappeared proposals, and issued-time drift between updates.
9. Stock survival and arrival margin = stock expected *remaining at actual arrival*, not just initial restock quantity; track lower-bound uncertainty and likely time above 30.
10. Incremental value = matched comparison against flying immediately or consistent baselines, net of waiting/round trips and later profit per player-hour. Keep separate from raw arrival accuracy.
11. Operational reliability = successful scheduled runs with current provider data vs missed/abstained; report sample sizes and coverage denominator.

## Polling and future observer

The current poller requests the full YATA export roughly every 30s with Prometheus fallback, and only writes per-item stock rows on quantity/cost changes; successful cycles are separately persisted in poll_heartbeats. The incoming travel export has a per-country update timestamp, but the existing item-change storage path does not preserve it.

An opt-in isolated arrival observer could make extra **full-export** calls and record request/response timestamps, provider update epoch, source, observed quantity, and immutable forecast ID for selected arrival windows, sharing calls among nearby arrivals and respecting external rate limits. A fresh HTTP fetch is *not* necessarily fresh in-game stock.

## UX design to follow logical validation

- Overview: categories Flowers, Plushies, Medical, Fossils, Other; country/item filters; Leave Now / Next Opportunity / Best Chance ranking; watchlist state; first-class leave countdown and revision status.
- Detail: observed stock history, restock/depletion events, flight/arrival markers, future opportunities, model revision timeline, verified vs proxy accuracy. Show graph near the top.
- Current 24 models only; category navigation can include other items while accurately labeling them "No specialist model".
- Distinguish READY NOW, DEPART SOON, WATCH, UPDATED, EXPIRED, ABSTAINED. Do not label a 6-hour watch "Ready".
- Optional restricted-scope user key and personal itinerary preferences later. Can plan routes and profit but never silently trigger in-game travel or buying. Never promise guaranteed stock or profit.

## Next read-only validation steps

1. V89 pending/horizon diagnosis: classify the previously observed large pending pool by wait-to-depart vs hypothetical in-flight vs post-arrival evidence buffer, per-item waits, and frequent target revisions.
2. V88 reconstruction of observed stock using successful collector heartbeats, labeled proxy and compared with immediate flight for matched instances.
3. Historical no-lookahead candidate replay across multiple wait policies; item-specific opportunity rates, stock margin, depletion risk, stability and missed available departures.
4. Pilot independent arrival-focused data capture with strong timestamp freshness gates; keep collector unchanged until evaluated.
5. Only after evaluation adjust experimental display or specialist recommendations, with rollback and no public gameplay automation.
