from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from modules.arbitrage import BazaarListing, BuyOffer, scan_arbitrage
from services.stock_provider import get_travel_export


WEAV3R_ITEM_URL = "https://weav3r.dev/item/{item_id}"
TORNW3B_API_BASE = "https://weav3r.dev/api"
TORN_EXCHANGE_LISTINGS_URL = "https://www.tornexchange.com/listings"
TORN_EXCHANGE_BEST_URL = "https://tornexchange.com/api/best_listing"
TE_MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("ARBITRAGE_TE_REQUEST_INTERVAL", "6.2"))
TE_CACHE_SECONDS = int(os.getenv("ARBITRAGE_TE_CACHE_SECONDS", "1800"))
TE_CACHE_DB = Path(os.getenv("ARBITRAGE_TE_CACHE_DB", "data/arbitrage_cache.db"))
DEFAULT_CACHE_SECONDS = int(os.getenv("ARBITRAGE_CACHE_SECONDS", "900"))
DEFAULT_MAX_WORKERS = max(1, min(int(os.getenv("ARBITRAGE_MAX_WORKERS", "2")), 4))
HTTP_TIMEOUT_SECONDS = float(os.getenv("ARBITRAGE_HTTP_TIMEOUT", "12"))
ENABLE_TORN_EXCHANGE = os.getenv("ARBITRAGE_ENABLE_TORN_EXCHANGE", "1").strip().lower() not in {"0", "false", "no", "off"}
ENABLE_TORN_ITEM_MARKET = os.getenv("ARBITRAGE_ENABLE_TORN_ITEM_MARKET", "1").strip().lower() not in {"0", "false", "no", "off"}
TORN_API_BASE = "https://api.torn.com/v2"
_COUNTRY_NAMES = {
    "mex": "Mexico",
    "cay": "Cayman Islands",
    "can": "Canada",
    "haw": "Hawaii",
    "uni": "United Kingdom",
    "arg": "Argentina",
    "swi": "Switzerland",
    "jap": "Japan",
    "chi": "China",
    "uae": "United Arab Emirates",
    "sou": "South Africa",
}

_MONEY_RE = re.compile(r"\$\s*([\d,]+)")
_PLAYER_ID_RE = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class ForeignItem:
    item_id: str
    item_name: str
    countries: tuple[str, ...]
    abroad_costs: tuple[int, ...]

    @property
    def weav3r_url(self) -> str:
        return WEAV3R_ITEM_URL.format(item_id=self.item_id)


_cache_lock = threading.Lock()
_te_rate_lock = threading.Lock()
_te_last_call_monotonic = 0.0
_snapshot_cache = {
    "timestamp": 0.0,
    "catalog": [],
    "listings": [],
    "offers": [],
    "errors": [],
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "torn-fren-arbitrage/0.1 (+https://github.com/fungjkTorn/torn-fren)",
            "Accept": "text/html,application/xhtml+xml",
        }
    )
    return s


def _money(text: str) -> Optional[int]:
    match = _MONEY_RE.search(text or "")
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def get_foreign_item_catalog() -> list[ForeignItem]:
    """
    Build the scanner universe dynamically from YATA/Prometheus travel stock.

    This deliberately limits arbitrage v0 to items that can actually be bought
    overseas. If a new foreign item is added to the travel export, it joins the
    scanner without a code change.
    """
    export = get_travel_export() or {}
    stocks = export.get("stocks") or {}

    by_item: dict[str, dict] = {}

    for country_code, country_data in stocks.items():
        rows = (country_data or {}).get("stocks") or []
        for row in rows:
            item_id = str(row.get("id") or "").strip()
            item_name = str(row.get("name") or "").strip()
            if not item_id or not item_name:
                continue

            try:
                cost = int(row.get("cost") or 0)
            except (TypeError, ValueError):
                cost = 0

            entry = by_item.setdefault(
                item_id,
                {
                    "item_id": item_id,
                    "item_name": item_name,
                    "countries": set(),
                    "abroad_costs": set(),
                },
            )
            entry["countries"].add(_COUNTRY_NAMES.get(country_code, country_code.upper()))
            if cost > 0:
                entry["abroad_costs"].add(cost)

    return sorted(
        [
            ForeignItem(
                item_id=value["item_id"],
                item_name=value["item_name"],
                countries=tuple(sorted(value["countries"])),
                abroad_costs=tuple(sorted(value["abroad_costs"])),
            )
            for value in by_item.values()
        ],
        key=lambda row: row.item_name.casefold(),
    )


def parse_weav3r_bazaar_html(
    html: str,
    *,
    item_id: str,
    item_name: str,
    observed_at: Optional[float] = None,
) -> list[BazaarListing]:
    """
    Parse TornW3B's public item-page bazaar table.

    The parser keys off semantic table columns instead of CSS class names so a
    cosmetic site redesign is less likely to break it.
    """
    soup = BeautifulSoup(html, "html.parser")
    observed_at = observed_at or time.time()
    rows: list[BazaarListing] = []
    seen = set()

    for table in soup.find_all("table"):
        headers = [
            cell.get_text(" ", strip=True).casefold()
            for cell in table.find_all("th")
        ]
        header_text = " ".join(headers)
        if not ("seller" in header_text and "quantity" in header_text and "price" in header_text):
            continue

        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue

            seller_text = cells[0].get_text(" ", strip=True)
            quantity_text = cells[1].get_text(" ", strip=True)
            price_text = cells[2].get_text(" ", strip=True)

            try:
                quantity = int(re.sub(r"[^0-9]", "", quantity_text))
            except ValueError:
                continue

            price = _money(price_text)
            if not price or quantity <= 0:
                continue

            seller_link = cells[0].find("a", href=True)
            seller_url = urljoin("https://www.torn.com/", seller_link["href"]) if seller_link else None
            player_match = _PLAYER_ID_RE.search(seller_text)
            seller_id = player_match.group(1) if player_match else None
            seller_name = _PLAYER_ID_RE.sub("", seller_text).strip() or None

            key = (seller_id or seller_name, price, quantity)
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                BazaarListing(
                    item_name=item_name,
                    item_id=item_id,
                    unit_price=price,
                    quantity=quantity,
                    source="tornw3b_bazaar",
                    seller_name=seller_name,
                    seller_id=seller_id,
                    url=seller_url,
                    observed_at=observed_at,
                )
            )

    return rows


def _unix_or_now(value) -> float:
    try:
        parsed = float(value)
        return parsed if parsed > 0 else time.time()
    except (TypeError, ValueError):
        return time.time()


def fetch_tornw3b_bazaar(
    item: ForeignItem,
    *,
    session: Optional[requests.Session] = None,
    limit: int = 100,
) -> list[BazaarListing]:
    """
    Fetch TornW3B's supported marketplace JSON feed.

    TornW3B's own Bazaars-in-Item-Market userscript calls:
      GET /api/marketplace/{item_id}?limit=...
    and maps player_id/player_name/quantity/price/last_checked from listings.

    Using this API avoids scraping the human-facing item page, which can be
    Cloudflare-protected on server/cloud IPs.
    """
    session = session or _session()
    response = session.get(
        f"{TORNW3B_API_BASE}/marketplace/{item.item_id}",
        params={"limit": max(1, min(int(limit), 100))},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    rows: list[BazaarListing] = []
    for listing in data.get("listings") or []:
        try:
            player_id = str(listing.get("player_id") or "").strip()
            price = int(listing.get("price") or 0)
            quantity = int(listing.get("quantity") or 0)
        except (TypeError, ValueError):
            continue

        if not player_id or price <= 0 or quantity <= 0:
            continue

        rows.append(
            BazaarListing(
                item_name=item.item_name,
                item_id=item.item_id,
                unit_price=price,
                quantity=quantity,
                source="tornw3b_bazaar",
                seller_name=listing.get("player_name") or None,
                seller_id=player_id,
                url=f"https://www.torn.com/profiles.php?XID={player_id}",
                observed_at=_unix_or_now(
                    listing.get("last_checked") or listing.get("content_updated")
                ),
            )
        )

    return rows


def fetch_tornw3b_buy_offers(
    item: ForeignItem,
    *,
    session: Optional[requests.Session] = None,
    limit: int = 100,
    traded_within_hours: Optional[int] = 168,
) -> list[BuyOffer]:
    """
    Fetch TornW3B trader buy offers from its supported marketplace trader feed.

    The official userscript supports sort=price and tradedWithinHours. We ask
    for highest-price candidates and still sort locally before evaluation.
    """
    session = session or _session()
    params = {
        "limit": max(1, min(int(limit), 100)),
        "sort": "price",
    }
    if traded_within_hours is not None:
        params["tradedWithinHours"] = max(1, min(int(traded_within_hours), 168))

    response = session.get(
        f"{TORNW3B_API_BASE}/marketplace/{item.item_id}/traders",
        params=params,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    generated_at = _unix_or_now(data.get("generated_at"))
    offers: list[BuyOffer] = []

    for trader in data.get("traders") or []:
        try:
            player_id = str(trader.get("player_id") or "").strip()
            price = int(trader.get("price") or 0)
        except (TypeError, ValueError):
            continue

        player_name = str(trader.get("player_name") or "").strip()
        if not player_id or not player_name or price <= 0:
            continue

        offers.append(
            BuyOffer(
                item_name=item.item_name,
                item_id=item.item_id,
                unit_price=price,
                source="tornw3b_trader",
                buyer_name=player_name,
                buyer_id=player_id,
                url=f"https://weav3r.dev/pricelist/{player_id}",
                observed_at=generated_at,
            )
        )

    return sorted(offers, key=lambda row: row.unit_price, reverse=True)


# Kept as an alias so older callers/tests do not break while the branch evolves.
fetch_weav3r_bazaar = fetch_tornw3b_bazaar


def _candidate_card(anchor):
    node = anchor
    for _ in range(7):
        if node is None:
            return None
        text = node.get_text(" ", strip=True)
        if "$" in text and ("Price List" in text or "Trade Now" in text):
            return node
        node = node.parent
    return None


def parse_tornexchange_listings_html(
    html: str,
    *,
    item_id: str,
    item_name: str,
    observed_at: Optional[float] = None,
) -> list[BuyOffer]:
    """
    Parse a Torn Exchange search result page.

    Torn Exchange is card-based rather than a stable data table. We identify
    result cards from their Price List links, then extract the effective price,
    trader identity, and trader pricelist URL from that card.
    """
    soup = BeautifulSoup(html, "html.parser")
    observed_at = observed_at or time.time()
    offers: list[BuyOffer] = []
    seen = set()
    item_cf = item_name.casefold()

    for price_link in soup.find_all("a", href=True):
        href = str(price_link.get("href") or "")
        link_text = price_link.get_text(" ", strip=True).casefold()
        if "/prices/" not in href and "price list" not in link_text:
            continue

        card = _candidate_card(price_link)
        if card is None:
            continue

        text = card.get_text(" ", strip=True)
        if item_cf not in text.casefold():
            continue

        price = _money(text)
        if not price:
            continue

        price_url = urljoin("https://www.tornexchange.com/", href)

        trader_name = None
        trader_id = None

        # Prefer a visible trader link containing the standard [player id] label.
        for a in card.find_all("a", href=True):
            a_text = a.get_text(" ", strip=True)
            match = _PLAYER_ID_RE.search(a_text)
            if match:
                trader_id = match.group(1)
                trader_name = _PLAYER_ID_RE.sub("", a_text).strip()
                break

        if not trader_name:
            # Some result layouts render the player label outside an anchor.
            for text_node in card.stripped_strings:
                player_match = _PLAYER_ID_RE.search(text_node)
                if player_match:
                    trader_id = player_match.group(1)
                    trader_name = _PLAYER_ID_RE.sub("", text_node).strip()
                    if trader_name:
                        break

        if not trader_name:
            # Pricelist URLs are /prices/<username>/ and are a reliable fallback.
            parts = [p for p in price_url.split("/") if p]
            if "prices" in parts:
                try:
                    trader_name = parts[parts.index("prices") + 1]
                except (ValueError, IndexError):
                    pass

        if not trader_name:
            continue

        key = (trader_id or trader_name.casefold(), price)
        if key in seen:
            continue
        seen.add(key)

        offers.append(
            BuyOffer(
                item_name=item_name,
                item_id=item_id,
                unit_price=price,
                source="torn_exchange",
                buyer_name=trader_name,
                buyer_id=trader_id,
                url=price_url,
                observed_at=observed_at,
            )
        )

    return sorted(offers, key=lambda row: row.unit_price, reverse=True)


def _te_cache_connection() -> sqlite3.Connection:
    TE_CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(TE_CACHE_DB, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tornexchange_best (
            item_id TEXT PRIMARY KEY,
            item_name TEXT NOT NULL,
            price INTEGER NOT NULL,
            trader TEXT,
            trader_id TEXT,
            fetched_at REAL NOT NULL
        )
        """
    )
    return conn


def _read_te_cache(item: ForeignItem, *, allow_stale: bool = False) -> Optional[list[BuyOffer]]:
    try:
        with _te_cache_connection() as conn:
            row = conn.execute(
                """
                SELECT price, trader, trader_id, fetched_at
                FROM tornexchange_best
                WHERE item_id = ?
                """,
                (item.item_id,),
            ).fetchone()
    except sqlite3.Error:
        return None

    if row is None:
        return None

    price, trader, trader_id, fetched_at = row
    age = time.time() - float(fetched_at or 0)
    if not allow_stale and age > TE_CACHE_SECONDS:
        return None

    if int(price or 0) <= 0 or not trader:
        return []

    trader_slug = quote_plus(str(trader)).replace("+", "%20")
    return [
        BuyOffer(
            item_name=item.item_name,
            item_id=item.item_id,
            unit_price=int(price),
            source="torn_exchange",
            buyer_name=str(trader),
            buyer_id=str(trader_id) if trader_id else None,
            url=f"https://www.tornexchange.com/prices/{trader_slug}/",
            observed_at=float(fetched_at),
        )
    ]


def _write_te_cache(
    item: ForeignItem,
    *,
    price: int,
    trader: Optional[str],
    trader_id: Optional[str],
    fetched_at: float,
) -> None:
    try:
        with _te_cache_connection() as conn:
            conn.execute(
                """
                INSERT INTO tornexchange_best (
                    item_id, item_name, price, trader, trader_id, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    item_name = excluded.item_name,
                    price = excluded.price,
                    trader = excluded.trader,
                    trader_id = excluded.trader_id,
                    fetched_at = excluded.fetched_at
                """,
                (
                    item.item_id,
                    item.item_name,
                    int(price),
                    trader,
                    trader_id,
                    float(fetched_at),
                ),
            )
    except sqlite3.Error:
        pass


def _wait_for_tornexchange_slot() -> None:
    """
    Torn Exchange's public best-listing API is documented by community scripts
    as a maximum of 10 calls/minute. Serialize calls at a 6.2 second interval
    to stay just under that ceiling even when the foreign scan uses workers.
    """
    global _te_last_call_monotonic

    with _te_rate_lock:
        now = time.monotonic()
        wait = TE_MIN_REQUEST_INTERVAL_SECONDS - (now - _te_last_call_monotonic)
        if wait > 0:
            time.sleep(wait)
        _te_last_call_monotonic = time.monotonic()


def fetch_tornexchange_buy_offers(
    item: ForeignItem,
    *,
    session: Optional[requests.Session] = None,
    force: bool = False,
) -> list[BuyOffer]:
    """
    Fetch Torn Exchange's best active trader for one item using its public API.

    Response fields used by existing Torn community scripts include:
      price, trader, trader_id, item, te_price, vote.
    """
    if not force:
        cached = _read_te_cache(item)
        if cached is not None:
            return cached

    session = session or _session()
    _wait_for_tornexchange_slot()

    response = session.get(
        TORN_EXCHANGE_BEST_URL,
        params={"item_id": item.item_id},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()

    fetched_at = time.time()
    if payload.get("status") != "success" or not payload.get("data"):
        _write_te_cache(
            item,
            price=0,
            trader=None,
            trader_id=None,
            fetched_at=fetched_at,
        )
        return []

    data = payload["data"]
    try:
        price = int(round(float(data.get("price") or 0)))
    except (TypeError, ValueError):
        return []

    trader_name = str(data.get("trader") or "").strip()
    trader_id = str(data.get("trader_id") or "").strip() or None

    if price <= 0 or not trader_name:
        _write_te_cache(
            item,
            price=0,
            trader=None,
            trader_id=None,
            fetched_at=fetched_at,
        )
        return []

    _write_te_cache(
        item,
        price=price,
        trader=trader_name,
        trader_id=trader_id,
        fetched_at=fetched_at,
    )

    # Torn Exchange usernames map directly to public /prices/<name>/ pages.
    trader_slug = quote_plus(trader_name).replace("+", "%20")
    trader_url = f"https://www.tornexchange.com/prices/{trader_slug}/"

    return [
        BuyOffer(
            item_name=item.item_name,
            item_id=item.item_id,
            unit_price=price,
            source="torn_exchange",
            buyer_name=trader_name,
            buyer_id=trader_id,
            url=trader_url,
            observed_at=fetched_at,
        )
    ]


def fetch_torn_item_market(
    item: ForeignItem,
    *,
    session: Optional[requests.Session] = None,
) -> list[BazaarListing]:
    """
    Pull the first page of official Torn item-market listings for one foreign
    item. Torn returns the cheapest listings first, so page one is sufficient
    for the initial arbitrage pass without burning API calls.
    """
    api_key = (os.getenv("TORN_API_KEY") or "").strip()
    if not api_key:
        return []

    session = session or _session()
    response = session.get(
        f"{TORN_API_BASE}/market/{item.item_id}/itemmarket",
        params={"offset": 0},
        headers={"Authorization": f"ApiKey {api_key}", "accept": "application/json"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise RuntimeError(str(data["error"]))

    market = data.get("itemmarket") or {}
    rows = []
    observed_at = time.time()

    for listing in market.get("listings") or []:
        try:
            price = int(listing.get("price") or 0)
            quantity = int(listing.get("amount") or 0)
        except (TypeError, ValueError):
            continue

        if price <= 0 or quantity <= 0:
            continue

        rows.append(
            BazaarListing(
                item_name=item.item_name,
                item_id=item.item_id,
                unit_price=price,
                quantity=quantity,
                source="torn_item_market",
                seller_name="Item Market",
                seller_id=None,
                url=None,
                observed_at=observed_at,
            )
        )

    return rows


def _collect_foreign_item_market(catalog: list[ForeignItem]) -> tuple[list[BazaarListing], list[dict]]:
    """
    Check the official Torn item market only for the same foreign-item catalog
    used by this scanner. This deliberately avoids scanning Torn's full item
    universe.
    """
    listings = []
    errors = []

    if not ENABLE_TORN_ITEM_MARKET or not (os.getenv("TORN_API_KEY") or "").strip():
        return listings, errors

    session = _session()

    for item in catalog:
        try:
            listings.extend(fetch_torn_item_market(item, session=session))
        except Exception as exc:
            errors.append(
                {
                    "item": item.item_name,
                    "source": "torn_item_market",
                    "error": str(exc),
                }
            )

        # Stay comfortably below Torn's per-minute API ceiling.
        time.sleep(1.0)

    return listings, errors


def _refresh_snapshot(*, force: bool = False) -> dict:
    catalog = get_foreign_item_catalog()
    listings: list[BazaarListing] = []
    offers: list[BuyOffer] = []
    errors: list[dict] = []

    def collect(item: ForeignItem):
        local_session = _session()
        item_listings = []
        item_offers = []
        item_errors = []

        try:
            item_listings.extend(fetch_tornw3b_bazaar(item, session=local_session))
        except Exception as exc:
            item_errors.append(
                {
                    "item": item.item_name,
                    "source": "tornw3b_bazaar",
                    "error": str(exc),
                }
            )

        try:
            item_offers.extend(fetch_tornw3b_buy_offers(item, session=local_session))
        except Exception as exc:
            item_errors.append(
                {
                    "item": item.item_name,
                    "source": "tornw3b_trader",
                    "error": str(exc),
                }
            )

        if ENABLE_TORN_EXCHANGE:
            try:
                item_offers.extend(fetch_tornexchange_buy_offers(item, session=local_session, force=force))
            except Exception as exc:
                item_errors.append(
                    {
                        "item": item.item_name,
                        "source": "torn_exchange",
                        "error": str(exc),
                    }
                )

        return item_listings, item_offers, item_errors

    with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as executor:
        futures = {executor.submit(collect, item): item for item in catalog}
        for future in as_completed(futures):
            item_listings, item_offers, item_errors = future.result()
            listings.extend(item_listings)
            offers.extend(item_offers)
            errors.extend(item_errors)

    market_listings, market_errors = _collect_foreign_item_market(catalog)
    listings.extend(market_listings)
    errors.extend(market_errors)

    snapshot = {
        "timestamp": time.time(),
        "catalog": catalog,
        "listings": listings,
        "offers": offers,
        "errors": errors,
    }

    with _cache_lock:
        _snapshot_cache.clear()
        _snapshot_cache.update(snapshot)

    return snapshot


def get_source_snapshot(*, force: bool = False) -> dict:
    with _cache_lock:
        age = time.time() - float(_snapshot_cache.get("timestamp") or 0)
        has_data = bool(_snapshot_cache.get("catalog"))
        if not force and has_data and age < DEFAULT_CACHE_SECONDS:
            return {
                "timestamp": _snapshot_cache["timestamp"],
                "catalog": list(_snapshot_cache["catalog"]),
                "listings": list(_snapshot_cache["listings"]),
                "offers": list(_snapshot_cache["offers"]),
                "errors": list(_snapshot_cache["errors"]),
            }

    return _refresh_snapshot(force=force)


def build_arbitrage_report(
    *,
    min_profit_per_item: int = 20_000,
    min_roi: float = 0.0,
    min_quantity: int = 1,
    force: bool = False,
) -> dict:
    snapshot = get_source_snapshot(force=force)

    opportunities = scan_arbitrage(
        snapshot["listings"],
        snapshot["offers"],
        min_profit_per_item=min_profit_per_item,
        min_roi=min_roi,
        min_quantity=min_quantity,
    )

    catalog_by_id = {item.item_id: item for item in snapshot["catalog"]}
    output = []

    for opportunity in opportunities:
        row = opportunity.to_dict()
        foreign_item = catalog_by_id.get(str(opportunity.item_id))
        row["countries"] = list(foreign_item.countries) if foreign_item else []
        row["abroad_costs"] = list(foreign_item.abroad_costs) if foreign_item else []
        row["buy_url"] = foreign_item.weav3r_url if foreign_item else None
        output.append(row)

    return {
        "generated_at": snapshot["timestamp"],
        "cache_seconds": DEFAULT_CACHE_SECONDS,
        "scope": "foreign_items_only",
        "min_profit_per_item": min_profit_per_item,
        "min_roi": min_roi,
        "min_quantity": min_quantity,
        "catalog_count": len(snapshot["catalog"]),
        "listing_count": len(snapshot["listings"]),
        "offer_count": len(snapshot["offers"]),
        "opportunity_count": len(output),
        "errors": snapshot["errors"],
        "opportunities": output,
    }
