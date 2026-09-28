from modules.arbitrage import scan_arbitrage
from services.arbitrage_live import (
    ForeignItem,
    fetch_tornexchange_buy_offers,
    fetch_tornw3b_bazaar,
    fetch_tornw3b_buy_offers,
)


def main():
    item = ForeignItem(
        item_id="1502",
        item_name="Basalt Point",
        countries=("Hawaii",),
        abroad_costs=(),
    )

    listings = fetch_tornw3b_bazaar(item)
    w3b_offers = fetch_tornw3b_buy_offers(item)
    exchange_offers = fetch_tornexchange_buy_offers(item)

    if not listings:
        raise SystemExit("No TornW3B Basalt Point bazaar listings returned.")
    if not w3b_offers:
        raise SystemExit("No TornW3B Basalt Point trader offers returned.")
    if not exchange_offers:
        raise SystemExit("No Torn Exchange Basalt Point trader offers parsed.")

    cheapest = min(listings, key=lambda row: row.unit_price)
    best_w3b = max(w3b_offers, key=lambda row: row.unit_price)
    best_exchange = max(exchange_offers, key=lambda row: row.unit_price)

    opportunities = scan_arbitrage(
        listings,
        [*w3b_offers, *exchange_offers],
        min_profit_per_item=20_000,
    )
    if not opportunities:
        raise SystemExit("Live Basalt data did not produce the expected $20k+ opportunity.")

    opportunity = opportunities[0]

    print(
        "LIVE_SMOKE_OK "
        f"bazaar_rows={len(listings)} cheapest={cheapest.unit_price} "
        f"w3b_traders={len(w3b_offers)} w3b_best={best_w3b.unit_price} "
        f"exchange_traders={len(exchange_offers)} exchange_best={best_exchange.unit_price} "
        f"arb_qty={opportunity.quantity} avg_buy={opportunity.average_buy_price:.0f} "
        f"buyer={opportunity.buyer_name} sell={opportunity.buyer_price} "
        f"profit={opportunity.total_profit:.0f}"
    )


if __name__ == "__main__":
    main()
