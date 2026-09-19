import argparse
from collections import Counter

from services.prediction_lab import run_model_tournament


def fmt(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    hours, rem = divmod(abs(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def main():
    parser = argparse.ArgumentParser(description="All-item prediction model tournament")
    parser.add_argument("--min-waits", type=int, default=6, help="minimum usable samples to include an item")
    parser.add_argument("--min-predictions", type=int, default=10, help="minimum walk-forward predictions before naming a winner")
    parser.add_argument("--min-rows", type=int, default=20)
    args = parser.parse_args()

    result = run_model_tournament(
        min_waits=args.min_waits,
        min_predictions=args.min_predictions,
        min_rows=args.min_rows,
    )

    print("\n=== Torn Fren all-item model tournament ===")
    print(f"Minimum samples to include item: {args.min_waits}")
    print(f"Minimum backtest predictions to name winner: {args.min_predictions}\n")
    print(f"{'item':<28} {'cty':<4} {'class':<10} {'waits':>6} {'r-r':>6} {'winner':<34} {'med err':>10} {'hit':>7}")
    print("-" * 118)

    for item in sorted(result["items"], key=lambda x: (x["behavior_class"], x["country"], x["item_name"])):
        winner = item["winner"]
        if winner:
            winner_name = winner.name
            med_err = fmt(winner.median_absolute_error_seconds)
            hit = f"{winner.window_hit_rate * 100:.1f}%" if winner.window_hit_rate is not None else "—"
        else:
            winner_name = "insufficient backtest data"
            med_err = "—"
            hit = "—"
        print(
            f"{item['item_name'][:28]:<28} {item['country'].upper():<4} {item['behavior_class']:<10} "
            f"{item['valid_waits']:>6} {item['valid_restock_intervals']:>6} "
            f"{winner_name[:34]:<34} {med_err:>10} {hit:>7}"
        )

    print("\n=== Behavior-class winners ===")
    for behavior, summary in sorted(result["class_summary"].items()):
        print(f"\n{behavior}: {summary['eligible_items']} eligible winner(s) / {summary['items']} item(s)")
        print(f"  anchor wins: depletion={summary['anchor_wins']['depletion']}  restock={summary['anchor_wins']['restock']}")
        wins = Counter(summary["model_wins"])
        for name, count in wins.most_common():
            print(f"  {name:<36} {count}")

    print("\n=== Anchor-family result ===")
    print(f"depletion-anchored winners: {result['anchor_summary']['depletion']}")
    print(f"restock-anchored winners:  {result['anchor_summary']['restock']}")
    print("\nThis directly tests the depletion-timer hypothesis: if depletion-anchored models consistently beat restock-to-restock models for an item/class, the data supports anchoring the timer at sellout.")


if __name__ == "__main__":
    main()
