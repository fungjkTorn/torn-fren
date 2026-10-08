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
    buyer_url: Optional[str]
    item_id: Optional[str]
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
    buy_sources: tuple[str, ...]
    buy_source_quantities: dict[str, int]
    buy_source_costs: dict[str, int]

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
    max_capital: Optional[int] = None,
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
    if max_capital is not None and max_capital <= 0:
        raise ValueError("max_capital must be positive when supplied.")

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
    buy_sources = set()
    buy_source_quantities: dict[str, int] = {}
    buy_source_costs: dict[str, int] = {}

    for listing in candidates:
        take = listing.quantity
        if remaining is not None:
            if remaining <= 0:
                break
            take = min(take, remaining)

        if max_capital is not None:
            affordable = max(0, (max_capital - total_cost) // listing.unit_price) if listing.unit_price else take
            take = min(take, affordable)

        if take <= 0:
            continue

        total_quantity += take
        total_cost += take * listing.unit_price
        accepted_prices.append(listing.unit_price)
        sellers.add((listing.source, listing.seller_id or listing.seller_name or "unknown"))
        accepted_listing_count += 1
        buy_sources.add(listing.source)
        buy_source_quantities[listing.source] = buy_source_quantities.get(listing.source, 0) + take
        buy_source_costs[listing.source] = buy_source_costs.get(listing.source, 0) + (take * listing.unit_price)

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
        buyer_url=offer.url,
        item_id=offer.item_id,
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
        buy_sources=tuple(sorted(buy_sources)),
        buy_source_quantities=dict(sorted(buy_source_quantities.items())),
        buy_source_costs=dict(sorted(buy_source_costs.items())),
    )


def _buyer_key(name: str) -> str:
    return (name or "").strip().casefold()


def build_arbitrage_candidates(
    listings: Iterable[BazaarListing],
    offers: Iterable[BuyOffer],
    *,
    min_profit_per_item: int = 20_000,
    min_roi: float = 0.0,
    min_quantity: int = 1,
    min_total_profit: int = 0,
    max_capital: Optional[int] = None,
    excluded_buyers: Optional[set[str]] = None,
) -> dict[str, list[ArbitrageOpportunity]]:
    """Evaluate every qualifying buyer and return ranked candidates per item."""
    if min_quantity <= 0:
        raise ValueError("min_quantity must be positive.")
    if min_total_profit < 0:
        raise ValueError("min_total_profit cannot be negative.")

    excluded = {_buyer_key(name) for name in (excluded_buyers or set()) if name}
    listing_rows = list(listings)
    listings_by_item: dict[str, list[BazaarListing]] = {}
    for listing in listing_rows:
        _validate_listing(listing)
        key = _item_key(listing.item_name, listing.item_id)
        listings_by_item.setdefault(key, []).append(listing)

    candidates_by_item: dict[str, list[ArbitrageOpportunity]] = {}
    for offer in offers:
        if _buyer_key(offer.buyer_name) in excluded:
            continue

        offer_key = _item_key(offer.item_name, offer.item_id)
        item_listings = listings_by_item.get(offer_key)
        if not item_listings:
            continue

        opportunity = evaluate_offer(
            item_listings,
            offer,
            min_profit_per_item=min_profit_per_item,
            min_roi=min_roi,
            max_capital=max_capital,
        )
        if (
            opportunity is None
            or opportunity.quantity < min_quantity
            or opportunity.total_profit < min_total_profit
        ):
            continue

        candidates_by_item.setdefault(offer_key, []).append(opportunity)

    for rows in candidates_by_item.values():
        rows.sort(
            key=lambda row: (
                row.total_profit,
                row.average_profit_per_item,
                row.roi,
                row.buyer_price,
            ),
            reverse=True,
        )
    return candidates_by_item


def scan_arbitrage(
    listings: Iterable[BazaarListing],
    offers: Iterable[BuyOffer],
    *,
    min_profit_per_item: int = 20_000,
    min_roi: float = 0.0,
    min_quantity: int = 1,
    min_total_profit: int = 0,
    max_capital: Optional[int] = None,
    excluded_buyers: Optional[set[str]] = None,
    max_opportunities_per_buyer: Optional[int] = None,
    diversified: bool = False,
    diversification_tolerance: float = 0.10,
) -> list[ArbitrageOpportunity]:
    """
    Select one buyer per item while supporting exclusions and buyer concentration
    controls.

    With diversified=True, if the highest-profit buyer is already represented,
    a less-used alternate may be selected when it preserves at least
    (1 - diversification_tolerance) of the best candidate's total profit.
    """
    if max_opportunities_per_buyer is not None and max_opportunities_per_buyer <= 0:
        raise ValueError("max_opportunities_per_buyer must be positive when supplied.")
    if not 0 <= diversification_tolerance < 1:
        raise ValueError("diversification_tolerance must be between 0 and 1.")

    candidates_by_item = build_arbitrage_candidates(
        listings,
        offers,
        min_profit_per_item=min_profit_per_item,
        min_roi=min_roi,
        min_quantity=min_quantity,
        min_total_profit=min_total_profit,
        max_capital=max_capital,
        excluded_buyers=excluded_buyers,
    )

    # Process the most valuable items first so a hard buyer cap preserves the
    # strongest opportunities before allocating that buyer to smaller rows.
    item_groups = sorted(
        candidates_by_item.values(),
        key=lambda rows: rows[0].total_profit if rows else 0,
        reverse=True,
    )

    selected: list[ArbitrageOpportunity] = []
    buyer_counts: dict[str, int] = {}

    for candidates in item_groups:
        allowed = []
        for candidate in candidates:
            key = _buyer_key(candidate.buyer_name)
            if (
                max_opportunities_per_buyer is not None
                and buyer_counts.get(key, 0) >= max_opportunities_per_buyer
            ):
                continue
            allowed.append(candidate)

        if not allowed:
            continue

        chosen = allowed[0]

        if diversified and buyer_counts.get(_buyer_key(chosen.buyer_name), 0) > 0:
            floor = chosen.total_profit * (1.0 - diversification_tolerance)
            near_best = [row for row in allowed if row.total_profit >= floor]
            if near_best:
                near_best.sort(
                    key=lambda row: (
                        -buyer_counts.get(_buyer_key(row.buyer_name), 0),
                        row.total_profit,
                        row.average_profit_per_item,
                    ),
                    reverse=True,
                )
                chosen = near_best[0]

        selected.append(chosen)
        key = _buyer_key(chosen.buyer_name)
        buyer_counts[key] = buyer_counts.get(key, 0) + 1

    return sorted(
        selected,
        key=lambda row: (
            row.total_profit,
            row.average_profit_per_item,
            row.roi,
        ),
        reverse=True,
    )
