import argparse
from collections import Counter
from services.medium_model_lab import run_short_medium_tournament


def fmt(seconds):
    if seconds is None:
        return "—"
    seconds = abs(int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def main():
    p = argparse.ArgumentParser(description="Short/medium Prediction-v2 model tournament")
    p.add_argument("--min-samples", type=int, default=15)
    p.add_argument("--min-predictions", type=int, default=12)
    p.add_argument("--min-rows", type=int, default=20)
    args = p.parse_args()

    result = run_short_medium_tournament(args.min_samples, args.min_predictions, args.min_rows)
    print("\n=== Prediction v2: SHORT + MEDIUM model tournament ===")
    print(f"{'item':<28} {'cty':<4} {'class':<8} {'waits':>5} {'winner':<30} {'med err':>9} {'p90':>9}")
    print("-" * 102)
    for item in sorted(result['items'], key=lambda x: (x['behavior_class'], x['country'], x['item_name'])):
        w = item['winner']
        if w:
            name, med, p90 = w.name, fmt(w.median_absolute_error_seconds), fmt(w.p90_absolute_error_seconds)
        else:
            name, med, p90 = "insufficient backtest data", "—", "—"
        print(f"{item['item_name'][:28]:<28} {item['country'].upper():<4} {item['behavior_class']:<8} {item['samples']:>5} {name[:30]:<30} {med:>9} {p90:>9}")

    print("\n=== Winner counts by behavior class ===")
    for behavior in ("short", "medium"):
        print(f"\n{behavior.upper()}")
        wins = Counter(result['class_wins'].get(behavior, {}))
        if not wins:
            print("  no eligible winners yet")
        for name, count in wins.most_common():
            print(f"  {name:<32} {count}")

    print("\nUse this to decide Prediction v2 model selection. Items without enough history should continue using their best available depletion-anchored baseline rather than being omitted.")


if __name__ == "__main__":
    main()
