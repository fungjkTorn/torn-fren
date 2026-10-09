"""Bounded sidecar for *research* predictions: no public inference or stock writes."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from research.v38_snapshot_schema import LATEST_TABLE, ATTEMPT_TABLE

STEP, HORIZON, MIN_QTY, GRACE = 300, 28800, 30, 10


def open_writer(path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=3)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=3000")
    con.execute(LATEST_TABLE)
    con.execute(ATTEMPT_TABLE)
    con.execute("CREATE INDEX IF NOT EXISTS v38_due ON latest_predictions(next_due_at)")
    con.execute("CREATE INDEX IF NOT EXISTS v38_attempt_at ON inference_attempts(attempted_at)")
    con.commit()
    return con


def record(con, *, key, family, config, output, now, stock_as_of,
           executed, next_due=None, elapsed_ms=None):
    """Accept a source-pinned subprocess result, or record explicit abstention."""
    now = int(now)
    if ":" not in key or not family or not isinstance(output, dict):
        raise ValueError("invalid candidate")
    if stock_as_of is not None and int(stock_as_of) > now:
        raise ValueError("future stock observation")
    status = str(output.get("status") or "NO_STATUS")[:80]
    dep = output.get("recommended_departure_timestamp")
    arr = output.get("recommended_arrival_timestamp")
    if status == "RESEARCH_PROPOSAL_ONLY":
        if not executed:
            status = "SPECIALIST_NOT_INTEGRATED"
        elif stock_as_of is None or now - int(stock_as_of) > 180:
            status = "STALE_SOURCE_REJECTED"
        elif (not isinstance(dep, int) or not isinstance(arr, int)
              or not now <= dep <= now + HORIZON or arr <= dep):
            status = "OUT_OF_BOUNDS_CANDIDATE_REJECTED"
        elif (output.get("quantity_threshold") != MIN_QTY or
              output.get("grace_seconds") != GRACE or
              output.get("replan_step_seconds") != STEP or
              output.get("probability_calibrated") is not False):
            status = "INCOMPATIBLE_CHAMPION_CONTRACT"
    if status != "RESEARCH_PROPOSAL_ONLY":
        dep, arr = None, None
    due = now + STEP if next_due is None else int(next_due)
    if due < now:
        raise ValueError("next_due precedes attempt")
    with con:
        con.execute("""
            INSERT INTO latest_predictions VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(item_key) DO UPDATE SET
                model_family=excluded.model_family,
                model_config=excluded.model_config,
                status=excluded.status,
                computed_at=excluded.computed_at,
                stock_as_of=excluded.stock_as_of,
                valid_until=excluded.valid_until,
                next_due_at=excluded.next_due_at,
                departure=excluded.departure,
                arrival=excluded.arrival,
                executed=excluded.executed
            WHERE excluded.computed_at >= latest_predictions.computed_at
        """, (key, family, config, status, now, stock_as_of,
              now+STEP, due, dep, arr, int(bool(executed))))
        con.execute("""
            INSERT INTO inference_attempts(item_key,attempted_at,status,elapsed_ms)
            VALUES(?,?,?,?)
        """, (key, now, status, elapsed_ms))
    return status


def _public(row, now):
    if row is None:
        return {"status": "NO_SNAPSHOT", "fallback_required": True}
    d = dict(row)
    stale = now >= d["valid_until"] or (
        d["stock_as_of"] is not None and d["stock_as_of"] > now)
    actionable = (not stale and d["status"] == "RESEARCH_PROPOSAL_ONLY"
                  and d["executed"] == 1 and d["departure"] is not None
                  and now <= d["departure"] <= now + HORIZON)
    return {
        "item_key": d["item_key"], "model_family": d["model_family"],
        "model_config": d["model_config"],
        "status": "STALE_SNAPSHOT" if stale else d["status"],
        "worker_status": d["status"], "computed_at": d["computed_at"],
        "stock_as_of": d["stock_as_of"], "valid_until": d["valid_until"],
        "next_due_at": d["next_due_at"],
        "recommended_departure_timestamp": d["departure"] if actionable else None,
        "recommended_arrival_timestamp": d["arrival"] if actionable else None,
        "experimental": True, "probability_calibrated": False,
        "fallback_required": not actionable,
    }


def read(path, now, key=None, limit=236):
    """Cheap read-only SQLite API; fails open to V2 fallback, never computes."""
    if not 1 <= limit <= 500:
        raise ValueError("bad limit")
    try:
        p = Path(path).resolve(strict=True)
        with sqlite3.connect(p.as_uri()+"?mode=ro", uri=True, timeout=.15) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            if key is not None:
                row = con.execute("SELECT * FROM latest_predictions WHERE item_key=?",
                                  (key,)).fetchone()
                return _public(row, int(now))
            rows = con.execute("SELECT * FROM latest_predictions ORDER BY item_key LIMIT ?",
                               (limit,)).fetchall()
            return [_public(row, int(now)) for row in rows]
    except (OSError, sqlite3.Error):
        return {"status": "CACHE_UNAVAILABLE", "fallback_required": True} if key else []


def prune_attempts(con, cutoff):
    with con:
        result = con.execute("DELETE FROM inference_attempts WHERE attempted_at < ?",
                             (int(cutoff),))
    return result.rowcount
