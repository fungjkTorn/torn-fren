import sqlite3

from services.history_service import DB_PATH
from services.prediction_v2_selector import select_prediction_v2_model


def fmt_duration(seconds):
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def main():
    with sqlite3.connect(DB_PATH) as conn:
        items = conn.execute(
            """
            SELECT country, item_name, COUNT(*)
            FROM stock_history
            GROUP BY country, item_name
            ORDER BY country, item_name
            """
        ).fetchall()

    print("=== Prediction v2 selector overview ===")
    print(
        f"{'item':28} {'cty':4} {'class':10} {'hist':>5} {'tier':12} "
        f"{'selected model':28} {'med err':>9} {'p90':>9}"
    )
    print("-" * 120)

    for country, item_name, _ in items:
        try:
            r = select_prediction_v2_model(country, item_name)
        except Exception:
            continue
        if r["behavior_class"] not in ("rapid", "short", "medium", "long", "very_long"):
            continue
        s = r["selected_model"]
        print(
            f"{item_name[:28]:28} {country.upper():4} {r['behavior_class']:10} "
            f"{r['history_samples']:5d} {r['selection_tier']:12} "
            f"{s['name'][:28]:28} "
            f"{fmt_duration(s['median_error_seconds']):>9} "
            f"{fmt_duration(s['p90_error_seconds']):>9}"
        )


if __name__ == "__main__":
    main()
