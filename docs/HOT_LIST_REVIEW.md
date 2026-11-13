# Homepage Hot List draft

Homepage defaults to the Hot List; All Items covers the catalog. Category filters, search, fixed ten-row pagination, item thumbnails/fallback, inventory capacity and flight presets are included. Stock graphs remain at the existing country/item query URLs. Existing experimental/travel-decisions lists retain their layout but lose the simulation-dot column and legend. Details retain the evidence.

Hot List eligibility: fresh supported departure estimate, usable sale price and positive full-load margin. Default sort is full-load margin divided by outbound + return flight time + time waiting before departure. Theoretical hourly return excludes departure wait. Neither is probability-adjusted expected profit; selling delay, demand, failure risk and other costs remain unmodelled. Full-load estimates assume sufficient stock at landing; observed stock is not a guarantee.

The existing /api/catalog supplies Torn market values and foreign purchase prices automatically; neither is editable in the Hot List. Profit = (market reference × 0.95 − foreign purchase cost) × selected inventory capacity. Stale or missing market values suppress profit rankings. These are estimates with the existing 5% Item Market selling fee, not live bazaar quotes. No automatic bazaar-demand ranking or Beanstalk integration is required for this release.

Published flight keeps published advice. Other preset flight times select the earliest reachable batch from unchanged stock forecasts, with ten-second end margin; these are labelled previews, with no transferred historical success claim. No model, collector or ledger changes.

Validation: node tests/hotlist-core.test.cjs, JS syntax checks and Python compile passed. Browser test is supplied using synthetic fixtures but could not execute here: Chromium socket creation is blocked by the environment. Desktop/mobile screenshots, full-app middleware regression and production feed verification are outstanding. This is a draft, not deployment-ready. No merge, VM deployment or user downloads were performed.
