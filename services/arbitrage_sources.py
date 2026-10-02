from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Iterable, Optional

from modules.arbitrage import BazaarListing, BuyOffer


@dataclass(frozen=True)
class RawBazaarRow:
    item_name: str
    unit_price: int
    quantity: int
    source: str
    seller_name: Optional[str] = None
    seller_id: Optional[str] = None
    item_id: Optional[str] = None
    url: Optional[str] = None
    observed_at: Optional[float] = None


@dataclass(frozen=True)
class RawBuyOfferRow:
    item_name: str
    unit_price: int
    source: str
    buyer_name: str
    buyer_id: Optional[str] = None
    item_id: Optional[str] = None
    max_quantity: Optional[int] = None
    url: Optional[str] = None
    observed_at: Optional[float] = None


def normalize_bazaar_rows(rows: Iterable[RawBazaarRow]) -> list[BazaarListing]:
    now = time()
    return [
        BazaarListing(
            item_name=row.item_name,
            unit_price=int(row.unit_price),
            quantity=int(row.quantity),
            source=row.source,
            seller_name=row.seller_name,
            seller_id=row.seller_id,
            item_id=row.item_id,
            url=row.url,
            observed_at=row.observed_at if row.observed_at is not None else now,
        )
        for row in rows
    ]


def normalize_buy_offer_rows(rows: Iterable[RawBuyOfferRow]) -> list[BuyOffer]:
    now = time()
    return [
        BuyOffer(
            item_name=row.item_name,
            unit_price=int(row.unit_price),
            source=row.source,
            buyer_name=row.buyer_name,
            buyer_id=row.buyer_id,
            item_id=row.item_id,
            max_quantity=row.max_quantity,
            url=row.url,
            observed_at=row.observed_at if row.observed_at is not None else now,
        )
        for row in rows
    ]
