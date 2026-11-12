# Torn Fren price foundation — 2026-09-27

Changes:
- `stock_history` now persists a row when quantity OR foreign buy `cost` changes.
- Price-only changes do not enter `changed_items`, so they do not trigger prediction/forecast audits.
- If a provider transiently omits `cost`, the last persisted cost is carried forward.
- `/stock` already showed foreign buy cost and continues to do so.
- `/predict` now shows the current persisted foreign buy price and source.
- `/history` now includes the current foreign buy price.
- Web graph stats now show Foreign buy price immediately, even while heavier stats/prediction work is warming.
- Price-only DB rows are filtered from the stock quantity graph so they do not create fake stock-change points.

Provider behavior:
- The existing provider layer remains YATA-primary with Prometheus fallback.
- Both provider payloads expose `cost`; the persisted row keeps the provider source.

Historical caveat:
- Prior to this patch, price-only changes were not saved. Historical price series before deployment is therefore incomplete.
- From deployment forward, price-only changes are captured.

## Profitability v1 — 2026-09-27

- Adds a global/player-agnostic profitability layer.
- Market price uses Torn's global item `market_value`, cached for 5 minutes from one all-items API request.
- Item Market sale proceeds assume the regular 5% sale fee.
- Net profit per item = market value × 0.95 − foreign buy price.
- Profit / slot / hour = net profit per item ÷ PI + pilot round-trip hours.
- ROI = net profit per item ÷ foreign buy price.
- Country and item selectors remain separate.
- Within the selected country, items are sorted highest → lowest by profit / slot / hour.
- Items without usable market/foreign pricing remain selectable and sort below priced items.
- Graph stats now show market price, net profit / item, profit / slot / hour, and ROI.
- Capacity, personal flight configuration, live travel state, and API-linked user profiles are intentionally deferred to the personalization phase.