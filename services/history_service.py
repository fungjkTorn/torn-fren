import sqlite3
import time
from pathlib import Path

from services.yata_api import get_country_stock

DB_PATH = Path(__file__).parent.parent / "data" / "stock_history.db"


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
            CREATE INDEX IF NOT EXISTS idx_country_item_lookup
            ON stock_history (country, item_name, timestamp)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_country_item_id_lookup
            ON stock_history (country, item_id, timestamp)
        """)


def get_known_items(country: str):
    """
    Return every distinct item name ever recorded for a country.
    This lets sold-out items still show up in autocomplete.
    """
    init_db()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT item_name
            FROM stock_history
            WHERE country = ?
            ORDER BY item_name ASC
            """,
            (country,),
        ).fetchall()

    return [row[0] for row in rows]


def get_latest_quantity(conn, country: str, item_id: int):
    """
    Return the most recent saved quantity for one country/item.
    """
    row = conn.execute(
        """
        SELECT quantity
        FROM stock_history
        WHERE country = ? AND item_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (country, item_id),
    ).fetchone()

    if row is None:
        return None

    return row[0]


def save_snapshot(country: str):
    """
    Save one country snapshot.

    Important:
    This only inserts a new row when an item's quantity changed.
    It prevents 30-second duplicate spam in the database.
    """
    init_db()

    stock = get_country_stock(country)
    timestamp = int(time.time())

    inserted = 0
    skipped = 0

    with _connect() as conn:
        for item in stock:
            item_id = item["id"]
            item_name = item["name"]
            quantity = item["quantity"]
            cost = item.get("cost")

            latest_quantity = get_latest_quantity(conn, country, item_id)

            if latest_quantity == quantity:
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO stock_history
                (timestamp, country, item_id, item_name, quantity, cost, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (timestamp, country, item_id, item_name, quantity, cost, "yata"),
            )

            inserted += 1

    print(
        f"{country}: inserted {inserted}, skipped {skipped} unchanged "
        f"at {time.strftime('%H:%M:%S', time.localtime(timestamp))}"
    )

def save_snapshot_from_export(country: str, country_data: dict, source: str):
    """
    Save one country's snapshot from an already-fetched export object,
    instead of calling any API directly. This is what the poller uses now.
    """
    init_db()

    stock = country_data.get("stocks", [])
    timestamp = int(time.time())

    inserted = 0
    skipped = 0

    with _connect() as conn:
        for item in stock:
            item_id = item["id"]
            item_name = item["name"]
            quantity = item["quantity"]
            cost = item.get("cost")

            latest_quantity = get_latest_quantity(conn, country, item_id)

            if latest_quantity == quantity:
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO stock_history
                (timestamp, country, item_id, item_name, quantity, cost, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (timestamp, country, item_id, item_name, quantity, cost, source),
            )

            inserted += 1

    print(f"{country}: inserted {inserted}, skipped {skipped} unchanged")


def save_all_snapshots(export: dict):
    """
    Save every country in one export object — one API call feeds every
    country's row inserts, instead of calling the API once per country.
    """
    source = export.get("source", "unknown")
    stocks = export.get("stocks", {})

    for country, country_data in stocks.items():
        save_snapshot_from_export(country, country_data, source)


def get_item_history_since(country: str, item_name: str, hours: int = 24):
    """
    Return stock history rows for one item over the last X hours, oldest → newest.
    Used later by /graph — not wired into any command yet.
    """
    init_db()
    cutoff = int(time.time()) - (hours * 3600)

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, quantity, cost
            FROM stock_history
            WHERE country = ? AND LOWER(item_name) = LOWER(?) AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (country, item_name, cutoff),
        ).fetchall()

    return [{"timestamp": row[0], "quantity": row[1], "cost": row[2]} for row in rows]

def get_item_history(country: str, item_name: str, limit: int = 15):
    """
    Return the most recent recorded stock changes for one item.
    """
    init_db()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, quantity, cost
            FROM stock_history
            WHERE country = ? AND LOWER(item_name) = LOWER(?)
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (country, item_name, limit),
        ).fetchall()

    return [
        {
            "timestamp": row[0],
            "quantity": row[1],
            "cost": row[2],
        }
        for row in rows
    ]


def get_all_item_rows(country: str, item_name: str):
    """
    Return all stock rows for one item in chronological order.
    """
    init_db()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, quantity
            FROM stock_history
            WHERE country = ? AND LOWER(item_name) = LOWER(?)
            ORDER BY timestamp ASC
            """,
            (country, item_name),
        ).fetchall()

    return rows


def _format_duration(seconds):
    if seconds is None:
        return "Unknown"

    seconds = int(seconds)

    minutes = seconds // 60
    remaining_seconds = seconds % 60

    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    return f"{hours}h {remaining_minutes}m"


def calculate_average_sellout_time(rows):
    """
    Average time from restock to sellout.

    Restock = previous quantity was 0, current quantity is above 0.
    Sellout = previous quantity was above 0, current quantity is 0.
    """
    if not rows:
        return {
            "avg_sellout_seconds": None,
            "sellout_samples": 0,
        }

    sellout_durations = []
    current_restock_time = None

    for i in range(1, len(rows)):
        previous_quantity = rows[i - 1][1]
        current_timestamp = rows[i][0]
        current_quantity = rows[i][1]

        if previous_quantity == 0 and current_quantity > 0:
            current_restock_time = current_timestamp

        if previous_quantity > 0 and current_quantity == 0 and current_restock_time is not None:
            sellout_durations.append(current_timestamp - current_restock_time)
            current_restock_time = None

    if not sellout_durations:
        return {
            "avg_sellout_seconds": None,
            "sellout_samples": 0,
        }

    avg_sellout_seconds = sum(sellout_durations) / len(sellout_durations)

    return {
        "avg_sellout_seconds": avg_sellout_seconds,
        "sellout_samples": len(sellout_durations),
    }


def get_restock_prediction(country: str, item_name: str):
    """
    Current simple prediction logic:
    - Find restocks: 0 -> positive
    - Average the interval between restocks
    - Predict next restock as last restock + average interval
    - Predict second next restock by adding the average interval again
    - Calculate average sellout time
    """
    rows = get_all_item_rows(country, item_name)

    if not rows:
        return None

    current_stock = rows[-1][1]
    latest_timestamp = rows[-1][0]

    restock_timestamps = []

    for i in range(1, len(rows)):
        previous_quantity = rows[i - 1][1]
        current_timestamp = rows[i][0]
        current_quantity = rows[i][1]

        if previous_quantity == 0 and current_quantity > 0:
            restock_timestamps.append(current_timestamp)

    sellout_stats = calculate_average_sellout_time(rows)

    result = {
        "current_stock": current_stock,
        "latest_timestamp": latest_timestamp,
        "latest_time_str": time.strftime("%I:%M:%S %p", time.localtime(latest_timestamp)),
        "observed_restocks": len(restock_timestamps),
        "avg_interval_minutes": None,
        "predicted_next_str": None,
        "predicted_second_next_str": None,
        "avg_sellout_seconds": sellout_stats["avg_sellout_seconds"],
        "avg_sellout_str": _format_duration(sellout_stats["avg_sellout_seconds"]),
        "sellout_samples": sellout_stats["sellout_samples"],
    }

    if len(restock_timestamps) >= 2:
        intervals = [
            restock_timestamps[i] - restock_timestamps[i - 1]
            for i in range(1, len(restock_timestamps))
        ]

        avg_interval_seconds = sum(intervals) / len(intervals)

        predicted_next = restock_timestamps[-1] + avg_interval_seconds
        predicted_second_next = predicted_next + avg_interval_seconds

        result["avg_interval_minutes"] = avg_interval_seconds / 60
        result["predicted_next_str"] = time.strftime("%I:%M:%S %p", time.localtime(predicted_next))
        result["predicted_second_next_str"] = time.strftime("%I:%M:%S %p", time.localtime(predicted_second_next))

    return result

def predict_restock(country: str, item_name: str):
    """
    Console-friendly wrapper for testing.
    """
    result = get_restock_prediction(country, item_name)

    if result is None:
        print(f"No history found for '{item_name}' in {country}. Run save_snapshot() first.")
        return

    print(f"Current Stock: {result['current_stock']}")
    print(f"Last Recorded Change: {result['latest_time_str']}")
    print(f"Observed Restocks: {result['observed_restocks']}")

    if result["avg_interval_minutes"] is None:
        print("Not enough restocks observed yet.")
    else:
        print(f"Average Interval: {result['avg_interval_minutes']:.1f} minutes")
        print(f"Predicted Next Restock: {result['predicted_next_str']}")

    print(f"Average Sellout Time: {result['avg_sellout_str']} ({result['sellout_samples']} samples)")


if __name__ == "__main__":
    save_snapshot("uni")

def get_latest_stock_snapshot(country: str):
    """
    Return the most recently known quantity/cost for every item in a country,
    straight from our own database — no live API call. This is what /stock
    uses so it keeps working even if YATA and Prometheus are both down; it
    just shows the latest known state along with how old that is.
    """
    init_db()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT sh.item_id, sh.item_name, sh.quantity, sh.cost, sh.timestamp, sh.source
            FROM stock_history sh
            INNER JOIN (
                SELECT item_id, MAX(timestamp) AS max_ts
                FROM stock_history
                WHERE country = ?
                GROUP BY item_id
            ) latest
            ON sh.item_id = latest.item_id AND sh.timestamp = latest.max_ts
            WHERE sh.country = ?
            ORDER BY sh.item_name ASC
            """,
            (country, country),
        ).fetchall()

    return [
        {"id": row[0], "name": row[1], "quantity": row[2], "cost": row[3], "timestamp": row[4], "source": row[5]}
        for row in rows
    ]