from services.arbitrage_live import build_arbitrage_report


def main():
    report = build_arbitrage_report(
        min_profit_per_item=20_000,
        min_roi=0.0,
        min_quantity=1,
        force=True,
    )

    print(
        "FULL_FOREIGN_SCAN "
        f"catalog={report['catalog_count']} "
        f"listings={report['listing_count']} "
        f"offers={report['offer_count']} "
        f"opportunities={report['opportunity_count']} "
        f"errors={len(report.get('errors') or [])}"
    )

    for row in report["opportunities"][:20]:
        print(
            "OPPORTUNITY "
            f"item={row['item_name']!r} "
            f"avg_buy={row['average_buy_price']:.0f} "
            f"sell={row['buyer_price']} "
            f"qty={row['quantity']} "
            f"profit_each={row['average_profit_per_item']:.0f} "
            f"roi={row['roi']:.4f} "
            f"total_profit={row['total_profit']:.0f} "
            f"buyer={row['buyer_name']!r} "
            f"buyer_source={row['buyer_source']!r}"
        )

    for error in report.get("errors") or []:
        print(
            "SOURCE_ERROR "
            f"item={error.get('item')!r} "
            f"source={error.get('source')!r} "
            f"error={error.get('error')!r}"
        )


if __name__ == "__main__":
    main()
