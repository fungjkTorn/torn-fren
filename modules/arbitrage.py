from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class BazaarListing:
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
class BuyOffer:
    item_name: str
    unit_price: int
    source: str
    buyer_name: str
    buyer_id: Optional[str] = None
    item_id: Optional[str] = None
    max_quantity: Optional[int] = None
    url: Optional[str] = None
    observed_at: Optional[float] = None


@dataclass(frozen=True)
class ArbitrageOpportunity:
    item_name: str
    buyer_name: str
    buyer_source: str
    buyer_price: int
    quantity: int
    total_cost: int
    total_revenue: int
    total_profit: int
    average_buy_price: float
    average_profit_per_item: float
    roi: float
    cheapest_buy_price: int
    highest_accepted_buy_price: int
    seller_count: int
    listing_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def _item_key(item_name: str, item_id: Optional[str]) -> str:
    if item_id:
        return f"id:{item_id}"
    return f"name:{item_name.strip().casefold()}"


def _validate_listing(listing: BazaarListing) -> None:
    if not listing.item_name.strip():
        raise ValueError("Bazaar listing item_name cannot be empty.")
    if listing.unit_price < 0:
        raise ValueError("Bazaar listing unit_price cannot be negative.")
    if listing.quantity <= 0:
        raise ValueError("Bazaar listing quantity must be positive.")


def _validate_offer(offer: BuyOffer) -> None:
    if not offer.item_name.strip():
        raise ValueError("Buy offer item_name cannot be empty.")
    if offer.unit_price < 0:
        raise ValueError("Buy offer unit_price cannot be negative.")
    if offer.max_quantity is not None and offer.max_quantity <= 0:
        raise ValueError("Buy offer max_quantity must be positive when supplied.")


def evaluate_offer(
    listings: Iterable[BazaarListing],
    offer: BuyOffer,
    *,
    min_profit_per_item: int = 20_000,
    min_roi: float = 0.0,
) -> Optional[ArbitrageOpportunity]:
    """
    Evaluate one trader buy offer against all available bazaar listings.

    A listing is only included when every unit from that listing clears BOTH:
      - min_profit_per_item
      - min_roi

    Listings are consumed cheapest-first. This naturally supports buying from
    multiple sellers while keeping the weighted average acquisition price
    internal to the calculation.
    """
    _validate_offer(offer)

    if min_profit_per_item < 0:
        raise ValueError("min_profit_per_item cannot be negative.")
    if min_roi < 0:
        raise ValueError("min_roi cannot be negative.")

    offer_key = _item_key(offer.item_name, offer.item_id)
    candidates = []

    for listing in listings:
        _validate_listing(listing)
        if _item_key(listing.item_name, listing.item_id) != offer_key:
            continue

        unit_profit = offer.unit_price - listing.unit_price
        roi = unit_profit / listing.unit_price if listing.unit_price else float("inf")

        if unit_profit < min_profit_per_item:
            continue
        if roi < min_roi:
            continue

        candidates.append(listing)

    if not candidates:
        return None

    candidates.sort(key=lambda row: (row.unit_price, row.source, row.seller_name or ""))

    remaining = offer.max_quantity
    total_quantity = 0
    total_cost = 0
    accepted_prices = []
    sellers = set()
    accepted_listing_count = 0

    for listing in candidates:
        take = listing.quantity
        if remaining is not None:
            if remaining <= 0:
                break
            take = min(take, remaining)

        if take <= 0:
            continue

        total_quantity += take
        total_cost += take * listing.unit_price
        accepted_prices.append(listing.unit_price)
        sellers.add((listing.source, listing.seller_id or listing.seller_name or "unknown"))
        accepted_listing_count += 1

        if remaining is not None:
            remaining -= take

    if total_quantity <= 0:
        return None

    total_revenue = total_quantity * offer.unit_price
    total_profit = total_revenue - total_cost
    average_buy_price = total_cost / total_quantity
    average_profit_per_item = total_profit / total_quantity
    roi = total_profit / total_cost if total_cost else float("inf")

    return ArbitrageOpportunity(
        item_name=offer.item_name,
        buyer_name=offer.buyer_name,
        buyer_source=offer.source,
        buyer_price=offer.unit_price,
        quantity=total_quantity,
        total_cost=total_cost,
        total_revenue=total_revenue,
        total_profit=total_profit,
        average_buy_price=average_buy_price,
        average_profit_per_item=average_profit_per_item,
        roi=roi,
        cheapest_buy_price=min(accepted_prices),
        highest_accepted_buy_price=max(accepted_prices),
        seller_count=len(sellers),
        listing_count=accepted_listing_count,
    )


def scan_arbitrage(
    listings: Iterable[BazaarListing],
    offers: Iterable[BuyOffer],
    *,
    min_profit_per_item: int = 20_000,
    min_roi: float = 0.0,
    min_quantity: int = 1,
) -> list[ArbitrageOpportunity]:
    """
    Find the strongest opportunity for each item.

    Every buyer is evaluated independently against the same bazaar inventory.
    We then keep the best buyer for that item, ranked by:
      1) total profit
      2) average profit per item
      3) ROI

    This avoids double-counting inventory across multiple buyers in the output.
    """
    if min_quantity <= 0:
        raise ValueError("min_quantity must be positive.")

    listing_rows = list(listings)
    best_by_item: dict[str, ArbitrageOpportunity] = {}

    for offer in offers:
        opportunity = evaluate_offer(
            listing_rows,
            offer,
            min_profit_per_item=min_profit_per_item,
            min_roi=min_roi,
        )
        if opportunity is None or opportunity.quantity < min_quantity:
            continue

        key = _item_key(offer.item_name, offer.item_id)
        current = best_by_item.get(key)

        if current is None:
            best_by_item[key] = opportunity
            continue

        current_rank = (
            current.total_profit,
            current.average_profit_per_item,
            current.roi,
        )
        new_rank = (
            opportunity.total_profit,
            opportunity.average_profit_per_item,
            opportunity.roi,
        )

        if new_rank > current_rank:
            best_by_item[key] = opportunity

    return sorted(
        best_by_item.values(),
        key=lambda row: (
            row.total_profit,
            row.average_profit_per_item,
            row.roi,
        ),
        reverse=True,
    )
