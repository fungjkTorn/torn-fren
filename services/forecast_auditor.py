import hashlib
import json
import time
from pathlib import Path

from services.history_service import (
    _build_validated_cycles,
    _collection_coverage,
    _connect,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
    init_db,
)


AUDITOR_VERSION = "forecast-audit-v1"
PROFILE_CACHE_FILE = Path(__file__).parent.parent / "data" / "prediction_v2_profiles.json"


def ensure_forecast_audit_schema():
    """Create the forecast-audit tables without touching existing history rows."""
    init_db()
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forecast_audit_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                country TEXT NOT NULL,
                item_name TEXT NOT NULL,
                source TEXT NOT NULL,
                auditor_version TEXT NOT NULL,
                status TEXT,
                current_stock INTEGER,
                active_prediction_number INTEGER,
                travel_reliability TEXT,
                model_evidence_tier TEXT,
                model_name TEXT,
                arrival_success_rate REAL,
                recent10_success_rate REAL,
                signature TEXT NOT NULL,
                UNIQUE(country, item_name, signature)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecast_runs_item_time
            ON forecast_audit_runs(country, item_name, created_at)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS forecast_audit_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                prediction_number INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                estimate_timestamp INTEGER,
                window_start_timestamp INTEGER,
                window_end_timestamp INTEGER,
                recommended_arrival_timestamp INTEGER,
                recommended_leave_by_timestamp INTEGER,
                projected INTEGER NOT NULL DEFAULT 0,
                usable_for_departure INTEGER NOT NULL DEFAULT 0,
                travel_reliability TEXT,
                model_name TEXT,
                method TEXT,
                arrival_offset_source TEXT,
                projection_depth INTEGER,

                status TEXT NOT NULL DEFAULT 'pending',
                actual_restock_timestamp INTEGER,
                actual_depletion_timestamp INTEGER,
                signed_error_seconds INTEGER,
                absolute_error_seconds INTEGER,
                window_hit INTEGER,
                outside_window_seconds INTEGER,
                arrival_hit INTEGER,
                ground_truth_valid INTEGER,
                validation_reason TEXT,
                resolved_at INTEGER,

                FOREIGN KEY(run_id) REFERENCES forecast_audit_runs(id),
                UNIQUE(run_id, prediction_number)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecast_points_pending
            ON forecast_audit_points(status, run_id, prediction_number)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_forecast_points_actual
            ON forecast_audit_points(actual_restock_timestamp)
        """)


def _forecast_signature(result):
    predictions = result.get("predictions") or []
    if not predictions:
        predictions = [
            p for p in (result.get("prediction_1"), result.get("prediction_2"))
            if p
        ]

    compact = {
        "status": result.get("status"),
        "active": (result.get("display_prediction") or {}).get("prediction_number"),
        "predictions": [
            {
                "n": p.get("prediction_number"),
                "estimate": p.get("estimate_timestamp"),
                "ws": p.get("window_start_timestamp"),
                "we": p.get("window_end_timestamp"),
                "arrival": p.get("recommended_arrival_timestamp"),
                "leave": p.get("recommended_leave_by_timestamp"),
                "projected": bool(p.get("projected")),
                "model": p.get("model_name"),
            }
            for p in predictions
        ],
    }
    raw = json.dumps(compact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def record_forecast_snapshot(country, item_name, result, source="live"):
    """
    Freeze one forecast chain for later scoring.

    Exact duplicate chains are ignored. Quantity changes alone do not create a
    new run; a new run appears only when the forecast/active target changes.
    """
    ensure_forecast_audit_schema()

    predictions = result.get("predictions") or []
    if not predictions:
        predictions = [
            p for p in (result.get("prediction_1"), result.get("prediction_2"))
            if p
        ]
    predictions = [
        p for p in predictions
        if p and p.get("prediction_number") is not None and p.get("estimate_timestamp")
    ]
    if not predictions:
        return {"recorded": False, "run_id": None, "points": 0}

    signature = _forecast_signature(result)
    now = int(time.time())
    active = result.get("display_prediction") or {}

    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO forecast_audit_runs (
                created_at, country, item_name, source, auditor_version,
                status, current_stock, active_prediction_number,
                travel_reliability, model_evidence_tier, model_name,
                arrival_success_rate, recent10_success_rate, signature
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                country.lower(),
                item_name,
                source,
                AUDITOR_VERSION,
                result.get("status"),
                result.get("current_stock"),
                active.get("prediction_number"),
                active.get("travel_reliability") or result.get("travel_reliability"),
                result.get("model_evidence_tier"),
                active.get("model_name") or result.get("model_name"),
                result.get("arrival_success_rate"),
                result.get("recent10_arrival_success_rate"),
                signature,
            ),
        )

        if cursor.rowcount == 0:
            row = conn.execute(
                """
                SELECT id FROM forecast_audit_runs
                WHERE country = ? AND item_name = ? AND signature = ?
                """,
                (country.lower(), item_name, signature),
            ).fetchone()
            return {
                "recorded": False,
                "run_id": int(row[0]) if row else None,
                "points": 0,
            }

        run_id = int(cursor.lastrowid)
        point_count = 0
        for p in predictions:
            conn.execute(
                """
                INSERT INTO forecast_audit_points (
                    run_id, prediction_number, created_at,
                    estimate_timestamp, window_start_timestamp, window_end_timestamp,
                    recommended_arrival_timestamp, recommended_leave_by_timestamp,
                    projected, usable_for_departure, travel_reliability,
                    model_name, method, arrival_offset_source, projection_depth
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    int(p.get("prediction_number") or 1),
                    now,
                    p.get("estimate_timestamp"),
                    p.get("window_start_timestamp"),
                    p.get("window_end_timestamp"),
                    p.get("recommended_arrival_timestamp"),
                    p.get("recommended_leave_by_timestamp"),
                    int(bool(p.get("projected"))),
                    int(bool(p.get("usable_for_departure"))),
                    p.get("travel_reliability"),
                    p.get("model_name"),
                    p.get("method"),
                    p.get("arrival_offset_source"),
                    p.get("projection_depth"),
                ),
            )
            point_count += 1

    return {"recorded": True, "run_id": run_id, "points": point_count}


def is_tracked_item(country, item_name):
    ensure_forecast_audit_schema()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM forecast_audit_runs
            WHERE country = ? AND LOWER(item_name) = LOWER(?)
            LIMIT 1
            """,
            (country.lower(), item_name),
        ).fetchone()
    return bool(row)


def get_tracked_items():
    ensure_forecast_audit_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT country, item_name, MAX(created_at) AS latest
            FROM forecast_audit_runs
            GROUP BY country, item_name
            ORDER BY latest DESC
            """
        ).fetchall()
    return [(row[0], row[1]) for row in rows]


def get_profiled_items():
    """
    Items already used by Prediction v2 have persistent model profiles.
    Seeding these on poller startup starts auditing immediately after upgrade.
    """
    try:
        if not PROFILE_CACHE_FILE.exists():
            return []
        data = json.loads(PROFILE_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    found = []
    seen = set()
    for key in data:
        # New keys: v2.4::jap::xanax ; old keys: jap::xanax
        parts = key.split("::")
        if len(parts) >= 3 and parts[0].startswith("v"):
            country = parts[-2]
            item_name = parts[-1]
        elif len(parts) == 2:
            country, item_name = parts
        else:
            continue

        pair = (country.lower(), item_name.lower())
        if pair not in seen:
            seen.add(pair)
            found.append((country.lower(), item_name))
    return found


def _normal_completed_cycles(country, item_name):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, _ = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    if not rows:
        return []

    cycles, _active, _waits = _build_validated_cycles(rows)
    return [
        cycle
        for cycle in cycles
        if cycle.get("complete")
        and not cycle.get("tiny_restock")
        and cycle.get("restock_time") is not None
        and cycle.get("depletion_time") is not None
    ]



def invalidate_pending_forecasts_crossing_gap(
    gap_start_timestamp,
    gap_end_timestamp,
    reason="collector recovery gap",
):
    """
    Retire every still-pending multi-cycle forecast that existed before a
    collection outage and therefore cannot be mapped safely to P1/P2/P3/etc.

    Without this, a pre-gap P4 could accidentally be matched to the fourth
    *observed* cycle after recovery even though unknown cycles occurred during
    the outage.
    """
    ensure_forecast_audit_schema()
    now = int(time.time())
    gap_start = int(gap_start_timestamp)
    gap_end = int(gap_end_timestamp)

    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE forecast_audit_points
            SET status = 'invalidated',
                ground_truth_valid = 0,
                validation_reason = ?,
                resolved_at = ?
            WHERE status = 'pending'
              AND run_id IN (
                  SELECT id
                  FROM forecast_audit_runs
                  WHERE created_at <= ?
              )
            """,
            (
                f"invalidated: {reason} ({gap_start} -> {gap_end})",
                now,
                gap_start,
            ),
        )
        return int(cursor.rowcount or 0)

def resolve_forecast_audits(country, item_name):
    """
    Resolve P1/P2/P3/... against the corresponding future real cycles.

    A run created at time T maps:
      P1 -> first normal completed restock after T
      P2 -> second normal completed restock after T
      ...
    This naturally lets the same eventual restock be evaluated as an original
    P4, later P3, later P2, and finally P1 after rolling re-anchors.
    """
    ensure_forecast_audit_schema()
    cycles = _normal_completed_cycles(country, item_name)
    if not cycles:
        return 0

    now = int(time.time())
    resolved_count = 0

    with _connect() as conn:
        pending = conn.execute(
            """
            SELECT
                p.id, p.run_id, p.prediction_number, p.created_at,
                p.estimate_timestamp, p.window_start_timestamp, p.window_end_timestamp,
                p.recommended_arrival_timestamp,
                r.created_at AS run_created_at
            FROM forecast_audit_points p
            JOIN forecast_audit_runs r ON r.id = p.run_id
            WHERE r.country = ?
              AND LOWER(r.item_name) = LOWER(?)
              AND p.status = 'pending'
            ORDER BY r.created_at ASC, p.prediction_number ASC
            """,
            (country.lower(), item_name),
        ).fetchall()

        for (
            point_id,
            run_id,
            prediction_number,
            point_created_at,
            estimate,
            window_start,
            window_end,
            recommended_arrival,
            run_created_at,
        ) in pending:
            future_cycles = [
                cycle for cycle in cycles
                if int(cycle["restock_time"]) > int(run_created_at)
            ]

            ordinal = int(prediction_number) - 1
            if ordinal < 0 or ordinal >= len(future_cycles):
                continue

            actual_cycle = future_cycles[ordinal]
            actual_restock = int(actual_cycle["restock_time"])
            actual_depletion = int(actual_cycle["depletion_time"])

            signed_error = (
                actual_restock - int(estimate)
                if estimate is not None else None
            )
            absolute_error = abs(signed_error) if signed_error is not None else None

            window_hit = None
            outside_window = None
            if window_start is not None and window_end is not None:
                window_hit = int(int(window_start) <= actual_restock <= int(window_end))
                outside_window = 0
                if actual_restock < int(window_start):
                    outside_window = int(window_start) - actual_restock
                elif actual_restock > int(window_end):
                    outside_window = actual_restock - int(window_end)

            arrival_hit = None
            if recommended_arrival is not None:
                arrival_hit = int(
                    actual_restock
                    <= int(recommended_arrival)
                    < actual_depletion
                )

            # To score arrival success, collection must have remained trustworthy
            # from forecast creation through the target cycle's depletion.
            coverage = _collection_coverage(
                int(run_created_at),
                actual_depletion,
            )
            valid = int(bool(coverage["valid"]))
            reason = (
                f"coverage valid via {coverage['method']} "
                f"(max gap {coverage['max_gap_seconds']}s)"
                if valid
                else f"coverage invalid via {coverage['method']} "
                f"(max gap {coverage['max_gap_seconds']}s)"
            )

            conn.execute(
                """
                UPDATE forecast_audit_points
                SET status = 'resolved',
                    actual_restock_timestamp = ?,
                    actual_depletion_timestamp = ?,
                    signed_error_seconds = ?,
                    absolute_error_seconds = ?,
                    window_hit = ?,
                    outside_window_seconds = ?,
                    arrival_hit = ?,
                    ground_truth_valid = ?,
                    validation_reason = ?,
                    resolved_at = ?
                WHERE id = ?
                """,
                (
                    actual_restock,
                    actual_depletion,
                    signed_error,
                    absolute_error,
                    window_hit,
                    outside_window,
                    arrival_hit,
                    valid,
                    reason,
                    now,
                    point_id,
                ),
            )
            resolved_count += 1

    return resolved_count


def forecast_depth_summary(country=None, item_name=None):
    """Aggregate empirical accuracy by projection depth."""
    ensure_forecast_audit_schema()

    where = ["p.status = 'resolved'", "p.ground_truth_valid = 1"]
    args = []
    if country is not None:
        where.append("r.country = ?")
        args.append(country.lower())
    if item_name is not None:
        where.append("LOWER(r.item_name) = LOWER(?)")
        args.append(item_name)

    query = f"""
        SELECT
            p.prediction_number,
            COUNT(*) AS n,
            AVG(p.absolute_error_seconds) AS mean_abs_error,
            AVG(CASE WHEN p.window_hit = 1 THEN 1.0 ELSE 0.0 END) AS window_hit_rate,
            AVG(CASE WHEN p.arrival_hit = 1 THEN 1.0 ELSE 0.0 END) AS arrival_hit_rate
        FROM forecast_audit_points p
        JOIN forecast_audit_runs r ON r.id = p.run_id
        WHERE {' AND '.join(where)}
        GROUP BY p.prediction_number
        ORDER BY p.prediction_number
    """

    with _connect() as conn:
        rows = conn.execute(query, args).fetchall()

    return [
        {
            "prediction_number": int(row[0]),
            "n": int(row[1]),
            "mean_absolute_error_seconds": row[2],
            "window_hit_rate": row[3],
            "arrival_hit_rate": row[4],
        }
        for row in rows
    ]


def recent_forecast_runs(country=None, item_name=None, limit=10):
    ensure_forecast_audit_schema()
    where = []
    args = []
    if country is not None:
        where.append("country = ?")
        args.append(country.lower())
    if item_name is not None:
        where.append("LOWER(item_name) = LOWER(?)")
        args.append(item_name)

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    args.append(int(limit))

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, created_at, country, item_name, source, status,
                   active_prediction_number, travel_reliability
            FROM forecast_audit_runs
            {clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            args,
        ).fetchall()

    return [
        {
            "id": row[0],
            "created_at": row[1],
            "country": row[2],
            "item_name": row[3],
            "source": row[4],
            "status": row[5],
            "active_prediction_number": row[6],
            "travel_reliability": row[7],
        }
        for row in rows
    ]
