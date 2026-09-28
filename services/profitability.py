"""Global travel profitability helpers.

Profitability v1 intentionally stays player-agnostic.  It assumes one unit of
carrying capacity ("one slot") and PI + pilot travel times.  Personalized
capacity and travel modifiers can multiply/replace these values later without
changing the base calculation.
"""

import os
import threading
import time
from typing import Dict, Iterable, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

MARKET_SALE_FEE_RATE = 0.05
MARKET_VALUE_TTL_SECONDS = 300
MARKET_VALUE_URL = "https://api.torn.com/torn/"

# One-way PI + pilot travel times used by the existing graph UI.
PI_PILOT_FLIGHT_MINUTES = {
    "mex": 17,
    "cay": 23,
    "can": 27,
    "haw": 89,
    "uni": 106,
    "arg": 111,
    "swi": 116,
    "jap": 149,
    "chi": 160,
    "uae": 180,
    "sou": 197,
}

_MARKET_LOCK = threading.RLock()
_MARKET_CACHE = {
    "fetched_at": 0.0,
    "values": {},
    "source_timestamp": None,
    "error": None,
}


def calculate_profitability(
    foreign_price: Optional[float],
    market_price: Optional[float],
    one_way_minutes: Optional[float],
    market_fee_rate: float = MARKET_SALE_FEE_RATE,
):
    """Return normalized travel profitability for one inventory slot."""
    if foreign_price is None or market_price is None or one_way_minutes is None:
        return None

    try:
        foreign_price = float(foreign_price)
        market_price = float(market_price)
        one_way_minutes = float(one_way_minutes)
    except (TypeError, ValueError):
        return None

    if foreign_price <= 0 or market_price <= 0 or one_way_minutes <= 0:
        return None

    net_sale_value = market_price * (1.0 - float(market_fee_rate))
    net_profit = net_sale_value - foreign_price
    round_trip_hours = (one_way_minutes * 2.0) / 60.0
    profit_per_slot_per_hour = net_profit / round_trip_hours
    roi_percent = (net_profit / foreign_price) * 100.0

    return {
        "market_fee_rate": float(market_fee_rate),
        "net_sale_value": round(net_sale_value),
        "net_profit_per_item": round(net_profit),
        "round_trip_minutes": round(one_way_minutes * 2),
        "profit_per_slot_per_hour": round(profit_per_slot_per_hour),
        "roi_percent": round(roi_percent, 2),
    }


def _extract_market_values(payload) -> Dict[int, int]:
    """Normalize Torn v1 `torn/?selections=items` into item_id -> market value."""
    values: Dict[int, int] = {}
    items = (payload or {}).get("items") or {}
    if not isinstance(items, dict):
        return values

    for raw_id, item in items.items():
        if not isinstance(item, dict):
            continue
        raw_value = item.get("market_value")
        try:
            item_id = int(raw_id)
            market_value = int(raw_value)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and market_value > 0:
            values[item_id] = market_value
    return values


def get_market_values(force_refresh: bool = False):
    """Return a cached map of Torn item ids to global market values.

    Torn's all-items selection gives us every market value in one globally
    useful request, avoiding one Item Market API request per travel item.
    Stale cached values remain available if a refresh temporarily fails.
    """
    now = time.time()
    with _MARKET_LOCK:
        age = now - float(_MARKET_CACHE["fetched_at"] or 0)
        if _MARKET_CACHE["values"] and not force_refresh and age < MARKET_VALUE_TTL_SECONDS:
            return dict(_MARKET_CACHE["values"]), {
                "fetched_at": _MARKET_CACHE["fetched_at"],
                "error": _MARKET_CACHE["error"],
                "stale": False,
            }

    api_key = (os.getenv("TORN_API_KEY") or "").strip()
    if not api_key:
        with _MARKET_LOCK:
            return dict(_MARKET_CACHE["values"]), {
                "fetched_at": _MARKET_CACHE["fetched_at"] or None,
                "error": "TORN_API_KEY is not configured",
                "stale": bool(_MARKET_CACHE["values"]),
            }

    try:
        response = requests.get(
            MARKET_VALUE_URL,
            params={"selections": "items", "key": api_key},
            headers={"User-Agent": "torn-fren/1.0 profitability"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        values = _extract_market_values(payload)
        if not values:
            raise RuntimeError("Torn items response did not contain market values")

        fetched_at = time.time()
        with _MARKET_LOCK:
            _MARKET_CACHE.update({
                "fetched_at": fetched_at,
                "values": values,
                "error": None,
            })
        return dict(values), {"fetched_at": fetched_at, "error": None, "stale": False}
    except Exception as exc:
        with _MARKET_LOCK:
            _MARKET_CACHE["error"] = str(exc)
            return dict(_MARKET_CACHE["values"]), {
                "fetched_at": _MARKET_CACHE["fetched_at"] or None,
                "error": str(exc),
                "stale": bool(_MARKET_CACHE["values"]),
            }


def enrich_items_with_profitability(country: str, items: Iterable[dict]):
    """Attach market/profit fields and sort profitable items first."""
    country = (country or "").lower()
    one_way_minutes = PI_PILOT_FLIGHT_MINUTES.get(country)
    market_values, market_meta = get_market_values()

    enriched = []
    for raw in items:
        item = dict(raw)
        item_id = item.get("item_id", item.get("id"))
        foreign_price = item.get("foreign_price", item.get("cost"))
        try:
            market_price = market_values.get(int(item_id)) if item_id is not None else None
        except (TypeError, ValueError):
            market_price = None

        profit = calculate_profitability(foreign_price, market_price, one_way_minutes)
        item["foreign_price"] = foreign_price
        item["market_price"] = market_price
        item["market_price_source"] = "Torn market value" if market_price is not None else None
        item["market_price_fetched_at"] = market_meta.get("fetched_at")
        item["market_price_stale"] = bool(market_meta.get("stale"))
        if profit:
            item.update(profit)
        else:
            item.update({
                "market_fee_rate": MARKET_SALE_FEE_RATE,
                "net_sale_value": None,
                "net_profit_per_item": None,
                "round_trip_minutes": round(one_way_minutes * 2) if one_way_minutes else None,
                "profit_per_slot_per_hour": None,
                "roi_percent": None,
            })
        enriched.append(item)

    # Valid profitability first, best $/slot/hr first. Missing-price items remain
    # selectable and fall back to alphabetical order at the bottom.
    enriched.sort(key=lambda row: (
        row.get("profit_per_slot_per_hour") is None,
        -(row.get("profit_per_slot_per_hour") or 0),
        str(row.get("item_name") or row.get("name") or "").lower(),
    ))
    return enriched, market_meta


def profitability_for_item(country: str, item_state: Optional[dict]):
    if not item_state:
        return None, {"error": "Item state unavailable", "stale": False, "fetched_at": None}
    rows, meta = enrich_items_with_profitability(country, [item_state])
    return (rows[0] if rows else None), meta