import argparse
import json

from services.arbitrage_live import build_arbitrage_report


def main():
    parser = argparse.ArgumentParser(
        description="Scan foreign-item bazaar/item-market listings against trader buy prices."
    )
    parser.add_argument("--min-profit", type=int, default=20_000)
    parser.add_argument("--min-roi", type=float, default=0.0, help="Decimal ROI, e.g. 0.05 for 5%%")
    parser.add_argument("--min-quantity", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_arbitrage_report(
        min_profit_per_item=max(0, args.min_profit),
        min_roi=max(0.0, args.min_roi),
        min_quantity=max(1, args.min_quantity),
        force=args.force,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return

    print(
        f"Foreign catalog: {report['catalog_count']} | "
        f"Listings: {report['listing_count']} | "
        f"Trader bids: {report['offer_count']} | "
        f"Opportunities: {report['opportunity_count']}"
    )
    print("-" * 118)
    print(
        f"{'Item':28} {'Avg buy':>12} {'Trader':18} {'Sell':>12} "
        f"{'Qty':>7} {'P/item':>12} {'ROI':>8} {'Total profit':>14}"
    )
    print("-" * 118)

    for row in report["opportunities"]:
        avg_buy = "$" + f"{row['average_buy_price']:,.0f}"
        sell = "$" + f"{row['buyer_price']:,}"
        per_item = "$" + f"{row['average_profit_per_item']:,.0f}"
        total = "$" + f"{row['total_profit']:,.0f}"
        print(
            f"{row['item_name'][:28]:28} "
            f"{avg_buy:>12} "
            f"{row['buyer_name'][:18]:18} "
            f"{sell:>12} "
            f"{row['quantity']:>7,} "
            f"{per_item:>12} "
            f"{row['roi'] * 100:>7.1f}% "
            f"{total:>14}"
        )
        if row.get("buyer_url"):
            print(f"  trader: {row['buyer_url']}")
        if row.get("buy_url"):
            print(f"  buy:    {row['buy_url']}")

    errors = report.get("errors") or []
    if errors:
        print("\nSource errors:")
        for error in errors:
            print(f"- {error.get('item')} / {error.get('source')}: {error.get('error')}")


if __name__ == "__main__":
    main()
