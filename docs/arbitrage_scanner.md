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
