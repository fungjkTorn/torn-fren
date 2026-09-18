import sqlite3
import time
import statistics
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS poll_heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                source TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_poll_heartbeats_timestamp
            ON poll_heartbeats (timestamp)
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

    A heartbeat row is also written once per successful export cycle.
    This gives the prediction engine a reliable way to know whether we
    were actually collecting data continuously.
    """
    init_db()

    source = export.get("source", "unknown")
    stocks = export.get("stocks", {})
    heartbeat_timestamp = int(time.time())

    with _connect() as conn:
        last_heartbeat = conn.execute(
            """
            SELECT MAX(timestamp)
            FROM poll_heartbeats
            """
        ).fetchone()[0]

        # We only need heartbeat resolution fine enough to detect multi-hour gaps.
        # Recording at most once every 5 minutes avoids unnecessary DB growth.
        if last_heartbeat is None or heartbeat_timestamp - last_heartbeat >= 300:
            conn.execute(
                """
                INSERT INTO poll_heartbeats (timestamp, source)
                VALUES (?, ?)
                """,
                (heartbeat_timestamp, source),
            )

    for country, country_data in stocks.items():
        save_snapshot_from_export(country, country_data, source)


def get_item_history_since(country: str, item_name: str, hours: float = 24):
    """
    Return stock history for one item over the requested window, oldest -> newest.

    stock_history only stores quantity changes. The latest row before the cutoff is
    therefore inserted as an anchor at the exact left edge of the requested range.
    That lets the chart hold the prior quantity until the next real change.
    """
    init_db()

    hours = max(float(hours), 1 / 60)
    now = int(time.time())
    cutoff = now - int(hours * 3600)

    with _connect() as conn:
        previous = conn.execute(
            """
            SELECT timestamp, quantity, cost
            FROM stock_history
            WHERE country = ?
              AND LOWER(item_name) = LOWER(?)
              AND timestamp < ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (country, item_name, cutoff),
        ).fetchone()

        rows = conn.execute(
            """
            SELECT timestamp, quantity, cost
            FROM stock_history
            WHERE country = ?
              AND LOWER(item_name) = LOWER(?)
              AND timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp ASC
            """,
            (country, item_name, cutoff, now),
        ).fetchall()

    result = []

    if previous is not None:
        result.append({
            "timestamp": cutoff,
            "quantity": previous[1],
            "cost": previous[2],
            "anchor": True,
        })

    for row in rows:
        result.append({
            "timestamp": row[0],
            "quantity": row[1],
            "cost": row[2],
            "anchor": False,
        })

    return result

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


def _median_absolute_deviation(values):
    if not values:
        return None
    med = statistics.median(values)
    return statistics.median(abs(value - med) for value in values)


def _format_clock(timestamp):
    if timestamp is None:
        return None
    return time.strftime("%I:%M:%S %p", time.localtime(timestamp))


def _format_datetime(timestamp):
    if timestamp is None:
        return None
    return time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(timestamp))


def _get_observation_timestamps(start_timestamp: int, end_timestamp: int):
    """
    Return timestamps that prove the collector was alive during an interval.

    New data uses poll_heartbeats, which are written once per successful poll.
    Historical data collected before heartbeat support falls back to timestamps
    from stock_history across all countries/items. That historical fallback is
    intentionally conservative and should be treated as a best-effort estimate.
    """
    init_db()

    if end_timestamp <= start_timestamp:
        return [start_timestamp, end_timestamp]

    with _connect() as conn:
        heartbeat_rows = conn.execute(
            """
            SELECT timestamp
            FROM poll_heartbeats
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
            """,
            (start_timestamp, end_timestamp),
        ).fetchall()

        if heartbeat_rows:
            timestamps = [row[0] for row in heartbeat_rows]
        else:
            # Historical fallback for data collected before heartbeat support.
            history_rows = conn.execute(
                """
                SELECT DISTINCT timestamp
                FROM stock_history
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
                """,
                (start_timestamp, end_timestamp),
            ).fetchall()
            timestamps = [row[0] for row in history_rows]

    return [start_timestamp, *timestamps, end_timestamp]


def _max_collection_gap_seconds(start_timestamp: int, end_timestamp: int):
    timestamps = _get_observation_timestamps(start_timestamp, end_timestamp)
    if len(timestamps) < 2:
        return max(0, end_timestamp - start_timestamp)

    return max(
        timestamps[i] - timestamps[i - 1]
        for i in range(1, len(timestamps))
    )


def _leave_one_out_mean(values, index):
    others = [value for i, value in enumerate(values) if i != index]
    if not others:
        return None
    return statistics.mean(others)


def _build_validated_cycles(rows, max_collection_gap_seconds=3 * 60 * 60):
    """
    Convert raw stock changes into restock cycles and qualify each cycle for use
    in prediction statistics.

    A completed cycle is excluded when:
      1. the collector has an observation gap greater than 3 hours anywhere
         between restock and depletion, or
      2. its observed peak is less than 10% of the leave-one-out average peak
         quantity for the other completed cycles.

    Zero->restock wait samples are validated separately because they span the gap
    between two cycles. They are excluded if the collector was down for >3 hours
    during the wait, if the previous depletion was unreliable, or if the incoming
    restock is a tiny/anomalous cycle.
    """
    cycles = []
    current = None

    for i in range(1, len(rows)):
        prev_ts, prev_qty = rows[i - 1]
        ts, qty = rows[i]

        if prev_qty == 0 and qty > 0:
            if current is not None and current.get("depletion_time") is None:
                # We saw a new restock without a clean depletion. Preserve the
                # raw event, but the unfinished cycle cannot be used statistically.
                current["complete"] = False
                current["valid_lifetime"] = False
                current["exclusion_reasons"] = ["missing depletion before next restock"]
                cycles.append(current)

            current = {
                "restock_time": ts,
                "first_seen_quantity": qty,
                "peak_time": ts,
                "peak_quantity": qty,
                "depletion_time": None,
                "lifetime_seconds": None,
                "complete": False,
                "valid_lifetime": False,
                "tiny_restock": False,
                "max_collection_gap_seconds": None,
                "exclusion_reasons": [],
            }
            continue

        if current is not None and qty > current["peak_quantity"]:
            current["peak_quantity"] = qty
            current["peak_time"] = ts

        if prev_qty > 0 and qty == 0 and current is not None:
            current["depletion_time"] = ts
            current["lifetime_seconds"] = ts - current["restock_time"]
            current["complete"] = True
            cycles.append(current)
            current = None

    active_cycle = current

    completed_indexes = [i for i, cycle in enumerate(cycles) if cycle.get("complete")]
    completed_peaks = [cycles[i]["peak_quantity"] for i in completed_indexes]

    # Tiny-restock rule: compare each completed cycle to the mean of all OTHER
    # completed observed peaks. Using peak rather than first-seen quantity avoids
    # penalizing a cycle merely because the first poll caught it late.
    for local_index, cycle_index in enumerate(completed_indexes):
        cycle = cycles[cycle_index]
        comparison_mean = _leave_one_out_mean(completed_peaks, local_index)
        cycle["comparison_mean_peak"] = comparison_mean

        if comparison_mean and cycle["peak_quantity"] < comparison_mean * 0.10:
            cycle["tiny_restock"] = True
            cycle["exclusion_reasons"].append(
                f"tiny restock: peak {cycle['peak_quantity']:,} < 10% of other-cycle average {comparison_mean:,.0f}"
            )

    # Validate lifetime coverage for each completed cycle.
    for cycle in cycles:
        if not cycle.get("complete"):
            continue

        gap = _max_collection_gap_seconds(
            cycle["restock_time"],
            cycle["depletion_time"],
        )
        cycle["max_collection_gap_seconds"] = gap

        if gap > max_collection_gap_seconds:
            cycle["exclusion_reasons"].append(
                f"collector gap {_format_duration(gap)} exceeded 3h"
            )

        cycle["valid_lifetime"] = not cycle["exclusion_reasons"]

    # Build validated zero->restock samples.
    #
    # Tiny/anomalous restocks are deliberately NOT treated as boundaries here.
    # They remain visible in raw history/events, but prediction timing bridges
    # across them from the last normal depletion to the next normal restock.
    # This prevents a 4-unit/300-unit blip from poisoning two adjacent waits.
    wait_samples = []
    completed_cycles = [cycle for cycle in cycles if cycle.get("complete")]
    normal_cycles = [cycle for cycle in completed_cycles if not cycle.get("tiny_restock")]

    for i in range(1, len(normal_cycles)):
        previous = normal_cycles[i - 1]
        current_cycle = normal_cycles[i]

        wait_seconds = current_cycle["restock_time"] - previous["depletion_time"]
        gap = _max_collection_gap_seconds(
            previous["depletion_time"],
            current_cycle["restock_time"],
        )

        # Count any tiny cycles that occurred between these two normal boundaries.
        bridged_tiny_count = sum(
            1
            for cycle in completed_cycles
            if cycle.get("tiny_restock")
            and previous["depletion_time"] < cycle["restock_time"] < current_cycle["restock_time"]
        )

        reasons = []
        if gap > max_collection_gap_seconds:
            reasons.append(f"collector gap {_format_duration(gap)} exceeded 3h")

        # The outgoing depletion must itself be trustworthy. A later collection
        # gap inside the incoming cycle does not invalidate the restock timestamp.
        if not previous.get("valid_lifetime"):
            reasons.append("previous depletion/cycle was not reliable")

        wait_samples.append({
            "from_depletion": previous["depletion_time"],
            "to_restock": current_cycle["restock_time"],
            "seconds": wait_seconds,
            "max_collection_gap_seconds": gap,
            "bridged_tiny_restock_count": bridged_tiny_count,
            "valid": not reasons,
            "exclusion_reasons": reasons,
        })

    return cycles, active_cycle, wait_samples


def get_stock_graph_analysis(country: str, item_name: str, window_hours: float = 24):
    """
    Build observed cycle statistics plus a baseline prediction using only qualified
    samples. Raw graph events are never deleted; validation only controls which
    cycles are allowed to influence averages, medians, confidence, and prediction.
    """
    rows = get_all_item_rows(country, item_name)
    if not rows:
        return None

    now = int(time.time())
    cutoff = now - int(max(float(window_hours), 1 / 60) * 3600)

    cycles, active_cycle, wait_samples = _build_validated_cycles(rows)
    completed_cycles = [cycle for cycle in cycles if cycle.get("complete")]
    valid_cycles = [cycle for cycle in completed_cycles if cycle.get("valid_lifetime")]

    # Every raw event remains visible on the graph, even if excluded statistically.
    events = []
    for cycle in completed_cycles:
        events.extend([
            {
                "type": "restock",
                "timestamp": cycle["restock_time"],
                "quantity": cycle["first_seen_quantity"],
                "valid_for_prediction": cycle["valid_lifetime"],
            },
            {
                "type": "peak",
                "timestamp": cycle["peak_time"],
                "quantity": cycle["peak_quantity"],
                "valid_for_prediction": cycle["valid_lifetime"],
            },
            {
                "type": "depletion",
                "timestamp": cycle["depletion_time"],
                "quantity": 0,
                "valid_for_prediction": cycle["valid_lifetime"],
            },
        ])

    if active_cycle is not None:
        events.extend([
            {
                "type": "restock",
                "timestamp": active_cycle["restock_time"],
                "quantity": active_cycle["first_seen_quantity"],
                "valid_for_prediction": True,
            },
            {
                "type": "peak",
                "timestamp": active_cycle["peak_time"],
                "quantity": active_cycle["peak_quantity"],
                "valid_for_prediction": True,
            },
        ])

    valid_lifetimes = [cycle["lifetime_seconds"] for cycle in valid_cycles]
    valid_zero_waits = [sample["seconds"] for sample in wait_samples if sample["valid"]]

    # Restock-to-restock intervals use normal (non-tiny) restocks and validate
    # collector continuity across the whole interval. Tiny blips are bridged.
    normal_completed_cycles = [
        cycle for cycle in completed_cycles if not cycle.get("tiny_restock")
    ]
    restock_interval_samples = []
    for i in range(1, len(normal_completed_cycles)):
        previous = normal_completed_cycles[i - 1]
        current_cycle = normal_completed_cycles[i]
        gap = _max_collection_gap_seconds(
            previous["restock_time"],
            current_cycle["restock_time"],
        )
        reasons = []
        if gap > 3 * 60 * 60:
            reasons.append(f"collector gap {_format_duration(gap)} exceeded 3h")

        bridged_tiny_count = sum(
            1
            for cycle in completed_cycles
            if cycle.get("tiny_restock")
            and previous["restock_time"] < cycle["restock_time"] < current_cycle["restock_time"]
        )

        restock_interval_samples.append({
            "from_restock": previous["restock_time"],
            "to_restock": current_cycle["restock_time"],
            "seconds": current_cycle["restock_time"] - previous["restock_time"],
            "max_collection_gap_seconds": gap,
            "bridged_tiny_restock_count": bridged_tiny_count,
            "valid": not reasons,
            "exclusion_reasons": reasons,
        })

    valid_restock_intervals = [
        sample["seconds"] for sample in restock_interval_samples if sample["valid"]
    ]

    current_stock = rows[-1][1]
    latest_timestamp = rows[-1][0]

    all_restock_times = [cycle["restock_time"] for cycle in completed_cycles]
    if active_cycle is not None:
        all_restock_times.append(active_cycle["restock_time"])

    all_depletion_times = [cycle["depletion_time"] for cycle in completed_cycles]
    last_restock = all_restock_times[-1] if all_restock_times else None
    last_depletion = all_depletion_times[-1] if all_depletion_times else None

    if active_cycle is not None:
        last_peak_quantity = active_cycle["peak_quantity"]
        last_peak_time = active_cycle["peak_time"]
    elif completed_cycles:
        last_peak_quantity = completed_cycles[-1]["peak_quantity"]
        last_peak_time = completed_cycles[-1]["peak_time"]
    else:
        last_peak_quantity = None
        last_peak_time = None

    def mean_or_none(values):
        return statistics.mean(values) if values else None

    def median_or_none(values):
        return statistics.median(values) if values else None

    avg_lifetime = mean_or_none(valid_lifetimes)
    median_lifetime = median_or_none(valid_lifetimes)
    avg_zero_wait = mean_or_none(valid_zero_waits)
    median_zero_wait = median_or_none(valid_zero_waits)
    avg_restock_interval = mean_or_none(valid_restock_intervals)
    median_restock_interval = median_or_none(valid_restock_intervals)

    prediction = {
        "method": None,
        "estimate_timestamp": None,
        "window_start_timestamp": None,
        "window_end_timestamp": None,
        "second_estimate_timestamp": None,
        "confidence": "low",
        "sample_count": 0,
        "excluded_sample_count": 0,
        "note": "Not enough qualified history yet.",
    }

    samples = None
    anchor = None
    typical = None

    if current_stock == 0 and last_depletion is not None and valid_zero_waits:
        samples = valid_zero_waits
        anchor = last_depletion
        typical = median_zero_wait
        prediction["method"] = "validated depletion-anchored median"
        prediction["excluded_sample_count"] = len(wait_samples) - len(valid_zero_waits)
        prediction["note"] = (
            "Uses only qualified depletion→restock waits. Cycles with >3h collection gaps "
            "or tiny restocks are excluded from the baseline."
        )
    elif current_stock > 0 and last_restock is not None and valid_restock_intervals:
        samples = valid_restock_intervals
        anchor = last_restock
        typical = median_restock_interval
        prediction["method"] = "validated restock-interval median"
        prediction["excluded_sample_count"] = len(restock_interval_samples) - len(valid_restock_intervals)
        prediction["note"] = (
            "Item is still in stock, so the baseline uses intervals between qualified restocks. "
            "It will switch to depletion-anchored timing after sellout."
        )

    if samples and anchor is not None and typical is not None:
        mad = _median_absolute_deviation(samples) or 0
        spread = max(60, int(mad * 1.5))
        estimate = int(anchor + typical)

        prediction.update({
            "estimate_timestamp": estimate,
            "window_start_timestamp": estimate - spread,
            "window_end_timestamp": estimate + spread,
            "sample_count": len(samples),
        })

        if median_restock_interval is not None:
            prediction["second_estimate_timestamp"] = int(estimate + median_restock_interval)

        relative_spread = (mad / typical) if typical else 1
        if len(samples) >= 20 and relative_spread <= 0.08:
            prediction["confidence"] = "high"
        elif len(samples) >= 8 and relative_spread <= 0.20:
            prediction["confidence"] = "medium"
        else:
            prediction["confidence"] = "low"

    visible_events = [event for event in events if event["timestamp"] >= cutoff]

    excluded_cycles = [cycle for cycle in completed_cycles if not cycle.get("valid_lifetime")]
    diagnostics = {
        "completed_cycles": len(completed_cycles),
        "valid_cycles": len(valid_cycles),
        "excluded_cycles": len(excluded_cycles),
        "valid_zero_to_restock_samples": len(valid_zero_waits),
        "excluded_zero_to_restock_samples": len(wait_samples) - len(valid_zero_waits),
        "valid_restock_interval_samples": len(valid_restock_intervals),
        "excluded_restock_interval_samples": len(restock_interval_samples) - len(valid_restock_intervals),
        "bridged_tiny_restock_count": sum(
            sample.get("bridged_tiny_restock_count", 0) for sample in wait_samples
        ),
        "max_allowed_collection_gap_seconds": 3 * 60 * 60,
        "tiny_restock_threshold_fraction": 0.10,
        "excluded_cycle_details": [
            {
                "restock_timestamp": cycle["restock_time"],
                "peak_quantity": cycle["peak_quantity"],
                "depletion_timestamp": cycle["depletion_time"],
                "reasons": cycle["exclusion_reasons"],
            }
            for cycle in excluded_cycles[-10:]
        ],
        "excluded_wait_details": [
            {
                "from_depletion": sample["from_depletion"],
                "to_restock": sample["to_restock"],
                "seconds": sample["seconds"],
                "bridged_tiny_restock_count": sample.get("bridged_tiny_restock_count", 0),
                "reasons": sample["exclusion_reasons"],
            }
            for sample in wait_samples
            if not sample["valid"]
        ][-10:],
    }

    return {
        "current_stock": current_stock,
        "latest_timestamp": latest_timestamp,
        "latest_time_str": _format_datetime(latest_timestamp),
        "observed_restocks": len(all_restock_times),
        "completed_cycles": len(completed_cycles),
        "valid_cycles": len(valid_cycles),
        "excluded_cycles": len(excluded_cycles),
        "last_restock_timestamp": last_restock,
        "last_restock_str": _format_datetime(last_restock),
        "last_depletion_timestamp": last_depletion,
        "last_depletion_str": _format_datetime(last_depletion),
        "last_peak_quantity": last_peak_quantity,
        "last_peak_timestamp": last_peak_time,
        "last_peak_str": _format_datetime(last_peak_time),
        "avg_lifetime_seconds": avg_lifetime,
        "avg_lifetime_str": _format_duration(avg_lifetime),
        "median_lifetime_seconds": median_lifetime,
        "median_lifetime_str": _format_duration(median_lifetime),
        "lifetime_samples": len(valid_lifetimes),
        "avg_zero_to_restock_seconds": avg_zero_wait,
        "avg_zero_to_restock_str": _format_duration(avg_zero_wait),
        "median_zero_to_restock_seconds": median_zero_wait,
        "median_zero_to_restock_str": _format_duration(median_zero_wait),
        "zero_to_restock_samples": len(valid_zero_waits),
        "avg_restock_interval_seconds": avg_restock_interval,
        "avg_restock_interval_str": _format_duration(avg_restock_interval),
        "median_restock_interval_seconds": median_restock_interval,
        "median_restock_interval_str": _format_duration(median_restock_interval),
        "restock_interval_samples": len(valid_restock_intervals),
        "events": visible_events,
        "prediction": prediction,
        "diagnostics": diagnostics,
    }

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