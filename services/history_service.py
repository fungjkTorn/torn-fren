import sqlite3
import time
from pathlib import Path

from services.yata_api import get_country_stock

DB_PATH = Path(__file__).parent.parent / "data" / "stock_history.db"

def get_known_items(country: str):
    """Return every distinct item name ever recorded for a country, regardless of
    current stock level — lets sold-out items still show up in autocomplete."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT item_name FROM stock_history WHERE country = ?",
            (country,),
        ).fetchall()
    return [row[0] for row in rows]

def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                country TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                cost INTEGER,
                source TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_snapshot
            ON stock_history (timestamp, country, item_id, quantity, cost)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_country_item_lookup ON stock_history (country, item_name, timestamp)")

def save_snapshot(country: str):
    init_db()
    stock = get_country_stock(country)
    timestamp = int(time.time())

    inserted = 0
    skipped = 0

    with _connect() as conn:
        for item in stock:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO stock_history
                   (timestamp, country, item_id, item_name, quantity, cost, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (timestamp, country, item["id"], item["name"], item["quantity"], item["cost"], "yata"),
            )
            if cursor.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

    print(f"{country}: inserted {inserted}, skipped {skipped} duplicates at {time.strftime('%H:%M:%S', time.localtime(timestamp))}")

def get_restock_prediction(country: str, item_name: str):
    """Core logic, returns a dict (or None if no history exists at all) so both
    the console script and the Discord bot share one calculation."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT timestamp, quantity FROM stock_history
               WHERE country = ? AND item_name = ?
               ORDER BY timestamp ASC""",
            (country, item_name),
        ).fetchall()

    if not rows:
        return None

    current_stock = rows[-1][1]

    restock_timestamps = []
    for i in range(1, len(rows)):
        if rows[i - 1][1] == 0 and rows[i][1] > 0:
            restock_timestamps.append(rows[i][0])

    result = {
        "current_stock": current_stock,
        "observed_restocks": len(restock_timestamps),
        "avg_interval_minutes": None,
        "predicted_next_str": None,
    }

    if len(restock_timestamps) >= 2:
        intervals = [
            restock_timestamps[i] - restock_timestamps[i - 1]
            for i in range(1, len(restock_timestamps))
        ]
        avg_interval_seconds = sum(intervals) / len(intervals)
        predicted_next = restock_timestamps[-1] + avg_interval_seconds

        result["avg_interval_minutes"] = avg_interval_seconds / 60
        result["predicted_next_str"] = time.strftime("%I:%M %p", time.localtime(predicted_next))

    return result


def predict_restock(country: str, item_name: str):
    """Console-friendly wrapper for manual testing in a Python shell."""
    result = get_restock_prediction(country, item_name)

    if result is None:
        print(f"No history found for '{item_name}' in {country}. Run save_snapshot() a few times first.")
        return

    print(f"Current Stock: {result['current_stock']}")
    print(f"Observed Restocks: {result['observed_restocks']}")

    if result["avg_interval_minutes"] is None:
        print("Not enough restocks observed yet to estimate an average interval.")
    else:
        print(f"Average Interval: {result['avg_interval_minutes']:.1f} minutes")
        print(f"Predicted Next Restock: {result['predicted_next_str']}")


if __name__ == "__main__":
    save_snapshot("uni")