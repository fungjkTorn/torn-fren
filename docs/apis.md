# API Research: Travel Data Sources

## TL;DR

- **The official Torn API has no live abroad-stock endpoint.** Confirmed: tools like YATA
  work because client apps (TornTools, Torn PDA) *push* stock data whenever a real player
  lands abroad — it's crowdsourced, not polled from Torn.
- **YATA is the primary crowdsourced source.** **Prometheus** (prombot.co.uk) is a second,
  independent crowdsourced source used as a fallback when YATA is overloaded/down.
- **Current stock is available** (YATA's `/travel/export/`). **Restock prediction is NOT**
  available from any API — every tool that shows an ETA calculated it themselves from
  historical polling. This is the one piece of real engineering in this whole project.
- **TornStats has no travel/market data** — it's a player/faction stats tool.
- **Flight times are static game constants** — hardcode from the Torn Wiki, no API needed.
- **Architecture consequence**: we're not building "a travel command," we're building a
  small data pipeline: raw sources → a source-agnostic `StockProvider` interface → a
  SQLite history store → a prediction/profit engine → Discord as the last, thinnest layer.

---

## 1. Official Torn API

v1 (`api.torn.com/{category}/{id}?selections=...&key=...`) and a newer v2 (Swagger UI at
torn.com/swagger.php). Auth via `key=` query param. Rate limit: 100 req/min per user, 1,000/min
per IP, ~30s server-side cache per unique call.

| Data | Endpoint | Notes |
|---|---|---|
| Item base info | `/torn/{id}?selections=items` | `buy_price`, `sell_price`, `market_value`, `circulation`. `market_value` updates ~once/day. |
| Item market | `/market/{id}?selections=itemmarket` | Real-time-ish player listings. |
| Bazaar prices | `/market/{id}?selections=bazaar` | Individual bazaar listings. |
| Torn stock market | `/torn/{id}?selections=stocks` | Financial stock market (WSB/TCB) — **not** abroad item stock, easy to confuse by name. |

**Does not provide**: abroad shop stock, restock timing, travel times.

---

## 2. YATA API

**Base URL**: `https://yata.yt/api/v1/`
**Key endpoint**: `GET /api/v1/travel/export/` — public, no key required to read.

```json
{
  "stocks": {
    "mex": {
      "update": 1735689600,
      "stocks": [
        { "id": 180, "name": "Teddy Bear", "quantity": 1860, "cost": 4200 }
      ]
    }
  },
  "timestamp": 1735689600
}
```

Cached until the next crowdsourced `/travel/import/` write for that country — `update` tells
us exactly how stale a given country's numbers are. Poll politely (every 30–60s); hammering
it faster doesn't get fresher data since it's server-cached anyway.

**Provides**: current stock + cost, per country, with staleness signal.
**Does not provide**: history or restock prediction — we build that ourselves.

---

## 3. Prometheus (secondary crowdsourced source)

Website/bot: prombot.co.uk. Same purpose as YATA — crowdsourced current stock — used by
TornTools as an explicit fallback when YATA is overloaded. Confirmed to exist via multiple
community threads; **actual API endpoint/response format not yet confirmed** — needs a direct
look at prombot.co.uk before `PrometheusProvider` can be more than a stub.

---

## 4. TornStats API

Covers spy data, faction stats, employee efficiency, crime pass rates. **No travel, stock, or
market endpoints found.** Not a source for this project.

---

## 5. Data-type → best source matrix

| Data needed | Best source | Reliability | Notes |
|---|---|---|---|
| Current abroad stock | YATA (+ Prometheus as fallback) | Medium — depends on recent player traffic | Check `update` staleness |
| Restock prediction | **Nobody provides this** — we calculate it | — | Needs our own history + confidence model |
| Historical stock | **We build it** — `history_service.py` | — | SQLite, polling every ~30s, forever |
| Market prices | Official Torn API `/market` | High | Real-time, well within rate limits |
| Item base values | Official Torn API `/torn/items` | High, but daily-cached | Fine for baseline math |
| Travel times | Static constants (Torn Wiki) | 100% | Hardcode, no API |

---

## 6. Revised architecture