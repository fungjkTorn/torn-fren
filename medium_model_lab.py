import argparse
from services.medium_model_lab import analyze_advanced_item


def fmt(seconds):
    if seconds is None:
        return "—"
    sign = "-" if seconds < 0 else ""
    seconds = abs(int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{sign}{h}h {m}m {s}s"
    if m:
        return f"{sign}{m}m {s}s"
    return f"{sign}{s}s"


def main():
    parser = argparse.ArgumentParser(description="Advanced walk-forward model lab for short/medium Torn foreign items")
    parser.add_argument("country")
    parser.add_argument("item", nargs="+")
    parser.add_argument("--min-train", type=int, default=15)
    args = parser.parse_args()
    item = " ".join(args.item)
    result = analyze_advanced_item(args.country.lower(), item, min_train=args.min_train)

    print(f"=== {result['item_name']} / {result['country'].upper()} ===")
    print(f"Behavior class: {result['behavior_class']}")
    print(f"Qualified waits: {result['samples']}")
    print(f"Median zero->restock: {fmt(result['median_wait_seconds'])}")
    print(f"Provider bounces suppressed: {result['provider_bounces_suppressed']}")
    print("\n=== Advanced walk-forward model tournament ===")
    if not result["models"]:
        print("Not enough history yet.")
        return
    print(f"{'model':30} {'n':>4} {'med err':>10} {'mean err':>10} {'p90 err':>10} {'bias':>10}")
    for m in result["models"]:
        print(f"{m.name:30} {m.predictions:>4} {fmt(m.median_absolute_error_seconds):>10} {fmt(m.mean_absolute_error_seconds):>10} {fmt(m.p90_absolute_error_seconds):>10} {fmt(m.signed_bias_seconds):>10}")

    baseline = next((m for m in result['models'] if m.name == 'baseline_all_median'), None)
    winner = result['models'][0]
    print("\n=== Readout ===")
    print(f"Current winner: {winner.name} | median error {fmt(winner.median_absolute_error_seconds)} | p90 {fmt(winner.p90_absolute_error_seconds)}")
    if baseline and winner.name != baseline.name:
        improvement = 100 * (baseline.median_absolute_error_seconds - winner.median_absolute_error_seconds) / baseline.median_absolute_error_seconds
        print(f"Median-error improvement vs baseline: {improvement:.1f}%")
    print("Promotion rule: prefer a new model only when the median improvement is meaningful and p90 does not get materially worse.")


if __name__ == "__main__":
    main()
