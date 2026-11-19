# Beanstalk seven-pick Hot List — public JSON contract

## Version 2 upgrade: two Xanax destinations and freshness

Prepared November 19, 2026; this code change is not a production deployment.
GET `/api/beanstalk-hot-list?version=2` opts into schema
`torn-fren-beanstalk-hot-list-v2`: exactly eight picks, two Xanax, two plushies,
two flowers and two Nikeh. The default URL still returns the legacy v1 seven
picks, so old clients remain supported during rollout. Unsupported versions
return 400; insufficient eligible items return 503 without padding/duplicates.

The two Xanax are the highest estimated round-trip profit/hour from distinct
eligible destinations, including UK Xanax when its profitability qualifies. All prior prices, fee,
flight, market floor, other exclusions and plushie/flower/Nikeh constraints
remain intact. The minimum-six-destination preference also counts both Xanax.

V2 includes `valid_until` (at most 120 seconds after generation),
`market_price_checked_at` and `market_price_valid_until` (300-second market
cache life). Missing trustworthy timestamps are null, never replaced with the
list generation time. The current catalog lacks a foreign-price receipt clock,
so `foreign_price_checked_at` is explicitly null. A known market timestamp older
than 300 seconds makes v2 unavailable. Estimates with unknown clocks must be
labeled unknown; a newly generated list is not proof of newly collected prices.

Published departure rows additionally include `source_checked_at` and
`departure_valid_until`, bounded by the publication validity, the 180-second
heartbeat window and the departure deadline. Unverified departures have null
clocks. A client must expire timing independently of price/list expiry and must
not invent confidence probabilities from these status checks. These are clock
validity checks, not calibrated accuracy guarantees.

Use the guarded `deploy/scripts/publish_beanstalk_hot_list.py` procedure for a
later reviewed deployment. It upgrades only the exact recognized legacy handler
or inserts the reviewed route at its original anchor, retaining unrelated VM
customizations. Publish the backend upgrade and then the Beanstalk UI. The new
UI accepts v1 during rollout, clearly labels the pending upgrade, and treats
legacy timing as unverified because v1 does not expose timing expiry.

The original v1 contract below is retained for existing clients.

**Deployment status:** This endpoint is not public until the guarded VM deployment succeeds. GitHub merge alone does not make it live.

## GET endpoint

`https://tornfren.duckdns.org/api/beanstalk-hot-list`

Unauthenticated read-only GET. `Access-Control-Allow-Origin: *` for the public data, `Cache-Control: public, max-age=15`. Returns the current best seven selections as JSON from the same Torn-FREN market data and published first-release forecasts as `/experimental`.

No Torn API key, user account credentials, Beanstalk account data, or privileged API access are used.

## Success schema

```json
{
  "schema": "torn-fren-beanstalk-hot-list-v1",
  "status": "OK",
  "generated_at": "2026-11-13T23:14:05Z",
  "generated_epoch": 1794611645,
  "inventory_slots": 15,
  "flight_profile": "PI + pilot",
  "selling_price_basis": "Torn Item Market (5% fee) or Nikeh fixed NPC payout (0% Item Market fee)",
  "market_value_floor": 15000,
  "category_quotas": {"xanax":1,"plushie":2,"flower":2,"nikeh":2},
  "forecast_feed_status": "LIVE_BETA",
  "picks": [
    {
      "category": "xanax",
      "item_name": "Xanax",
      "country_code": "jap",
      "destination": "Japan",
      "item_key": "jap:Xanax",
      "estimated_round_trip_profit_per_hour": 453532,
      "estimated_profit_per_15_slots": 2252545,
      "selling_method": "item_market",
      "recommended_departure_time": null,
      "recommended_departure_epoch": null,
      "departure_status": "UNVERIFIED"
    }
  ]
}
```

*The JSON above is a partial illustrative sample, not a live response; the actual success response contains exactly seven picks and a real generated timestamp. A complete sample can be obtained via GET after deployment. The sample price figures come from the historical November 13 pricing snapshot, not a current market quote.*

Dates are UTC ISO 8601. A departure time is provided **only** when a currently published recommendation is still within its validity and heartbeat window. `null` means unverified, not "leave now" or a failed model. Do not infer stock on arrival from profitability.

On incomplete, missing, or stale prices, or if the required category quotas cannot be met, the endpoint returns HTTP 503 with a descriptive `status` and `picks: []`, rather than inventing an item or price. Beanstalk should show a "temporarily unavailable" state and link to the full planner.

## Selection contract

Exactly seven items, grouped in this order:

1. Highest theoretical hourly **Xanax**, including UK Xanax.
2. Two highest-profit **plushies**, each from a different country.
3. Two highest-profit **flowers**, from different countries and neither flower sharing either selected plushie country.
4. Two highest-profit **Nikeh NPC** items from different countries.

At least six different country destinations are preferred when possible. Pangolin Scales can qualify only if its theoretical hourly profit becomes the highest among current eligible Nikeh items. These are **dynamic** category-based rankings rather than hardcoded item names.

Other fixed rules: 15 inventory slots, PI + pilot one-way flight times, each trip modeled outbound + return, Item Market price reference minus 5% fee or Nikeh fixed NPC payout without that fee, valid market reference at least $15,000, positive trip profit, and the exclusions for Jaguar Plushie, Orchid, Banana Orchid, and Edelweiss. These exclusions do **not** remove items from Torn-FREN All Items.

Theoretical profit per hour excludes forecast wait, selling delay, unsuccessful inventory loads, and travel incidentals. Nikeh access requires Sports Administration. This endpoint never promotes a research-only forecasting model.

## Beanstalk integration

Jedi should read `picks` directly and render compact rows in the existing drawer; no separate price calculations, live-model imports, or independent exclusions in the Beanstalk codebase. A frontend client can `fetch` the public URL directly with a 30–60 second polling cadence and a small cache; do not poll more often than the endpoint's 15-second server cache. Use `generated_at` to display data freshness, and link to `https://tornfren.duckdns.org/experimental` for full details. On a 503 or network error, do not render cached departure times as current.

Future real bazaar sale-price and liquidity rankings can replace the price basis on the Torn-FREN side without modifying this response shape.

