from services.arbitrage_live import (
    ForeignItem,
    fetch_tornexchange_buy_offers,
    fetch_weav3r_bazaar,
)


def main():
    item = ForeignItem(
        item_id="1502",
        item_name="Basalt Point",
        countries=("Hawaii",),
        abroad_costs=(),
    )

    listings = fetch_weav3r_bazaar(item)
    offers = fetch_tornexchange_buy_offers(item)

    if not listings:
        raise SystemExit("No TornW3B Basalt Point bazaar listings parsed.")
    if not offers:
        raise SystemExit("No Torn Exchange Basalt Point trader offers parsed.")

    cheapest = min(listings, key=lambda row: row.unit_price)
    best = max(offers, key=lambda row: row.unit_price)

    print(
        "LIVE_SMOKE_OK "
        f"bazaar_rows={len(listings)} cheapest={cheapest.unit_price} "
        f"trader_rows={len(offers)} best={best.unit_price} buyer={best.buyer_name}"
    )


if __name__ == "__main__":
    main()
