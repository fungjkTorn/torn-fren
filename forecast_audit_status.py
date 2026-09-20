import argparse
from datetime import datetime

from services.forecast_auditor import (
    forecast_depth_summary,
    recent_forecast_runs,
)


def pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def dur(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def main():
    p = argparse.ArgumentParser(description="Inspect multi-cycle forecast audit data.")
    p.add_argument("country", nargs="?")
    p.add_argument("item_name", nargs="?")
    p.add_argument("--runs", type=int, default=8)
    args = p.parse_args()

    print("=== Multi-cycle forecast auditor ===")
    if args.country and args.item_name:
        print(f"Item: {args.item_name} / {args.country.upper()}")

    summary = forecast_depth_summary(args.country, args.item_name)
    if not summary:
        print("\nNo resolved projected-cycle audits yet.")
        print("That is normal immediately after installing this patch.")
    else:
        print("\nResolved accuracy by true projection depth:")
        print(f"{'depth':>6} {'n':>5} {'mean err':>12} {'window hit':>12} {'arrival hit':>13}")
        print("-" * 56)
        for row in summary:
            print(
                f"D{row.get('projection_depth', row['prediction_number'] - 1):<5} "
                f"{row['n']:>5} "
                f"{dur(row['mean_absolute_error_seconds']):>12} "
                f"{pct(row['window_hit_rate']):>12} "
                f"{pct(row['arrival_hit_rate']):>13}"
            )

    runs = recent_forecast_runs(args.country, args.item_name, limit=args.runs)
    print("\nRecent frozen forecast chains:")
    if not runs:
        print("  none yet")
    else:
        for run in runs:
            when = datetime.fromtimestamp(run["created_at"]).strftime("%m/%d %I:%M:%S %p")
            active = run["active_prediction_number"]
            print(
                f"  {when} | {run['country'].upper()}/{run['item_name']} | "
                f"active=P{active or '-'} | {run['travel_reliability'] or '—'} | "
                f"{run['source']}"
            )


if __name__ == "__main__":
    main()
