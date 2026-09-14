
**Key design rule**: `TravelService` (and everything above it) only ever talks to the
`StockProvider` interface — never to YATA or Prometheus by name. Swapping, adding, or
falling back between sources should never require touching travel logic.

## Revised roadmap

- **Sprint 3 — Data Collection**: `StockProvider` interface, `YataProvider`,
  `PrometheusProvider` stub, SQLite `history_service.py`, standalone poller.
- **Sprint 4 — Intelligence**: profit calculations, restock/sellout detection, confidence
  scoring, predictions built on accumulated history.
- **Sprint 5 — User Experience**: `/travel best`, `/travel leave`, `/travel country`,
  alerts, embeds. Discord is last on purpose — it's the thinnest layer, not the product.

## Open follow-ups
- [ ] Confirm Prometheus's real API endpoint/response shape at prombot.co.uk.
- [ ] Confirm YATA's actual rate-limit policy (nothing formally published — 30–60s polling assumed safe).
- [ ] Decide whether Torn Fren should eventually POST to YATA's `/travel/import/` to contribute data back.