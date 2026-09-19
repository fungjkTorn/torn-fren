import argparse

from services.arrival_success_lab import backtest_arrival_policy


def dur(value, signed=False):
    if value is None:
        return "—"
    value = int(round(value))
    sign = ""
    if value < 0:
        sign = "-"
        value = abs(value)
    h, rem = divmod(value, 3600)
    m, s = divmod(rem, 60)
    body = f"{h}h {m}m {s}s" if h else f"{m}m {s}s" if m else f"{s}s"
    return sign + body


def pct(value):
    return "—" if value is None else f"{100 * value:.1f}%"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("country")
    p.add_argument("item_name")
    p.add_argument("--coverage", type=float, default=0.90)
    args = p.parse_args()

    r = backtest_arrival_policy(
        args.country,
        args.item_name,
        target_coverage=args.coverage,
    )

    print(f"=== Arrival-success backtest: {r['item_name']} / {r['country']} ===")
    print(f"Behavior: {r['behavior_class']} | selector tier: {r['selection_tier'].upper()}")
    print(f"Selected Prediction v2 model: {r['selected_model']}")
    print(f"Qualified history samples: {r['history_samples']}")
    print(f"Scored predictions: {r['scored_predictions']}")
    print(f"Median stock lifetime: {dur(r['median_stock_lifetime_seconds'])}")
    print(f"PI + pilot travel time: {dur(r['travel_seconds'])}")
    print()
    print("ARRIVAL POLICY")
    print(f"  arrive exactly at predicted restock: {pct(r['arrival_at_prediction_success_rate'])}")
    print(f"  optimized walk-forward arrival:      {pct(r['optimized_arrival_success_rate'])}")
    print(f"  recent 20 optimized:                 {pct(r['recent20_arrival_success_rate'])}")
    print(f"  recent 10 optimized:                 {pct(r['recent10_arrival_success_rate'])}")
    print()
    print("CURRENT LEARNED TARGET")
    print(f"  recommended arrival offset vs predicted restock: {dur(r['recommended_arrival_offset_seconds'])}")
    print(f"  historical fit at that offset:                 {pct(r['historical_fit_success_rate'])}")
    print()
    print(f"{int(r['target_coverage'] * 100)}% RESTOCK WINDOW")
    if r["restock_window_width_seconds"] is None:
        print("  not enough resolved predictions for a bounded window yet")
    else:
        print(f"  actual-restock error range: {dur(r['restock_window_lo_error_seconds'])} .. {dur(r['restock_window_hi_error_seconds'])}")
        print(f"  width:                      {dur(r['restock_window_width_seconds'])}")
        print(f"  width < stock lifetime:     {r['window_is_useful']}")
    print()
    print("Interpretation:")
    print("- The optimized arrival policy is walk-forward: each historical trip uses only older resolved predictions.")
    print("- Success means the simulated arrival happened AFTER the real restock and BEFORE the real depletion.")
    print("- Travel duration affects the leave-by timestamp, but not whether the chosen arrival offset was inside stock availability.")
    print("- This lab does not change the live graph or Discord yet.")


if __name__ == "__main__":
    main()
