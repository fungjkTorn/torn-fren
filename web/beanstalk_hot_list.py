"""Read-only seven-pick Beanstalk Hot List response from Torn-FREN public data.

The ranking does not touch research, collectors, models, inventory or Beanstalk
accounts. Only already-published departure decisions are eligible for a time.
The Item Market economics/policy is intentionally kept in parity with the
public hotlist-core.js, asserted by the CI contract test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from itertools import combinations, product
import math
import time

SLOTS = 15
MARKET_FLOOR = 15_000
MARKET_FEE = .05
COUNTRIES = {
    "arg": "Argentina", "can": "Canada", "cay": "Cayman Islands",
    "chi": "China", "haw": "Hawaii", "jap": "Japan",
    "mex": "Mexico", "sou": "South Africa", "swi": "Switzerland",
    "uae": "United Arab Emirates", "uni": "United Kingdom",
}
# PI + pilot one-way flight times; source: Torn-FREN hotlist-core.js profile 1.
FLIGHTS_MINUTES = {
    "mex": 17, "cay": 23, "can": 27, "haw": 89, "uni": 106,
    "arg": 111, "swi": 116, "jap": 149, "chi": 160, "uae": 180, "sou": 197,
}
FLOWERS = frozenset({
    "Dahlia", "Crocus", "Orchid", "Heather", "Ceibo Flower", "Edelweiss",
    "Cherry Blossom", "Peony", "Tribulus Omanense", "African Violet",
    "Banana Orchid",
})
NIKEH_PAYOUTS = {
    "can:Bear Gall": 35_000,
    "chi:Pangolin Scales": 205_000,
    "haw:Shark Fin": 66_000,
    "chi:Tiger Bone Powder": 70_000,
    "jap:Whale Meat": 40_000,
}
CANDIDATES = frozenset({
    "arg:Ceibo Flower", "arg:Monkey Plushie",
    "can:Crocus", "can:Wolverine Plushie", "can:Xanax",
    "cay:Banana Orchid", "cay:Stingray Plushie",
    "chi:Panda Plushie", "chi:Peony",
    "haw:Orchid",
    "jap:Cherry Blossom", "jap:Xanax",
    "mex:Dahlia", "mex:Jaguar Plushie",
    "sou:African Violet", "sou:Lion Plushie", "sou:Xanax",
    "swi:Chamois Plushie", "swi:Edelweiss",
    "uae:Camel Plushie", "uae:Tribulus Omanense",
    "uni:Heather", "uni:Nessie Plushie", "uni:Red Fox Plushie",
    "uni:Xanax",
    *NIKEH_PAYOUTS,
})
EXCLUSIONS = frozenset({
    "uni:Xanax", "mex:Jaguar Plushie", "haw:Orchid",
    "cay:Banana Orchid", "swi:Edelweiss",
})
QUOTAS = {"xanax": 1, "plushie": 2, "flower": 2, "nikeh": 2}
SCHEMA = "torn-fren-beanstalk-hot-list-v1"


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _iso(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _category(key):
    name = key.partition(":")[2]
    if key in NIKEH_PAYOUTS:
        return "nikeh"
    if name == "Xanax":
        return "xanax"
    if name.endswith(" Plushie"):
        return "plushie"
    if name in FLOWERS:
        return "flower"
    return None


def _departure(row, now):
    """Mirror the website's PI + pilot published-decision checks, not a forecast."""
    if not isinstance(row, dict):
        return None
    valid = row.get("valid_until_epoch")
    heartbeat = row.get("source_heartbeat_epoch")
    if not isinstance(valid, int) or valid < now:
        return None
    if not isinstance(heartbeat, int) or not 0 <= now-heartbeat <= 180:
        return None
    d = row.get("decision") or {}
    if not isinstance(d, dict) or str(d.get("status", "")).startswith("STALE"):
        return None
    start, deadline = d.get("estimated_departure_epoch"), d.get("estimated_departure_deadline_epoch")
    if not isinstance(start, int) or not isinstance(deadline, int) or deadline < now:
        return None
    if not isinstance(d.get("player_flight_seconds"), (int, float)) or d["player_flight_seconds"] <= 0:
        return None
    departure = max(now, start)
    return departure if departure <= deadline else None


def _candidates(catalog, board, now):
    if not isinstance(catalog, dict) or not isinstance(catalog.get("countries"), list):
        raise ValueError("catalog unavailable")
    if (catalog.get("profitability") or {}).get("market_price_stale") is True:
        raise ValueError("global Item Market reference is stale")

    published = {}
    for row in (board or {}).get("rows", []):
        if isinstance(row, dict) and isinstance(row.get("item_key"), str):
            published[row["item_key"]] = row

    found = {}
    for country in catalog["countries"]:
        if not isinstance(country, dict):
            continue
        code = country.get("country")
        if code not in COUNTRIES:
            continue
        for item in country.get("items") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("item_name")
            if not isinstance(name, str):
                continue
            key = code+":"+name
            if key not in CANDIDATES or key in EXCLUSIONS or item.get("market_price_stale") is True:
                continue
            market = item.get("market_price")
            buy = item.get("foreign_price", item.get("price"))
            if not (_numeric(market) and market >= MARKET_FLOOR and _numeric(buy) and buy > 0):
                continue
            kind = _category(key)
            if kind is None:
                continue
            payout = NIKEH_PAYOUTS.get(key)
            sale = payout if payout is not None else market * (1-MARKET_FEE)
            unit_profit = sale - buy
            if not _numeric(unit_profit) or unit_profit <= 0:
                continue
            hourly = unit_profit * SLOTS * 60 / (2 * FLIGHTS_MINUTES[code])
            if hourly <= 0 or not math.isfinite(hourly):
                continue
            departure = _departure(published.get(key), now)
            found[key] = {
                "category": kind,
                "item_name": name,
                "country_code": code,
                "destination": COUNTRIES[code],
                "item_key": key,
                "estimated_round_trip_profit_per_hour": math.floor(hourly+.5),
                "estimated_profit_per_15_slots": math.floor(unit_profit*SLOTS+.5),
                "selling_method": "nikeh_npc" if payout is not None else "item_market",
                "recommended_departure_time": _iso(departure) if departure is not None else None,
                "recommended_departure_epoch": departure,
                "departure_status": "PUBLISHED_OPPORTUNITY" if departure is not None else "UNVERIFIED",
                "_rank": hourly,
            }
    return list(found.values())


def _select(eligible):
    groups = {category: [] for category in QUOTAS}
    for item in eligible:
        groups[item["category"]].append(item)
    if any(len(groups[category]) < qty for category, qty in QUOTAS.items()):
        return []

    # Pangolin is not a runner-facing recommendation unless it actually is
    # the best Nikeh hourly performer; a high NPC sticker price isn't enough.
    top_nikeh = max(item["_rank"] for item in groups["nikeh"])
    groups["nikeh"] = [
        item for item in groups["nikeh"]
        if item["item_key"] != "chi:Pangolin Scales" or item["_rank"] >= top_nikeh
    ]
    if len(groups["nikeh"]) < 2:
        return []

    # Every category has its reserved slots. A flower may not duplicate either
    # plushie country; the two plushies, flowers and Nikeh items are distinct
    # within each pair. Prefer >=6 unique destinations without sacrificing
    # category quotas or manufacturing replacements.
    options = []
    for plushies in combinations(groups["plushie"], 2):
        p_countries = {i["country_code"] for i in plushies}
        if len(p_countries) != 2:
            continue
        for flowers in combinations(groups["flower"], 2):
            f_countries = {i["country_code"] for i in flowers}
            if len(f_countries) != 2 or f_countries & p_countries:
                continue
            for nikeh in combinations(groups["nikeh"], 2):
                if nikeh[0]["country_code"] == nikeh[1]["country_code"]:
                    continue
                for xanax in groups["xanax"]:
                    selection = (xanax, *plushies, *flowers, *nikeh)
                    diversity = len({i["country_code"] for i in selection})
                    score = sum(i["_rank"] for i in selection)
                    keys = tuple(i["item_key"] for i in selection)
                    options.append((diversity >= 6, score, diversity, keys, selection))
    if not options:
        return []
    if any(option[0] for option in options):
        options = [option for option in options if option[0]]
    # Profitability decides among diversity-compliant combinations. Deterministic
    # tie-breaking keeps the Beanstalk drawer from jumping between equal quotes.
    best = sorted(options, key=lambda x: (-x[1], -x[2], x[3]))[0][4]
    return [{k: v for k, v in item.items() if not k.startswith("_")} for item in best]


def build_hot_list(catalog, board, *, now=None):
    now = int(time.time()) if now is None else int(now)
    picks = _select(_candidates(catalog, board, now))
    result = {
        "schema": SCHEMA,
        "status": "OK" if len(picks) == 7 else "INSUFFICIENT_ELIGIBLE_ITEMS",
        "generated_at": _iso(now),
        "generated_epoch": now,
        "inventory_slots": SLOTS,
        "flight_profile": "PI + pilot",
        "selling_price_basis": "Torn Item Market (5% fee) or Nikeh fixed NPC payout (0% Item Market fee)",
        "market_value_floor": MARKET_FLOOR,
        "category_quotas": QUOTAS,
        "forecast_feed_status": (board or {}).get("status", "UNAVAILABLE"),
        "picks": picks,
    }
    return result


@lru_cache(maxsize=4)
def _public_bucket(bucket):
    # Lazy imports avoid app/module import cycles and reuse the already installed
    # public catalog endpoint and precomputed publisher instead of research code.
    from web.app import api_catalog
    from web.first_release_bridge import read_board
    now = int(time.time())
    catalog = api_catalog()
    try:
        board = read_board(now=now)
    except (OSError, ValueError, KeyError, TypeError):
        board = {"status": "UNAVAILABLE", "rows": []}
    return build_hot_list(catalog, board, now=now)


def public_hot_list():
    return _public_bucket(int(time.time()) // 15)
