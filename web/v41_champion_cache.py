"""Read-only, bounded V41 presentation of V38 private champion snapshots.

No inference, writes, model fallbacks, or access to collector history. This
module is intentionally independent of the research venv and research branch.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

HORIZON = 28800
FRESHNESS = 180
VALID_STATUS = "RESEARCH_PROPOSAL_ONLY"


def read_live_poll_heartbeat(path):
    """Latest verified poll, from the indexed timestamp column. Read-only.

    A missing/unreadable collector never authorizes a departure prediction.
    """
    try:
        p = Path(path).resolve(strict=True)
        with closing(sqlite3.connect(p.as_uri() + "?mode=ro",
                                    uri=True, timeout=0.15)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute("""SELECT timestamp FROM poll_heartbeats
                WHERE mode='poll-cycle' AND success=1
                ORDER BY timestamp DESC LIMIT 1""").fetchone()
            return int(row[0]) if row and row[0] is not None else None
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return None



def _present(row, now, live_heartbeat):
    d = dict(row)
    computed = int(d["computed_at"])
    as_of = d["stock_as_of"]
    expiry = int(d["valid_until"])
    departure = d["departure"]
    arrival = d["arrival"]
    status = str(d["status"])
    if computed > now:
        status = "FUTURE_SNAPSHOT"
    elif now >= expiry:
        status = "EXPIRED_SNAPSHOT"
    elif as_of is None or int(as_of) > computed or computed - int(as_of) > FRESHNESS:
        # Provenance age is measured at inference, not at page-view time:
        # five-minute valid snapshots must not become stale after 180 seconds.
        status = "STALE_AT_INFERENCE"
    elif live_heartbeat is None:
        status = "COLLECTOR_UNVERIFIED"
    elif live_heartbeat > now:
        status = "FUTURE_COLLECTOR_HEARTBEAT"
    elif live_heartbeat < int(as_of):
        status = "COLLECTOR_HEARTBEAT_REGRESSION"
    elif now - live_heartbeat > FRESHNESS:
        status = "COLLECTOR_STALE"
    elif status == VALID_STATUS:
        if (int(d["executed"]) != 1 or not isinstance(departure, int)
                or not isinstance(arrival, int)
                or departure < computed or departure > computed + HORIZON
                or arrival <= departure):
            status = "INVALID_SNAPSHOT"
        elif departure < now:
            status = "DEPARTURE_PASSED"
    actionable = status == VALID_STATUS
    return {
        "item_key": d["item_key"],
        "status": status,
        "model_family": d["model_family"],
        "model_config": d["model_config"],
        "computed_at": computed,
        "stock_as_of": as_of,
        "collector_last_verified": live_heartbeat,
        "valid_until": expiry,
        "departure": departure if actionable else None,
        "arrival": arrival if actionable else None,
        "quantity_threshold": 30,
        "grace_seconds": 10,
        "planning_horizon_seconds": HORIZON,
        "experimental": True,
        "prediction_accuracy_verified": False,
        "actionable": actionable,
    }


def read_snapshots(path, *, now, live_heartbeat=None, key=None, limit=236):
    """Fail closed. All queries are short, read-only and bounded."""
    if not 1 <= limit <= 236:
        raise ValueError("invalid snapshot limit")
    try:
        p = Path(path).resolve(strict=True)
        with closing(sqlite3.connect(p.as_uri() + "?mode=ro",
                                    uri=True, timeout=0.15)) as db:
            db.execute("PRAGMA query_only=ON")
            db.row_factory = sqlite3.Row
            if key is None:
                rows = db.execute(
                    "SELECT * FROM latest_predictions ORDER BY item_key LIMIT ?",
                    (limit,)).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM latest_predictions WHERE item_key = ? LIMIT 1",
                    (key,)).fetchall()
    except (OSError, sqlite3.Error):
        return {"status": "SNAPSHOT_CACHE_UNAVAILABLE",
                "actionable": False} if key is not None else []
    if key is not None and not rows:
        return {"item_key": key, "status": "NO_MODEL_SNAPSHOT",
                "actionable": False}
    return _present(rows[0], int(now), live_heartbeat) if key is not None else [
        _present(row, int(now), live_heartbeat) for row in rows
    ]
