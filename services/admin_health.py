import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from services.history_service import (
    _connect,
    get_collection_gaps,
    get_collector_recovery_status,
    init_db,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "stock_history.db"
PROFILE_PATH = DATA_DIR / "prediction_v2_profiles.json"


def _safe_count(conn, table_name):
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return None


def _latest_row(conn, query, args=()):
    try:
        return conn.execute(query, args).fetchone()
    except Exception:
        return None


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip() or None
    except Exception:
        return None


def _git_branch():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip() or None
    except Exception:
        return None


def _db_size_bytes():
    try:
        return DB_PATH.stat().st_size
    except Exception:
        return None


def _profile_age_seconds(now):
    try:
        return max(0, int(now - PROFILE_PATH.stat().st_mtime))
    except Exception:
        return None


def _disk_usage():
    try:
        usage = shutil.disk_usage(str(ROOT))
        return {
            "total_bytes": int(usage.total),
            "used_bytes": int(usage.used),
            "free_bytes": int(usage.free),
            "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else None,
        }
    except Exception:
        return None


def build_admin_health():
    import shutil

    init_db()
    now = int(time.time())
    collector = get_collector_recovery_status(now)

    with _connect() as conn:
        counts = {
            "stock_history": _safe_count(conn, "stock_history"),
            "poll_heartbeats": _safe_count(conn, "poll_heartbeats"),
            "collection_gaps": _safe_count(conn, "collection_gaps"),
            "prediction_audits": _safe_count(conn, "prediction_audits"),
            "forecast_audit_runs": _safe_count(conn, "forecast_audit_runs"),
            "forecast_audit_points": _safe_count(conn, "forecast_audit_points"),
        }

        latest_success = _latest_row(
            conn,
            """
            SELECT timestamp, source
            FROM poll_heartbeats
            WHERE mode = 'poll-cycle' AND success = 1
            ORDER BY timestamp DESC
            LIMIT 1
            """
        )

        latest_failed = _latest_row(
            conn,
            """
            SELECT timestamp, source, error
            FROM poll_heartbeats
            WHERE mode = 'poll-cycle' AND success = 0
            ORDER BY timestamp DESC
            LIMIT 1
            """
        )

        pending_points = _latest_row(
            conn,
            "SELECT COUNT(*) FROM forecast_audit_points WHERE status = 'pending'"
        )
        resolved_points = _latest_row(
            conn,
            "SELECT COUNT(*) FROM forecast_audit_points WHERE status = 'resolved'"
        )
        invalid_points = _latest_row(
            conn,
            "SELECT COUNT(*) FROM forecast_audit_points WHERE status = 'invalidated'"
        )

    gaps = get_collection_gaps()
    recent_gaps = []
    for gap in gaps[-8:]:
        recent_gaps.append({
            "start_timestamp": gap.get("start_timestamp"),
            "end_timestamp": gap.get("end_timestamp"),
            "reason": gap.get("reason"),
        })

    last_success_ts = int(latest_success[0]) if latest_success else collector.get("last_success_timestamp")
    last_success_age = max(0, now - last_success_ts) if last_success_ts else None

    # Health status derives only from collection freshness here.
    # VM process/service health will be added once systemd units exist.
    if last_success_age is None:
        health = "unknown"
    elif last_success_age <= 90:
        health = "healthy"
    elif last_success_age <= 180:
        health = "delayed"
    else:
        health = "stale"

    return {
        "generated_at": now,
        "health": health,
        "collector": {
            "stale": bool(collector.get("stale")),
            "last_success_timestamp": last_success_ts,
            "last_success_source": latest_success[1] if latest_success else None,
            "last_success_age_seconds": last_success_age,
            "gap_threshold_seconds": collector.get("threshold_seconds"),
        },
        "database": {
            "path": str(DB_PATH),
            "size_bytes": _db_size_bytes(),
            "counts": counts,
        },
        "forecast_auditor": {
            "pending_points": int(pending_points[0]) if pending_points else 0,
            "resolved_points": int(resolved_points[0]) if resolved_points else 0,
            "invalidated_points": int(invalid_points[0]) if invalid_points else 0,
            "profile_cache_age_seconds": _profile_age_seconds(now),
        },
        "recent_collection_gaps": recent_gaps,
        "last_failed_poll": (
            {
                "timestamp": int(latest_failed[0]),
                "source": latest_failed[1],
                "error": latest_failed[2],
            }
            if latest_failed else None
        ),
        "runtime": {
            "python": sys.version.split()[0],
            "git_branch": _git_branch(),
            "git_commit": _git_commit(),
            "pid": os.getpid(),
            "disk": _disk_usage(),
        },
    }
