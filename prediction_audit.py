import argparse
import sqlite3
from pathlib import Path

from services.history_service import get_prediction_accuracy_summary, init_db

DB_PATH = Path(__file__).parent / "data" / "stock_history.db"


def fmt(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    hours, rem = divmod(abs(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    sign = "-" if seconds < 0 else ""
    if hours:
        return f"{sign}{hours}h {minutes}m {secs}s"
    return f"{sign}{minutes}m {secs}s"


def main():
    parser = argparse.ArgumentParser(description="Inspect live prediction audit results")
    parser.add_argument("country")
    parser.add_argument("item")
    parser.add_argument("--recent", type=int, default=10)
    args = parser.parse_args()

    init_db()
    summary = get_prediction_accuracy_summary(args.country.lower(), args.item)
    print(f"\n=== Live prediction audit: {args.item} / {args.country.upper()} ===")
    print(f"Valid resolved predictions: {summary['resolved_valid_predictions']}")
    print(f"Median exact error: {fmt(summary['median_absolute_error_seconds'])}")
    print(f"Mean exact error: {fmt(summary['mean_absolute_error_seconds'])}")
    hit = summary['window_hit_rate']
    print(f"Window hit rate: {'—' if hit is None else f'{hit * 100:.1f}%'}")
    print(f"Median miss outside window: {fmt(summary['median_outside_window_seconds'])}")

    with sqlite3.connect(DB_PATH) as conn:
        pending = conn.execute(
            """
            SELECT COUNT(*) FROM prediction_audits
            WHERE country=? AND LOWER(item_name)=LOWER(?) AND status='pending'
            """,
            (args.country.lower(), args.item),
        ).fetchone()[0]
        print(f"Pending predictions: {pending}")

        rows = conn.execute(
            """
            SELECT created_at, method, estimate_timestamp, window_start_timestamp,
                   window_end_timestamp, actual_restock_timestamp,
                   signed_error_seconds, window_hit, data_valid, validation_reason
            FROM prediction_audits
            WHERE country=? AND LOWER(item_name)=LOWER(?)
            ORDER BY created_at DESC LIMIT ?
            """,
            (args.country.lower(), args.item, args.recent),
        ).fetchall()

    if rows:
        import datetime
        print("\nRecent frozen predictions:")
        for row in rows:
            created, method, estimate, ws, we, actual, error, hit, valid, reason = row
            clock = lambda ts: datetime.datetime.fromtimestamp(ts).strftime('%m/%d %I:%M:%S %p') if ts else 'pending'
            print(
                f"- made {clock(created)} | {method} | predicted {clock(estimate)} "
                f"| actual {clock(actual)} | error {fmt(error)} | "
                f"window {'HIT' if hit else ('MISS' if hit == 0 else 'pending')} | "
                f"ground truth {'valid' if valid else ('invalid' if valid == 0 else 'pending')}"
            )
            if reason and valid == 0:
                print(f"  reason: {reason}")


if __name__ == '__main__':
    main()
