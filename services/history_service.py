import sqlite3
import time
import statistics
import threading
from pathlib import Path

from services.yata_api import get_country_stock

DB_PATH = Path(__file__).parent.parent / "data" / "stock_history.db"

_DB_INIT_LOCK = threading.Lock()
_DB_READY = False

# Missing successful poll coverage longer than this is a real collection gap.
GENERIC_COLLECTION_GAP_SECONDS = 180



def _connect():
    """
    Open SQLite with a real busy timeout.

    Torn Fren intentionally has multiple processes touching this DB at once:
    poller, web server, Discord bot, and offline prediction labs.  A default
    SQLite connection can fail immediately when one of those processes happens
    to be committing.  Waiting briefly is safer than treating a normal
    millisecond-scale writer collision as a fatal error.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    """
    Initialize schema once per Python process.

    IMPORTANT: this function no longer reconciles collection gaps.  Gap
    reconciliation is a write operation and used to run from every read helper,
    which could make an offline analysis collide with the 30-second poller.
    The poller reconciles gaps after heartbeat writes, and the explicit
    reconcile_collection_gaps() diagnostic still performs it on demand.
    """
    global _DB_READY

    if _DB_READY:
        return

    with _DB_INIT_LOCK:
        if _DB_READY:
            return

        with _connect() as conn:
            # WAL is persistent for the database and is much friendlier to the
            # poller + web + Discord + analysis read/write pattern.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")

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
                    source TEXT NOT NULL,
                    success INTEGER NOT NULL DEFAULT 1,
                    error TEXT,
                    mode TEXT
                )
            """)

            heartbeat_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(poll_heartbeats)").fetchall()
            }
            if "success" not in heartbeat_columns:
                conn.execute("ALTER TABLE poll_heartbeats ADD COLUMN success INTEGER NOT NULL DEFAULT 1")
            if "error" not in heartbeat_columns:
                conn.execute("ALTER TABLE poll_heartbeats ADD COLUMN error TEXT")
            if "mode" not in heartbeat_columns:
                conn.execute("ALTER TABLE poll_heartbeats ADD COLUMN mode TEXT")

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_poll_heartbeats_timestamp
                ON poll_heartbeats (timestamp)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS collection_gaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_timestamp INTEGER NOT NULL,
                    end_timestamp INTEGER,
                    reason TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    closed_at INTEGER,
                    UNIQUE(start_timestamp, reason)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_collection_gaps_range
                ON collection_gaps (start_timestamp, end_timestamp)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS prediction_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at INTEGER NOT NULL,
                    country TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    method TEXT NOT NULL,
                    model_name TEXT,
                    model_version TEXT,
                    anchor_type TEXT,
                    anchor_timestamp INTEGER NOT NULL,
                    estimate_timestamp INTEGER NOT NULL,
                    window_start_timestamp INTEGER NOT NULL,
                    window_end_timestamp INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL DEFAULT 0,
                    excluded_sample_count INTEGER NOT NULL DEFAULT 0,
                    confidence TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    actual_restock_timestamp INTEGER,
                    signed_error_seconds INTEGER,
                    absolute_error_seconds INTEGER,
                    window_hit INTEGER,
                    outside_window_seconds INTEGER,
                    data_valid INTEGER,
                    validation_reason TEXT,
                    resolved_at INTEGER,
                    UNIQUE(country, item_name, method, anchor_timestamp)
                )
            """)

            audit_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(prediction_audits)").fetchall()
            }
            if "model_name" not in audit_columns:
                conn.execute("ALTER TABLE prediction_audits ADD COLUMN model_name TEXT")
            if "model_version" not in audit_columns:
                conn.execute("ALTER TABLE prediction_audits ADD COLUMN model_version TEXT")
            if "anchor_type" not in audit_columns:
                conn.execute("ALTER TABLE prediction_audits ADD COLUMN anchor_type TEXT")
            if "outside_window_seconds" not in audit_columns:
                conn.execute("ALTER TABLE prediction_audits ADD COLUMN outside_window_seconds INTEGER")

            conn.execute("""
                UPDATE prediction_audits
                SET model_name = COALESCE(model_name, 'baseline_median'),
                    model_version = COALESCE(model_version, 'v1'),
                    anchor_type = COALESCE(
                        anchor_type,
                        CASE
                            WHEN method LIKE '%depletion%' THEN 'depletion'
                            WHEN method LIKE '%restock%' THEN 'restock'
                            ELSE 'unknown'
                        END
                    )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prediction_audits_pending
                ON prediction_audits (country, item_name, status, created_at)
            """)

        _DB_READY = True

def _group_contiguous_timestamps(timestamps, max_break_seconds: int = 300):
    """Group repeated collector failures into distinct outage incidents."""
    if not timestamps:
        return []
    groups = [[int(timestamps[0])]]
    for raw_ts in timestamps[1:]:
        ts = int(raw_ts)
        if ts - groups[-1][-1] > max_break_seconds:
            groups.append([ts])
        else:
            groups[-1].append(ts)
    return groups


def _reconcile_known_collection_gaps_conn(conn):
    """
    Detect the September 2026 changed_items collector failure from its own
    heartbeat diagnostics and persist it as an explicit collection gap.

    The buggy poller wrote a success heartbeat immediately before save failure,
    so ordinary success-heartbeat continuity cannot identify this outage.  A
    clean recovery is the first later successful poll-cycle heartbeat that does
    NOT have a changed_items failure at the same time.
    """
    failure_rows = conn.execute(
        """
        SELECT timestamp
        FROM poll_heartbeats
        WHERE mode = 'poll-cycle'
          AND success = 0
          AND error LIKE '%changed_items%not defined%'
        ORDER BY timestamp ASC
        """
    ).fetchall()
    failure_timestamps = [int(row[0]) for row in failure_rows]
    if not failure_timestamps:
        return

    now = int(time.time())
    reason = "changed_items NameError prevented stock_history commits"

    for group in _group_contiguous_timestamps(failure_timestamps):
        start_ts = group[0]
        last_failure_ts = group[-1]

        # Find the first successful heartbeat after the failure run that is not
        # paired with the same changed_items exception.  New poller versions only
        # write success after save_all_snapshots() commits, so this timestamp is
        # the first trustworthy recovery observation.
        recovery = conn.execute(
            """
            SELECT h.timestamp
            FROM poll_heartbeats h
            WHERE h.mode = 'poll-cycle'
              AND h.success = 1
              AND h.timestamp > ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM poll_heartbeats e
                  WHERE e.mode = 'poll-cycle'
                    AND e.success = 0
                    AND e.error LIKE '%changed_items%not defined%'
                    AND ABS(e.timestamp - h.timestamp) <= 2
              )
            ORDER BY h.timestamp ASC
            LIMIT 1
            """,
            (last_failure_ts,),
        ).fetchone()
        end_ts = int(recovery[0]) if recovery else None

        conn.execute(
            """
            INSERT OR IGNORE INTO collection_gaps
                (start_timestamp, end_timestamp, reason, created_at, closed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (start_ts, end_ts, reason, now, now if end_ts is not None else None),
        )

        if end_ts is not None:
            conn.execute(
                """
                UPDATE collection_gaps
                SET end_timestamp = COALESCE(end_timestamp, ?),
                    closed_at = COALESCE(closed_at, ?)
                WHERE start_timestamp = ? AND reason = ?
                """,
                (end_ts, now, start_ts, reason),
            )



def _reconcile_heartbeat_collection_gaps_conn(conn):
    """
    Persist generic collector outages from successful poll heartbeat continuity.

    This covers PC sleep, process crashes, VM/server restarts, internet loss,
    provider downtime, and any other period where Torn Fren could not verify
    foreign stock.  The first recovery snapshot is intentionally inside the
    gap because it reveals the current state, not when transitions occurred.
    """
    rows = conn.execute(
        """
        SELECT timestamp
        FROM poll_heartbeats
        WHERE mode = 'poll-cycle'
          AND success = 1
        ORDER BY timestamp ASC
        """
    ).fetchall()

    timestamps = [int(row[0]) for row in rows]
    if len(timestamps) < 2:
        return

    now = int(time.time())
    for previous_ts, recovery_ts in zip(timestamps, timestamps[1:]):
        elapsed = recovery_ts - previous_ts
        if elapsed <= GENERIC_COLLECTION_GAP_SECONDS:
            continue

        reason = (
            f"collector heartbeat gap ({elapsed}s without verified successful polling)"
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO collection_gaps
                (start_timestamp, end_timestamp, reason, created_at, closed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (previous_ts, recovery_ts, reason, now, now),
        )


def get_collector_recovery_status(now_timestamp=None):
    """
    Return whether the collector is currently stale enough that startup
    prediction/audit seeding should be suppressed until a clean poll recovers.

    This is read-only. The actual gap is persisted when the next successful
    heartbeat is recorded.
    """
    init_db()
    now = int(now_timestamp or time.time())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT timestamp
            FROM poll_heartbeats
            WHERE mode = 'poll-cycle'
              AND success = 1
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return {
            "stale": False,
            "last_success_timestamp": None,
            "age_seconds": None,
            "threshold_seconds": GENERIC_COLLECTION_GAP_SECONDS,
        }

    last_success = int(row[0])
    age = max(0, now - last_success)
    return {
        "stale": age > GENERIC_COLLECTION_GAP_SECONDS,
        "last_success_timestamp": last_success,
        "age_seconds": age,
        "threshold_seconds": GENERIC_COLLECTION_GAP_SECONDS,
    }

def reconcile_collection_gaps():
    """Public helper used by diagnostics/tests; safe to call repeatedly."""
    init_db()
    with _connect() as conn:
        _reconcile_known_collection_gaps_conn(conn)
        _reconcile_heartbeat_collection_gaps_conn(conn)


def get_collection_gaps():
    """Return known bad collector intervals, oldest first."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT start_timestamp, end_timestamp, reason
            FROM collection_gaps
            ORDER BY start_timestamp ASC
            """
        ).fetchall()
    return [
        {"start_timestamp": row[0], "end_timestamp": row[1], "reason": row[2]}
        for row in rows
    ]


def _collection_gap_overlap(start_timestamp: int, end_timestamp: int):
    """
    Return a known bad collector interval overlapping [start, end].

    Boundaries are inclusive on purpose.  The first recovery snapshot tells us
    the current state, but not when a restock/depletion happened during the
    outage, so transitions stamped at the recovery timestamp are not valid
    training ground truth either.
    """
    init_db()
    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT start_timestamp, end_timestamp, reason
            FROM collection_gaps
            WHERE start_timestamp <= ?
              AND COALESCE(end_timestamp, ?) >= ?
            ORDER BY start_timestamp ASC
            LIMIT 1
            """,
            (int(end_timestamp), now, int(start_timestamp)),
        ).fetchone()
    if row is None:
        return None
    return {
        "start_timestamp": int(row[0]),
        "end_timestamp": int(row[1]) if row[1] is not None else None,
        "reason": row[2],
    }



def _prediction_anchor_is_currently_trustworthy(anchor_timestamp: int, now_timestamp: int):
    """
    A live prediction anchor must have uninterrupted trustworthy collection
    from the anchor through "now".  Historical samples can remain valid while
    the CURRENT anchor is stale because a later collection outage occurred.

    This is intentionally stricter than validating the historical cycle itself.
    Example: if an item depleted at 2:58 PM, collection failed from 3:16-9:09 PM,
    and the item is still observed at zero after recovery, we do NOT know whether
    one or more restock/depletion cycles happened inside the outage.  The 2:58 PM
    depletion therefore cannot be used as today's live countdown anchor.
    """
    if anchor_timestamp is None:
        return False, "missing anchor"

    overlap = _collection_gap_overlap(int(anchor_timestamp), int(now_timestamp))
    if overlap:
        return False, (
            "current prediction anchor crosses a known collection outage "
            f"({_format_datetime(overlap['start_timestamp'])} -> "
            f"{_format_datetime(overlap['end_timestamp'])})"
        )

    return True, None

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
    changed_items = []

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
    changed_items = []

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
            changed_items.append(item_name)

    print(f"{country}: inserted {inserted}, skipped {skipped} unchanged")
    return changed_items


def record_poll_heartbeat(success: bool, source: str = "none", error: str = None):
    """
    Record one row for every poll attempt.

    A successful heartbeat means the provider fetch AND database save completed.
    On success, detect whether this poll is recovering from a >3 minute period
    without verified collection.  The recovery snapshot is included in the
    collection gap so it may update current state without being treated as exact
    event timing or model ground truth.

    Returns metadata so poller.py can suppress downstream audit/model work on
    the recovery burst.
    """
    init_db()
    now = int(time.time())

    with _connect() as conn:
        previous_success = conn.execute(
            """
            SELECT timestamp
            FROM poll_heartbeats
            WHERE mode = 'poll-cycle'
              AND success = 1
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()
        previous_success_ts = int(previous_success[0]) if previous_success else None

        conn.execute(
            """
            INSERT INTO poll_heartbeats (timestamp, source, success, error, mode)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now, source or "none", 1 if success else 0, error, "poll-cycle"),
        )

        _reconcile_known_collection_gaps_conn(conn)
        _reconcile_heartbeat_collection_gaps_conn(conn)

    elapsed = (
        now - previous_success_ts
        if success and previous_success_ts is not None
        else None
    )
    recovered_from_gap = bool(
        success
        and elapsed is not None
        and elapsed > GENERIC_COLLECTION_GAP_SECONDS
    )

    return {
        "timestamp": now,
        "success": bool(success),
        "previous_success_timestamp": previous_success_ts,
        "elapsed_since_success_seconds": elapsed,
        "recovered_from_gap": recovered_from_gap,
        "gap_start_timestamp": previous_success_ts if recovered_from_gap else None,
        "gap_end_timestamp": now if recovered_from_gap else None,
    }


def save_all_snapshots(export: dict):
    """
    Save every country in one export object — one API call feeds every
    country's row inserts, instead of calling the API once per country.

    Heartbeats are recorded by poller.py for every attempt, including failures.
    """
    init_db()

    source = export.get("source", "unknown")
    stocks = export.get("stocks", {})

    changed_by_country = {}
    for country, country_data in stocks.items():
        changed = save_snapshot_from_export(country, country_data, source)
        if changed:
            changed_by_country[country] = changed

    return changed_by_country


def _get_all_item_rows_with_source(country: str, item_name: str):
    init_db()
    with _connect() as conn:
        return conn.execute(
            """
            SELECT timestamp, quantity, source
            FROM stock_history
            WHERE country = ? AND LOWER(item_name) = LOWER(?)
            ORDER BY timestamp ASC
            """,
            (country, item_name),
        ).fetchall()


def _suppress_provider_bounces(rows, max_bounce_seconds: int = 180):
    """
    Remove obvious one-poll provider disagreement from analysis/display without
    deleting anything from SQLite.

    Example seen in Japan Xanax:
      16:20:31 2386 prometheus
      16:21:02    0 yata       <- stale zero
      16:21:34 2062 yata

    The middle zero is suppressed because positive stock exists immediately on
    both sides and the source switched.  The inverse (a one-poll positive spike
    between zeros) is handled as well.
    """
    if len(rows) < 3:
        return list(rows), []

    suppressed = set()
    anomalies = []

    for i in range(1, len(rows) - 1):
        prev_ts, prev_qty, prev_source = rows[i - 1]
        ts, qty, source = rows[i]
        next_ts, next_qty, next_source = rows[i + 1]

        prev_gap = ts - prev_ts
        next_gap = next_ts - ts
        if prev_gap > max_bounce_seconds or next_gap > max_bounce_seconds:
            continue

        source_disagreement = source != prev_source or source != next_source
        if not source_disagreement:
            continue

        # One stale zero inside a live batch.
        if qty == 0 and prev_qty > 0 and next_qty > 0:
            suppressed.add(i)
            anomalies.append({
                "type": "provider_zero_bounce",
                "timestamp": ts,
                "quantity": qty,
                "source": source,
                "previous_source": prev_source,
                "next_source": next_source,
            })

        # One stale positive reading while both surrounding observations are zero.
        elif qty > 0 and prev_qty == 0 and next_qty == 0:
            suppressed.add(i)
            anomalies.append({
                "type": "provider_positive_bounce",
                "timestamp": ts,
                "quantity": qty,
                "source": source,
                "previous_source": prev_source,
                "next_source": next_source,
            })

    cleaned = [row for i, row in enumerate(rows) if i not in suppressed]
    return cleaned, anomalies



def get_stock_catalog():
    """
    Return the countries/items that actually exist in local collected history.

    This intentionally comes from Torn Fren's own database rather than a hard-
    coded item list so the hosted graph selector always reflects what the poller
    has seen.
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT country, item_name, MAX(timestamp) AS latest_timestamp
            FROM stock_history
            GROUP BY country, item_name
            ORDER BY country ASC, item_name COLLATE NOCASE ASC
            """
        ).fetchall()

    by_country = {}
    for country, item_name, latest_timestamp in rows:
        country = (country or "").lower()
        if not country or not item_name:
            continue
        by_country.setdefault(country, []).append({
            "item_name": item_name,
            "latest_timestamp": int(latest_timestamp) if latest_timestamp is not None else None,
        })

    return {
        "countries": [
            {
                "country": country,
                "items": items,
            }
            for country, items in sorted(by_country.items())
        ]
    }


def get_recent_completed_cycles(country, item_name, limit=3):
    """
    Return the latest qualified completed cycles for player-facing /history.

    A completed stock cycle is restock -> depletion. The empty wait shown for
    that cycle is the validated depletion -> NEXT restock sample that follows it.
    Discord intentionally caps this at 3 cycles.
    """
    init_db()
    limit = max(1, min(int(limit or 3), 3))

    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, suppressed = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]

    if not rows:
        return {
            "country": country.lower(),
            "item_name": item_name,
            "cycles": [],
            "typical": {},
            "suppressed_provider_bounces": suppressed,
        }

    cycles, _active_cycle, wait_samples = _build_validated_cycles(rows)

    # Map each VALID zero->restock sample by the depletion that started it.
    wait_by_depletion = {
        int(sample["from_depletion"]): sample
        for sample in wait_samples
        if sample.get("valid")
        and sample.get("from_depletion") is not None
        and sample.get("to_restock") is not None
        and sample.get("seconds") is not None
    }

    qualified = []
    for cycle in cycles:
        if not cycle.get("complete"):
            continue
        if cycle.get("tiny_restock"):
            continue
        if not cycle.get("valid_lifetime"):
            continue

        depletion = cycle.get("depletion_time")
        lifetime = cycle.get("lifetime_seconds")
        wait = wait_by_depletion.get(int(depletion)) if depletion is not None else None

        # /history is specifically showing a fully observed completed cycle PLUS
        # the empty period after it, so require the next valid restock too.
        if depletion is None or lifetime is None or wait is None:
            continue

        qualified.append({
            "restock_time": cycle.get("restock_time"),
            "depletion_time": depletion,
            "next_restock_time": wait.get("to_restock"),
            "zero_wait_seconds": wait.get("seconds"),
            "stock_lifetime_seconds": lifetime,
            "peak_quantity": cycle.get("peak_quantity"),
            "restock_quantity": cycle.get("first_seen_quantity"),
        })

    recent = list(reversed(qualified[-limit:]))

    def _median(values):
        vals = sorted(float(v) for v in values if v is not None)
        if not vals:
            return None
        n = len(vals)
        mid = n // 2
        return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2

    return {
        "country": country.lower(),
        "item_name": item_name,
        "cycles": recent,
        "typical": {
            "median_zero_wait_seconds": _median(
                c.get("zero_wait_seconds") for c in qualified
            ),
            "median_stock_lifetime_seconds": _median(
                c.get("stock_lifetime_seconds") for c in qualified
            ),
            "median_peak_quantity": _median(
                c.get("peak_quantity") for c in qualified
            ),
            "valid_cycle_count": len(qualified),
        },
        "suppressed_provider_bounces": suppressed,
    }


def get_item_history_since(country: str, item_name: str, hours: float = 24):
    """
    Return cleaned stock history for graphing, oldest -> newest.

    Raw rows stay untouched in SQLite. Obvious one-poll cross-provider bounces are
    suppressed only in the returned view so a stale provider reading cannot draw
    a fake double restock/depletion on the chart.
    """
    init_db()
    hours = max(float(hours), 1 / 60)
    now = int(time.time())
    cutoff = now - int(hours * 3600)

    all_rows = _get_all_item_rows_with_source(country, item_name)
    cleaned_rows, _ = _suppress_provider_bounces(all_rows)

    previous = None
    visible = []
    for ts, qty, source in cleaned_rows:
        if ts < cutoff:
            previous = (ts, qty, source)
        elif ts <= now:
            visible.append((ts, qty, source))

    result = []
    if previous is not None:
        result.append({
            "timestamp": cutoff,
            "quantity": previous[1],
            "cost": None,
            "source": previous[2],
            "anchor": True,
        })

    for ts, qty, source in visible:
        result.append({
            "timestamp": ts,
            "quantity": qty,
            "cost": None,
            "source": source,
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


def _get_poll_cycle_start_timestamp():
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT MIN(timestamp)
            FROM poll_heartbeats
            WHERE mode = 'poll-cycle'
            """
        ).fetchone()
    return row[0] if row else None


def _get_successful_poll_timestamps(start_timestamp: int, end_timestamp: int):
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT timestamp
            FROM poll_heartbeats
            WHERE mode = 'poll-cycle'
              AND success = 1
              AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
            """,
            (start_timestamp, end_timestamp),
        ).fetchall()
    return [row[0] for row in rows]


def _historical_observation_timestamps(start_timestamp: int, end_timestamp: int):
    """Best-effort fallback for periods before per-poll heartbeat support."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT timestamp
            FROM stock_history
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
            """,
            (start_timestamp, end_timestamp),
        ).fetchall()
    return [row[0] for row in rows]


def _max_gap_from_timestamps(start_timestamp, end_timestamp, timestamps):
    points = [start_timestamp, *timestamps, end_timestamp]
    points = sorted(set(points))
    if len(points) < 2:
        return max(0, end_timestamp - start_timestamp)
    return max(points[i] - points[i - 1] for i in range(1, len(points)))


def _collection_coverage(start_timestamp: int, end_timestamp: int):
    """
    Evaluate whether the collector was continuously observing an interval.

    After poll-cycle heartbeats begin, continuity is based on successful poll
    heartbeats, with a 3-minute tolerance around the expected 30-second cadence.
    Older history falls back to the prior conservative stock-activity heuristic
    and uses the old 3-hour tolerance because exact collector uptime is unknowable.
    """
    if end_timestamp <= start_timestamp:
        return {
            "valid": True,
            "max_gap_seconds": 0,
            "allowed_gap_seconds": 180,
            "method": "poll-heartbeat",
        }

    known_gap = _collection_gap_overlap(start_timestamp, end_timestamp)
    if known_gap is not None:
        gap_end = known_gap["end_timestamp"] or int(time.time())
        overlap_start = max(int(start_timestamp), known_gap["start_timestamp"])
        overlap_end = min(int(end_timestamp), gap_end)
        return {
            "valid": False,
            "max_gap_seconds": max(0, overlap_end - overlap_start),
            "allowed_gap_seconds": 0,
            "method": "known-collection-gap",
            "reason": known_gap["reason"],
            "gap_start_timestamp": known_gap["start_timestamp"],
            "gap_end_timestamp": known_gap["end_timestamp"],
        }

    poll_cycle_start = _get_poll_cycle_start_timestamp()

    # Entire interval predates reliable per-poll heartbeats.
    if poll_cycle_start is None or end_timestamp < poll_cycle_start:
        timestamps = _historical_observation_timestamps(start_timestamp, end_timestamp)
        gap = _max_gap_from_timestamps(start_timestamp, end_timestamp, timestamps)
        return {
            "valid": gap <= 3 * 60 * 60,
            "max_gap_seconds": gap,
            "allowed_gap_seconds": 3 * 60 * 60,
            "method": "historical-fallback",
        }

    # Interval is fully covered by modern heartbeat data.
    if start_timestamp >= poll_cycle_start:
        timestamps = _get_successful_poll_timestamps(start_timestamp, end_timestamp)
        gap = _max_gap_from_timestamps(start_timestamp, end_timestamp, timestamps)
        return {
            "valid": gap <= 180,
            "max_gap_seconds": gap,
            "allowed_gap_seconds": 180,
            "method": "poll-heartbeat",
        }

    # Interval crosses the migration boundary: validate each side by its own rule.
    old_timestamps = _historical_observation_timestamps(start_timestamp, poll_cycle_start)
    old_gap = _max_gap_from_timestamps(start_timestamp, poll_cycle_start, old_timestamps)
    new_timestamps = _get_successful_poll_timestamps(poll_cycle_start, end_timestamp)
    new_gap = _max_gap_from_timestamps(poll_cycle_start, end_timestamp, new_timestamps)
    return {
        "valid": old_gap <= 3 * 60 * 60 and new_gap <= 180,
        "max_gap_seconds": max(old_gap, new_gap),
        "allowed_gap_seconds": None,
        "method": "mixed-heartbeat/fallback",
        "historical_max_gap_seconds": old_gap,
        "heartbeat_max_gap_seconds": new_gap,
    }


def _max_collection_gap_seconds(start_timestamp: int, end_timestamp: int):
    return _collection_coverage(start_timestamp, end_timestamp)["max_gap_seconds"]

def _leave_one_out_mean(values, index):
    others = [value for i, value in enumerate(values) if i != index]
    if not others:
        return None
    return statistics.mean(others)


def _build_validated_cycles(rows):
    """
    Convert raw stock changes into restock cycles and qualify each cycle for use
    in prediction statistics.

    A completed cycle is excluded when collector heartbeat coverage shows a
    genuine collection outage, or when its observed peak is a tiny anomaly.

    Long refill/zero periods are valid. Duration itself is never an exclusion
    reason; only missing collector coverage is.
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

        coverage = _collection_coverage(
            cycle["restock_time"],
            cycle["depletion_time"],
        )
        cycle["max_collection_gap_seconds"] = coverage["max_gap_seconds"]
        cycle["coverage_method"] = coverage["method"]

        if not coverage["valid"]:
            detail = coverage.get("reason") or f"failed {coverage['method']} continuity"
            cycle["exclusion_reasons"].append(
                f"collector coverage invalid ({detail}); "
                f"overlap/gap {_format_duration(coverage['max_gap_seconds'])}"
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
        coverage = _collection_coverage(
            previous["depletion_time"],
            current_cycle["restock_time"],
        )
        gap = coverage["max_gap_seconds"]

        # Count any tiny cycles that occurred between these two normal boundaries.
        bridged_tiny_count = sum(
            1
            for cycle in completed_cycles
            if cycle.get("tiny_restock")
            and previous["depletion_time"] < cycle["restock_time"] < current_cycle["restock_time"]
        )

        reasons = []
        if not coverage["valid"]:
            reasons.append(
                f"collector coverage gap {_format_duration(gap)} failed {coverage['method']} continuity"
            )

        # The outgoing depletion must itself be trustworthy. A later collection
        # gap inside the incoming cycle does not invalidate the restock timestamp.
        if not previous.get("valid_lifetime"):
            reasons.append("previous depletion/cycle was not reliable")

        wait_samples.append({
            "from_depletion": previous["depletion_time"],
            "to_restock": current_cycle["restock_time"],
            "seconds": wait_seconds,
            "max_collection_gap_seconds": gap,
            "coverage_method": coverage["method"],
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
    raw_rows_with_source = _get_all_item_rows_with_source(country, item_name)
    cleaned_rows_with_source, provider_bounces = _suppress_provider_bounces(raw_rows_with_source)
    rows = [(ts, qty) for ts, qty, _source in cleaned_rows_with_source]
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
        coverage = _collection_coverage(
            previous["restock_time"],
            current_cycle["restock_time"],
        )
        gap = coverage["max_gap_seconds"]
        reasons = []
        if not coverage["valid"]:
            reasons.append(
                f"collector coverage gap {_format_duration(gap)} failed {coverage['method']} continuity"
            )

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
            "coverage_method": coverage["method"],
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
        "model_name": "baseline_median",
        "model_version": "v1",
        "anchor_type": None,
        "anchor_timestamp": None,
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
        prediction["anchor_type"] = "depletion"
        prediction["excluded_sample_count"] = len(wait_samples) - len(valid_zero_waits)
        prediction["note"] = (
            "Uses qualified depletion→restock waits. Long refill periods are allowed; "
            "only heartbeat-proven collection outages or tiny anomalous restocks are excluded."
        )
    elif current_stock > 0 and last_restock is not None and valid_restock_intervals:
        samples = valid_restock_intervals
        anchor = last_restock
        typical = median_restock_interval
        prediction["method"] = "validated restock-interval median"
        prediction["anchor_type"] = "restock"
        prediction["excluded_sample_count"] = len(restock_interval_samples) - len(valid_restock_intervals)
        prediction["note"] = (
            "Item is still in stock, so the baseline uses intervals between qualified restocks. "
            "It will switch to depletion-anchored timing after sellout."
        )

    # Historical samples may be perfectly valid while the CURRENT live anchor is
    # no longer trustworthy because a known collection outage happened after it.
    # Never display a stale countdown/leave-by time in that situation.
    if samples and anchor is not None and typical is not None:
        anchor_valid, anchor_reason = _prediction_anchor_is_currently_trustworthy(anchor, now)
        if not anchor_valid:
            prediction.update({
                "method": "waiting for clean post-outage anchor",
                "anchor_type": prediction.get("anchor_type"),
                "anchor_timestamp": None,
                "estimate_timestamp": None,
                "window_start_timestamp": None,
                "window_end_timestamp": None,
                "second_estimate_timestamp": None,
                "sample_count": len(samples),
                "confidence": "unavailable",
                "note": (
                    "Historical timing samples are still usable, but the latest live "
                    f"anchor is not trustworthy: {anchor_reason}. Wait for the next "
                    "clean restock/depletion event before using a departure countdown."
                ),
            })
            samples = None
            anchor = None
            typical = None

    if samples and anchor is not None and typical is not None:
        mad = _median_absolute_deviation(samples) or 0
        spread = max(60, int(mad * 1.5))
        estimate = int(anchor + typical)

        prediction.update({
            "anchor_timestamp": int(anchor),
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
        "heartbeat_gap_tolerance_seconds": 180,
        "historical_fallback_gap_tolerance_seconds": 3 * 60 * 60,
        "tiny_restock_threshold_fraction": 0.10,
        "suppressed_provider_bounce_count": len(provider_bounces),
        "provider_bounces": provider_bounces[-20:],
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

    with _connect() as conn:
        latest_successful_poll = conn.execute(
            """
            SELECT timestamp, source
            FROM poll_heartbeats
            WHERE success = 1
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()

    collector_last_success_timestamp = int(latest_successful_poll[0]) if latest_successful_poll else None
    collector_last_success_source = latest_successful_poll[1] if latest_successful_poll else None

    return {
        "collector_last_success_timestamp": collector_last_success_timestamp,
        "collector_last_success_source": collector_last_success_source,
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


def _normal_completed_cycles_for_audit(country: str, item_name: str):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, _ = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    if not rows:
        return []
    cycles, _, _ = _build_validated_cycles(rows)
    return [
        cycle for cycle in cycles
        if cycle.get("complete") and not cycle.get("tiny_restock")
    ]


def resolve_prediction_audits(country: str, item_name: str):
    """
    Resolve frozen predictions against the next qualified real restock.

    Exact error and window-hit are only considered trustworthy when successful
    poll-heartbeat coverage is continuous from prediction creation through the
    actual restock. Long item refill times are allowed; elapsed duration itself
    is never a reason to reject a result.
    """
    init_db()
    cycles = _normal_completed_cycles_for_audit(country, item_name)
    if not cycles:
        return 0

    with _connect() as conn:
        pending = conn.execute(
            """
            SELECT id, created_at, anchor_timestamp, estimate_timestamp,
                   window_start_timestamp, window_end_timestamp
            FROM prediction_audits
            WHERE country = ?
              AND LOWER(item_name) = LOWER(?)
              AND status = 'pending'
            ORDER BY created_at ASC
            """,
            (country, item_name),
        ).fetchall()

        resolved = 0
        for audit_id, created_at, anchor_timestamp, estimate, window_start, window_end in pending:
            threshold = max(int(created_at), int(anchor_timestamp))
            actual_cycle = next(
                (cycle for cycle in cycles if cycle["restock_time"] > threshold),
                None,
            )
            if actual_cycle is None:
                continue

            actual = int(actual_cycle["restock_time"])
            signed_error = actual - int(estimate)
            absolute_error = abs(signed_error)
            window_hit = int(int(window_start) <= actual <= int(window_end))
            outside_window = 0
            if actual < int(window_start):
                outside_window = int(window_start) - actual
            elif actual > int(window_end):
                outside_window = actual - int(window_end)

            # The prediction depends on its anchor.  Validate from the earlier
            # of anchor creation and audit creation so a recovery-stamped anchor
            # cannot be scored as trustworthy merely because the audit row was
            # written a few seconds after the collector recovered.
            coverage_start = min(int(created_at), int(anchor_timestamp))
            coverage = _collection_coverage(coverage_start, actual)
            data_valid = int(bool(coverage["valid"]))
            validation_reason = (
                f"coverage valid via {coverage['method']} (max gap {_format_duration(coverage['max_gap_seconds'])})"
                if data_valid
                else f"coverage invalid via {coverage['method']} (max gap {_format_duration(coverage['max_gap_seconds'])})"
            )

            conn.execute(
                """
                UPDATE prediction_audits
                SET status = 'resolved',
                    actual_restock_timestamp = ?,
                    signed_error_seconds = ?,
                    absolute_error_seconds = ?,
                    window_hit = ?,
                    outside_window_seconds = ?,
                    data_valid = ?,
                    validation_reason = ?,
                    resolved_at = ?
                WHERE id = ?
                """,
                (
                    actual,
                    signed_error,
                    absolute_error,
                    window_hit,
                    outside_window,
                    data_valid,
                    validation_reason,
                    int(time.time()),
                    audit_id,
                ),
            )
            resolved += 1

    return resolved


def record_prediction_audit(country: str, item_name: str):
    """Freeze the currently displayed baseline prediction for later scoring."""
    init_db()
    analysis = get_stock_graph_analysis(country, item_name, window_hours=24)
    if not analysis:
        return False

    prediction = analysis.get("prediction") or {}
    required = (
        prediction.get("anchor_timestamp"),
        prediction.get("estimate_timestamp"),
        prediction.get("window_start_timestamp"),
        prediction.get("window_end_timestamp"),
    )
    if any(value is None for value in required):
        return False

    model_name = prediction.get("model_name") or "baseline_median"
    model_version = prediction.get("model_version") or "v1"
    anchor_type = prediction.get("anchor_type") or "unknown"

    # Do not freeze a new audit if its anchor crosses a known collection gap.
    # We can still display the best available prediction to the user, but it is
    # not suitable as accuracy ground truth.
    anchor_coverage = _collection_coverage(
        int(prediction["anchor_timestamp"]),
        int(time.time()),
    )
    if not anchor_coverage["valid"]:
        return False

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO prediction_audits (
                created_at, country, item_name, method, model_name, model_version,
                anchor_type, anchor_timestamp, estimate_timestamp,
                window_start_timestamp, window_end_timestamp,
                sample_count, excluded_sample_count, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                country,
                item_name,
                prediction.get("method") or model_name,
                model_name,
                model_version,
                anchor_type,
                int(prediction["anchor_timestamp"]),
                int(prediction["estimate_timestamp"]),
                int(prediction["window_start_timestamp"]),
                int(prediction["window_end_timestamp"]),
                int(prediction.get("sample_count") or 0),
                int(prediction.get("excluded_sample_count") or 0),
                prediction.get("confidence"),
            ),
        )
        return cursor.rowcount > 0


def update_prediction_audits_for_item(country: str, item_name: str):
    resolved = resolve_prediction_audits(country, item_name)
    recorded = record_prediction_audit(country, item_name)
    return {"resolved": resolved, "recorded": recorded}


def seed_prediction_audits():
    """Seed one current prediction snapshot for known items if the audit table is empty."""
    init_db()
    with _connect() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM prediction_audits").fetchone()[0]
        if existing:
            return 0
        items = conn.execute(
            """
            SELECT DISTINCT country, item_name
            FROM stock_history
            ORDER BY country, item_name
            """
        ).fetchall()

    recorded = 0
    for country, item_name in items:
        try:
            if record_prediction_audit(country, item_name):
                recorded += 1
        except Exception as exc:
            print(f"Prediction audit seed skipped {country}/{item_name}: {exc}")
    return recorded


def get_prediction_accuracy_summary(country: str, item_name: str):
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT absolute_error_seconds, window_hit, outside_window_seconds,
                   signed_error_seconds
            FROM prediction_audits
            WHERE country = ?
              AND LOWER(item_name) = LOWER(?)
              AND status = 'resolved'
              AND data_valid = 1
            """,
            (country, item_name),
        ).fetchall()

    if not rows:
        return {
            "resolved_valid_predictions": 0,
            "median_absolute_error_seconds": None,
            "mean_absolute_error_seconds": None,
            "window_hit_rate": None,
            "median_outside_window_seconds": None,
            "early_predictions": 0,
            "late_predictions": 0,
        }

    errors = [row[0] for row in rows]
    hits = [row[1] for row in rows]
    misses = [row[2] for row in rows if not row[1]]
    signed = [row[3] for row in rows]
    return {
        "resolved_valid_predictions": len(rows),
        "median_absolute_error_seconds": statistics.median(errors),
        "mean_absolute_error_seconds": statistics.mean(errors),
        "window_hit_rate": sum(hits) / len(hits),
        "median_outside_window_seconds": statistics.median(misses) if misses else 0,
        "early_predictions": sum(1 for value in signed if value < 0),
        "late_predictions": sum(1 for value in signed if value > 0),
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