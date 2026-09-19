import argparse

from services.prediction_lab import walk_forward_backtest


def fmt(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{sign}{hours}h {minutes}m {secs}s"
    return f"{sign}{minutes}m {secs}s"


def main():
    parser = argparse.ArgumentParser(description="Walk-forward prediction model tester")
    parser.add_argument("country", help="country code, e.g. jap")
    parser.add_argument("item", help="item name, e.g. Xanax")
    parser.add_argument("--min-train", type=int, default=3)
    args = parser.parse_args()

    result = walk_forward_backtest(args.country.lower(), args.item, min_train=args.min_train)

    print(f"\n=== {result['item_name']} / {result['country'].upper()} ===")
    print(f"Behavior class: {result['behavior_class']} ({result['behavior_description']})")
    print(f"Median zero→restock: {fmt(result['median_zero_to_restock_seconds'])}")
    print(f"Median stock lifetime: {fmt(result['median_stock_lifetime_seconds'])}")
    print(f"Approx full cycle: {fmt(result['estimated_full_cycle_seconds'])}")
    print(f"Valid depletion waits: {result['valid_wait_samples']} | excluded: {result['excluded_wait_samples']}")
    print(f"Valid restock intervals: {result['valid_restock_interval_samples']} | excluded: {result['excluded_restock_interval_samples']}")
    print(f"Provider bounces suppressed: {result['provider_bounces_suppressed']}")

    if not result["models"]:
        print("\nNot enough valid historical samples for walk-forward testing yet.")
        return

    print("\nWalk-forward model results (no hindsight):")
    print(f"{'model':<36} {'n':>4} {'med err':>10} {'mean err':>10} {'p90 err':>10} {'hit':>8} {'med window':>12} {'bias':>10}")
    print("-" * 118)
    for model in result["models"]:
        hit = "—" if model.window_hit_rate is None else f"{model.window_hit_rate * 100:5.1f}%"
        print(
            f"{model.name:<36} {model.predictions:>4} "
            f"{fmt(model.median_absolute_error_seconds):>10} "
            f"{fmt(model.mean_absolute_error_seconds):>10} "
            f"{fmt(model.p90_absolute_error_seconds):>10} "
            f"{hit:>8} "
            f"{fmt(model.median_window_width_seconds):>12} "
            f"{fmt(model.signed_bias_seconds):>10}"
        )


if __name__ == "__main__":
    main()
