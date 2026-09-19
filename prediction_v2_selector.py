import argparse

from services.prediction_v2_selector import select_prediction_v2_model


def fmt_duration(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{sign}{h}h {m}m {s}s"
    if m:
        return f"{sign}{m}m {s}s"
    return f"{sign}{s}s"


def pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def main():
    parser = argparse.ArgumentParser(description="Inspect Prediction v2 model selection.")
    parser.add_argument("country")
    parser.add_argument("item_name")
    args = parser.parse_args()

    result = select_prediction_v2_model(args.country, args.item_name)
    selected = result["selected_model"]

    print(f"=== Prediction v2 selector: {result['item_name']} / {result['country']} ===")
    print(f"Behavior class: {result['behavior_class']}")
    print(f"Qualified history samples: {result['history_samples']}")
    print(f"Selection tier: {result['selection_tier'].upper()}")
    print(f"Median stock lifetime: {fmt_duration(result['median_stock_lifetime_seconds'])}")
    print()
    print("SELECTED")
    print(f"  model: {selected['name']}")
    print(f"  walk-forward predictions: {selected['predictions']}")
    print(f"  median error: {fmt_duration(selected['median_error_seconds'])}")
    print(f"  p90 error: {fmt_duration(selected['p90_error_seconds'])}")
    print(f"  p90 / lifetime: {pct(selected['p90_to_lifetime_ratio'])}")
    print(f"  p90 < lifetime: {selected['p90_within_stock_lifetime']}")
    print(f"  reason: {result['reason']}")
    print()
    print("CANDIDATES")
    print(f"{'model':30} {'tier':12} {'n':>4} {'med':>10} {'p90':>10} {'p90/life':>10}")
    print("-" * 84)
    for c in sorted(
        result["candidates"],
        key=lambda x: (
            9e99 if x["reliability_score"] is None else x["reliability_score"],
            x["name"],
        ),
    ):
        print(
            f"{c['name'][:30]:30} "
            f"{c['tier']:12} "
            f"{c['predictions']:4d} "
            f"{fmt_duration(c['median_error_seconds']):>10} "
            f"{fmt_duration(c['p90_error_seconds']):>10} "
            f"{pct(c['p90_to_lifetime_ratio']):>10}"
        )


if __name__ == "__main__":
    main()
