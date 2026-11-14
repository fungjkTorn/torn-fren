# Torn-FREN Hot List / All Items contract — November 2026

## Site and views
- Public travel planner is `/experimental`, not root. The original stock graph remains at `/` and `/?country=...&item=...`.
- Hot List is a **curated profitability shortlist**, not a promise of stock availability. All Items is an **unrestricted union** of the 236 reference identities, live catalog and publisher roster.
- **The $15,000 Item Market value floor applies ONLY to Hot List.** All Items must continue to display low-value items and manually excluded items with search/category filters intact.
- Initial Hot List pool is 25 existing foreign candidates (the first 25 tracked item/country identities), plus five Nikeh Performance NPC redemption candidates. Exclude UK Xanax, Mexico Jaguar Plushie, Hawaii Orchid, and Cayman Banana Orchid from Hot List only.
- Require valid current market reference `>= $15,000` and positive estimated net trip profit; stale or missing market data suppresses eligibility. No forecast is required for *profitability-only* membership.

## Selling sources and math
- Default capacity **15**, editable by runners. Default comparison `theoretical profit / hour`.
- **Item Market**: 5% fee. Per-item profit = `0.95 * market_price - foreign_price`.
- **Nikeh Performance**: fixed NPC cash redemption, no Item Market fee. Per-item profit = `nikeh_payout - foreign_price`. Requires Sports Administration education. These are NOT bazaar sale quotes.
- Fixed NPC payouts (Torn wiki): Canada Bear Gall $35,000; China Pangolin Scales $205,000; Hawaii Shark Fin $66,000; China Tiger Bone Powder $70,000; Japan Whale Meat $40,000.
- `full_load_profit = per_item_profit * inventory_slots`. `theoretical_hourly = full_load_profit * 3600 / (2 * one_way_flight_seconds)`.
- When a **verified departure** is published, additionally show `wait_adjusted_hourly = full_load_profit * 3600 / (2 * flight_seconds + seconds_until_departure)`; no false wait-adjusted result for unforecasted items.
- Theoretical hourly excludes selling delay, partial fills, demand, trips spent waiting, restock misses and other costs.

## Forecast safety
- If published advice is missing or stale, show `Awaiting forecast` and `Theoretical profit only`, NOT `Leave now` or an invented arrival time.
- Flight-time alternatives are projections, not validated forecasting accuracy. The presence of a fixed Nikeh price never promotes a research model.
- A filtered `In stock now` view must require recent published observed stock; unforecasted items must not be presented as confirmed available.
- No changes to collectors, models, publisher, Beanstalk, or stock-history data.

## Later upgrade path
Beanstalk integration remains optional. When enough real sales exist, a separate selling-liquidity layer can rank by actual bazaar price, observed time to sell and supply/demand without conflating these with travel forecasts. Keep sale source, estimated profit, and departure evidence independent.

## Deployment
`deploy/Publish-HotList.ps1` makes a guarded, owner-run SSH update. If the live website still runs V1 root/experimental routes, it first uses pinned reviewed PR24's route-migration release; then deploys the four reviewed UI assets without restarting the web service. Only exact signed predecessor assets (including CRLF-only Windows conversions) are replaceable. Other VM asset changes abort. Backup, smoke verification, and rollback are mandatory.
