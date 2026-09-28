import math
import sqlite3
import statistics
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from services.arrival_success_lab import TRAVEL_SECONDS
from services.history_service import (
    DB_PATH,
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _prediction_anchor_is_currently_trustworthy,
    _suppress_provider_bounces,
)

ET = ZoneInfo("America/New_York")
TRAVEL_DAY_START_TS = 1790308800  # 2026-09-25 00:00 ET
TRAVEL_DAY_END_TS = 1790568000    # 2026-09-28 00:00 ET
MIN_TRAINING_CYCLES = 30

SHADOW_MODELS = (
    "safe_balanced_v1",
    "safe_context_v1",
)


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_shadow_tables():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_travel_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                country TEXT NOT NULL,
                item_name TEXT NOT NULL,
                model_name TEXT NOT NULL,
                anchor_depletion_timestamp INTEGER NOT NULL,
                predicted_restock_timestamp INTEGER,
                target_arrival_timestamp INTEGER,
                recommended_leave_timestamp INTEGER,
                training_samples INTEGER NOT NULL,
                travel_day_at_issue INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                actual_restock_timestamp INTEGER,
                actual_depletion_timestamp INTEGER,
                restock_error_seconds INTEGER,
                arrival_hit INTEGER,
                early_seconds INTEGER,
                late_seconds INTEGER,
                travel_day_at_resolution INTEGER,
                validation_reason TEXT,
                resolved_at INTEGER,
                UNIQUE(country, item_name, model_name, anchor_depletion_timestamp)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_shadow_pending
            ON shadow_travel_forecasts(country, item_name, status)
            """
        )


def _is_travel_day(timestamp):
    if timestamp is None:
        return False
    return TRAVEL_DAY_START_TS <= int(timestamp) < TRAVEL_DAY_END_TS


def _hour_et(timestamp):
    value = datetime.fromtimestamp(int(timestamp), timezone.utc).astimezone(ET)
    return value.hour + value.minute / 60.0 + value.second / 3600.0


def _circular_hour_distance(a, b):
    delta = abs(float(a) - float(b)) % 24.0
    return min(delta, 24.0 - delta)


def _weighted_quantile(values, weights, q):
    pairs = sorted((float(v), float(w)) for v, w in zip(values, weights) if w > 0)
    if not pairs:
        return None
    total = sum(w for _v, w in pairs)
    cutoff = max(0.0, min(1.0, float(q))) * total
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= cutoff:
            return value
    return pairs[-1][0]


def _robust_training(records):
    if len(records) < 5:
        return records
    waits = [r["wait_seconds"] for r in records]
    med = statistics.median(waits)
    mad = statistics.median(abs(v - med) for v in waits)
    if not mad:
        return records
    lo = med - 4.0 * mad
    hi = med + 4.0 * mad
    filtered = [r for r in records if lo <= r["wait_seconds"] <= hi]
    return filtered if len(filtered) >= max(10, len(records) // 2) else records


def _build_training(country, item_name):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, _ = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    if not rows:
        return None, [], [], []

    cycles, active_cycle, wait_samples = _build_validated_cycles(rows, country, item_name)
    complete = [c for c in cycles if c.get("complete")]
    cycle_by_restock = {int(c["restock_time"]): c for c in complete}

    records = []
    for sample in wait_samples:
        if not sample.get("valid"):
            continue
        cycle = cycle_by_restock.get(int(sample["to_restock"]))
        if not cycle or not cycle.get("valid_lifetime") or cycle.get("tiny_restock"):
            continue
        restock_ts = int(cycle["restock_time"])
        # Keep Travel Day for separate forward validation, but do not let it teach
        # the normal-day model because double capacity materially changes sell rate.
        if _is_travel_day(restock_ts):
            continue
        records.append(
            {
                "anchor_timestamp": int(sample["from_depletion"]),
                "restock_timestamp": restock_ts,
                "depletion_timestamp": int(cycle["depletion_time"]),
                "wait_seconds": int(sample["seconds"]),
                "lifetime_seconds": int(cycle["lifetime_seconds"]),
                "restock_hour": _hour_et(restock_ts),
            }
        )

    records = _robust_training(records)
    return rows, cycles, wait_samples, records


def _choose_arrival_offset(records, *, early_cap, expected_hour=None, recent_half_life=None):
    if not records:
        return None

    waits = [r["wait_seconds"] for r in records]
    center = statistics.median(waits)
    lo = max(30 * 60, int(center - 35 * 60))
    hi = int(center + 35 * 60)

    weights = []
    for index, record in enumerate(records):
        weight = 1.0
        if expected_hour is not None:
            weight *= math.exp(-(_circular_hour_distance(record["restock_hour"], expected_hour) / 4.0) ** 2) + 0.15
        if recent_half_life:
            age = len(records) - 1 - index
            weight *= math.exp(-math.log(2.0) * age / float(recent_half_life))
        weights.append(weight)

    best = None
    for target in range(lo, hi + 1, 30):
        total_weight = sum(weights)
        early_weight = 0.0
        hit_weight = 0.0
        late_weight = 0.0
        for record, weight in zip(records, weights):
            start = record["wait_seconds"]
            end = start + record["lifetime_seconds"]
            if target < start:
                early_weight += weight
            elif target > end:
                late_weight += weight
            else:
                hit_weight += weight
        early_rate = early_weight / total_weight
        hit_rate = hit_weight / total_weight
        late_rate = late_weight / total_weight
        feasible = early_rate <= early_cap
        # First prefer satisfying the early-risk cap, then stock-at-arrival hit
        # rate, then lower late risk, then the earlier target on exact ties.
        score = (
            1 if feasible else 0,
            hit_rate if feasible else -early_rate,
            -late_rate,
            -target,
        )
        if best is None or score > best[0]:
            best = (score, target, early_rate, hit_rate, late_rate)
    return best


def _candidate_forecasts(country, item_name):
    travel_seconds = TRAVEL_SECONDS.get(country.lower())
    if travel_seconds is None:
        return []

    rows, cycles, wait_samples, training = _build_training(country, item_name)
    if not rows or len(training) < MIN_TRAINING_CYCLES or rows[-1][1] != 0:
        return []

    completed = [
        c for c in cycles
        if c.get("complete") and not c.get("tiny_restock") and c.get("depletion_time")
    ]
    if not completed:
        return []
    anchor = int(completed[-1]["depletion_time"])
    trustworthy, _reason = _prediction_anchor_is_currently_trustworthy(
        country, item_name, anchor, int(time.time())
    )
    if not trustworthy:
        return []

    # Only use historical cycles that existed before this anchor.
    training = [r for r in training if r["restock_timestamp"] < anchor]
    training = _robust_training(training)
    if len(training) < MIN_TRAINING_CYCLES:
        return []

    waits = [r["wait_seconds"] for r in training]
    global_wait = statistics.median(waits)

    global_choice = _choose_arrival_offset(training, early_cap=0.075)
    expected_hour = (_hour_et(anchor) + global_wait / 3600.0) % 24.0
    context_weights = []
    for index, record in enumerate(training):
        age = len(training) - 1 - index
        tod_weight = math.exp(-(_circular_hour_distance(record["restock_hour"], expected_hour) / 4.0) ** 2) + 0.15
        recent_weight = math.exp(-math.log(2.0) * age / 20.0)
        context_weights.append(tod_weight * recent_weight)
    context_wait = _weighted_quantile(waits, context_weights, 0.50) or global_wait
    context_choice = _choose_arrival_offset(
        training,
        early_cap=0.05,
        expected_hour=expected_hour,
        recent_half_life=20.0,
    )

    candidates = []
    if global_choice:
        candidates.append(
            {
                "model_name": "safe_balanced_v1",
                "predicted_restock_timestamp": int(anchor + global_wait),
                "target_arrival_timestamp": int(anchor + global_choice[1]),
                "training_samples": len(training),
            }
        )
    if context_choice:
        candidates.append(
            {
                "model_name": "safe_context_v1",
                "predicted_restock_timestamp": int(anchor + context_wait),
                "target_arrival_timestamp": int(anchor + context_choice[1]),
                "training_samples": len(training),
            }
        )
    for candidate in candidates:
        candidate["anchor_depletion_timestamp"] = anchor
        candidate["recommended_leave_timestamp"] = (
            candidate["target_arrival_timestamp"] - travel_seconds
        )
    return candidates


def record_shadow_forecasts(country, item_name):
    init_shadow_tables()
    candidates = _candidate_forecasts(country, item_name)
    if not candidates:
        return 0
    inserted = 0
    now = int(time.time())
    with _connect() as conn:
        for candidate in candidates:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO shadow_travel_forecasts (
                    created_at, country, item_name, model_name,
                    anchor_depletion_timestamp, predicted_restock_timestamp,
                    target_arrival_timestamp, recommended_leave_timestamp,
                    training_samples, travel_day_at_issue, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    now,
                    country.lower(),
                    item_name,
                    candidate["model_name"],
                    candidate["anchor_depletion_timestamp"],
                    candidate["predicted_restock_timestamp"],
                    candidate["target_arrival_timestamp"],
                    candidate["recommended_leave_timestamp"],
                    candidate["training_samples"],
                    1 if _is_travel_day(now) else 0,
                ),
            )
            inserted += int(cursor.rowcount > 0)
    return inserted


def resolve_shadow_forecasts(country, item_name):
    init_shadow_tables()
    _rows, cycles, wait_samples, _training = _build_training(country, item_name)
    cycle_by_restock = {
        int(c["restock_time"]): c
        for c in cycles
        if c.get("complete") and c.get("valid_lifetime") and not c.get("tiny_restock")
    }
    valid_wait_by_anchor = {
        int(s["from_depletion"]): s
        for s in wait_samples
        if s.get("valid")
    }

    with _connect() as conn:
        pending = conn.execute(
            """
            SELECT * FROM shadow_travel_forecasts
            WHERE country = ? AND LOWER(item_name) = LOWER(?) AND status = 'pending'
            ORDER BY id
            """,
            (country.lower(), item_name),
        ).fetchall()

        resolved = 0
        for row in pending:
            anchor = int(row["anchor_depletion_timestamp"])
            sample = valid_wait_by_anchor.get(anchor)
            if not sample:
                continue
            actual_restock = int(sample["to_restock"])
            cycle = cycle_by_restock.get(actual_restock)
            if not cycle:
                continue
            actual_depletion = int(cycle["depletion_time"])
            target = int(row["target_arrival_timestamp"])
            hit = actual_restock <= target <= actual_depletion
            early = max(0, actual_restock - target)
            late = max(0, target - actual_depletion)
            restock_error = int(row["predicted_restock_timestamp"] or actual_restock) - actual_restock
            travel_day = _is_travel_day(actual_restock)

            conn.execute(
                """
                UPDATE shadow_travel_forecasts
                SET status = 'resolved',
                    actual_restock_timestamp = ?, actual_depletion_timestamp = ?,
                    restock_error_seconds = ?, arrival_hit = ?,
                    early_seconds = ?, late_seconds = ?,
                    travel_day_at_resolution = ?, validation_reason = 'clean event-aware cycle',
                    resolved_at = ?
                WHERE id = ?
                """,
                (
                    actual_restock,
                    actual_depletion,
                    restock_error,
                    1 if hit else 0,
                    early,
                    late,
                    1 if travel_day else 0,
                    int(time.time()),
                    int(row["id"]),
                ),
            )
            resolved += 1
    return resolved


def update_shadow_models(country, item_name):
    resolved = resolve_shadow_forecasts(country, item_name)
    recorded = record_shadow_forecasts(country, item_name)
    return {"resolved": resolved, "recorded": recorded}


def shadow_summary(country="jap", item_name="Xanax"):
    init_shadow_tables()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT model_name,
                   SUM(CASE WHEN status='resolved' AND travel_day_at_resolution=0 THEN 1 ELSE 0 END) AS normal_n,
                   AVG(CASE WHEN status='resolved' AND travel_day_at_resolution=0 THEN arrival_hit END) AS normal_hit_rate,
                   AVG(CASE WHEN status='resolved' AND travel_day_at_resolution=0 AND early_seconds>0 THEN early_seconds END) AS normal_avg_early_seconds,
                   AVG(CASE WHEN status='resolved' AND travel_day_at_resolution=0 AND late_seconds>0 THEN late_seconds END) AS normal_avg_late_seconds,
                   SUM(CASE WHEN status='resolved' AND travel_day_at_resolution=1 THEN 1 ELSE 0 END) AS travel_day_n,
                   AVG(CASE WHEN status='resolved' AND travel_day_at_resolution=1 THEN arrival_hit END) AS travel_day_hit_rate,
                   SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending_n
            FROM shadow_travel_forecasts
            WHERE country=? AND LOWER(item_name)=LOWER(?)
            GROUP BY model_name
            ORDER BY model_name
            """,
            (country.lower(), item_name),
        ).fetchall()
        return [dict(row) for row in rows]