# Arbitrage Scanner v0

This module is intentionally separate from Torn Fren's travel-profit system.

## Goal

Find cases where player bazaar inventory can be purchased below a public trader buy price by a configurable minimum profit per item.

Example:

- 8 Meteorite Fragments at $455,000
- 22 at $460,000
- 40 at $468,000
- trader buys at $505,000
- minimum required profit = $20,000 per item

All 70 units qualify. The engine consumes the cheapest listings first and computes the weighted acquisition cost internally.

## Separation of concerns

`services/arbitrage_sources.py`
: Normalizes external source rows into a common shape.

`modules/arbitrage.py`
: Contains the source-agnostic profit calculation.

Future adapters can collect from:

- TornW3B bazaar listings
- TornW3B trader buy offers
- Torn Exchange trader buy offers
- manual/pinned traders
- other allowed read-only sources

The calculation layer does not care where the data came from.

## v0 calculation rules

For each trader buy offer:

1. Match bazaar listings for the same item.
2. Sort listings from cheapest to most expensive.
3. Reject any listing where:
   - trader price - listing price < configured minimum profit per item
   - ROI is below the configured minimum ROI
4. Consume qualifying listings cheapest-first.
5. Respect an optional buyer quantity cap.
6. Calculate:
   - total quantity
   - total cost
   - total revenue
   - total profit
   - weighted average buy price
   - average profit per item
   - ROI
   - seller/listing counts
7. When multiple buyers exist for one item, keep the strongest opportunity for display.

## Important data-quality rule

Source freshness must remain attached to the normalized row. TornW3B listings can be scan/cache based, so a displayed opportunity is not proof that the item still exists in the seller's bazaar.

The UI should eventually expose a freshness/status indicator instead of implying inventory is guaranteed.


## Live v0 integration

Current acquisition sources:

- TornW3B's supported marketplace API for bazaar listings across the foreign-item catalog.
- Official Torn v2 item-market listings across that same foreign-item catalog when a Torn API key is available.

Current buyer sources:

- TornW3B's supported marketplace trader API.
- Torn Exchange's public `api/best_listing` endpoint for the best active trader per item, cached locally to respect its request ceiling.

The foreign-item universe is generated from the same YATA/Prometheus travel
export Torn Fren already uses. This keeps v0 intentionally smaller than the
full Torn item universe.

## User surfaces

- `python arbitrage_scan.py --force` provides a terminal smoke test.
- `GET /api/arbitrage` returns the normalized report.
- `/arbitrage` is a sortable/searchable web table with item diagnostics and anomaly labels.
- Discord `/arbitrage [min_profit] [min_roi_percent] [min_quantity]` returns the top eight
  opportunities and links to the trader pricelist and TornW3B item page.

## Refresh policy

A source snapshot is cached for 15 minutes by default. A force refresh is
available for manual testing, but the normal UI and Discord command reuse the
cache. Third-party collection defaults to only two workers. The priority
official Torn item-market requests are intentionally sequential and rate
limited.

## Current limitation

The scanner treats public trader prices as offers and does not assume a trader
has unlimited cash or will accept unlimited quantity. The UI therefore reports
the currently visible profitable inventory, but a user should still confirm the
trader's pricelist/status before moving a large stack.


### Source controls

For diagnostics and CI, individual slower sources can be disabled without
changing the calculation engine:

- `ARBITRAGE_ENABLE_TORN_EXCHANGE=0`
- `ARBITRAGE_ENABLE_TORN_ITEM_MARKET=0`

Production defaults both sources on. Torn Exchange responses are cached in
`data/arbitrage_cache.db` for 30 minutes by default and calls are serialized
at roughly 6.2 seconds apart. The file is covered by the repository's existing
`data/*.db` ignore rule.

## Validation

The branch test workflow compiles the integration, runs deterministic unit and
parser tests, and performs one live Basalt Point smoke test against TornW3B and
Torn Exchange. A deliberate full-catalog diagnostic remains available via
`foreign_arbitrage_smoke.py`, but it is not run on every CI push so we do not
hammer third-party services. TornW3B calls in production are serialized and
retry once on HTTP 429. The key-dependent official Torn item-market path is
covered by mocked parser tests; live use requires the runtime `TORN_API_KEY`.


### Non-blocking interactive refresh

A full foreign-item refresh can take time because third-party rate limits are
respected. Web and Discord requests therefore do not sit open waiting for a
cold full scan. They return the newest persisted snapshot immediately and start
one daemon refresh in the background when the cache is stale. The web page
shows the snapshot age, indicates when a refresh is running, and polls again
while that refresh is active.

Successful refreshes are persisted to `data/arbitrage_snapshot.json`, so an
application restart can immediately serve the last known scanner state while a
new refresh runs. CLI calls remain synchronous by default so smoke tests can
fail loudly and report the completed source state.


## Staging deployment

The scanner is intentionally deployed separately from the production Torn Fren
web process while v0 is being validated.

Current layout:

- production repo: `/opt/torn-fren`
- arbitrage staging repo: `/opt/torn-fren-arbitrage`
- production web: `127.0.0.1:8000`
- arbitrage staging web: `127.0.0.1:8001`
- staging service: `torn-fren-arbitrage.service`
- public page: `https://tornfren.duckdns.org/arbitrage`

Nginx routes the arbitrage page/API to port 8001 while the rest of Torn Fren
continues to use port 8000.

Normal staging update:

```bash
cd /opt/torn-fren-arbitrage
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart torn-fren-arbitrage.service
sudo systemctl status torn-fren-arbitrage.service --no-pager
```

Item diagnostics intentionally reuse the existing `/api/arbitrage?item=...`
route, so the current exact Nginx API route does not need to change.

Always run `sudo nginx -t` before reloading Nginx if the proxy configuration
is changed for any future scanner route.

## Scanner UX / trust metadata

The web scanner now:

- defaults to total-profit descending and shows the active sort direction;
- searches across the full foreign-item catalog;
- exposes an item diagnostic view with cheapest buy listings and highest trader
  bids even when the item does not currently qualify;
- reports quantity contributed by each buy source;
- labels extreme/high spreads and buyer-price outliers without suppressing them.

Anomaly labels are warnings only. They are deliberately not filters because
mispriced trader lists can be real opportunities, but the user should verify
the trader before committing meaningful capital.

The UI also supports country, acquisition-source, and buyer-source filters.
Source filtering recomputes the opportunity instead of merely hiding source
badges, so weighted cost and quantity stay consistent with the selected data.

Force refresh is server-side throttled (five minutes by default) in addition to
preventing concurrent refresh threads. This keeps a public testing page from
accidentally hammering third-party sources.

The official Torn Item Market source uses Torn's API, not background scraping
of Torn web pages.
