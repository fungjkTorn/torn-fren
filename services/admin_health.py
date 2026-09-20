import os
import sqlite3
import subprocess
import sys
import time
import shutil
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
BACKUP_DIR = Path("/var/lib/torn-fren/backups")

SERVICE_UNITS = {
    "poller": "torn-fren-poller.service",
    "discord": "torn-fren-bot.service",
    "web": "torn-fren-web.service",
    "nginx": "nginx.service",
}
BACKUP_TIMER_UNIT = "torn-fren-backup.timer"


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


def _systemctl_properties(unit, properties):
    try:
        command = ["systemctl", "show", unit, "--no-pager"]
        for prop in properties:
            command.extend(["--property", prop])
        output = subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        result = {}
        for line in output.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key] = value
        return result
    except Exception:
        return {}


def _system_uptime_seconds():
    try:
        return float(time.clock_gettime(time.CLOCK_BOOTTIME))
    except Exception:
        return None


def _service_status(unit):
    props = _systemctl_properties(
        unit,
        ["ActiveState", "SubState", "MainPID", "ActiveEnterTimestampMonotonic"],
    )
    if not props:
        return {
            "unit": unit,
            "active": None,
            "active_state": "unknown",
            "sub_state": "unknown",
            "main_pid": None,
            "uptime_seconds": None,
        }

    active_state = props.get("ActiveState") or "unknown"
    sub_state = props.get("SubState") or "unknown"

    try:
        main_pid = int(props.get("MainPID") or 0) or None
    except Exception:
        main_pid = None

    uptime_seconds = None
    try:
        entered_us = int(props.get("ActiveEnterTimestampMonotonic") or 0)
        boot_seconds = _system_uptime_seconds()
        if entered_us > 0 and boot_seconds is not None:
            uptime_seconds = max(0, int(boot_seconds - (entered_us / 1_000_000)))
    except Exception:
        pass

    return {
        "unit": unit,
        "active": active_state == "active",
        "active_state": active_state,
        "sub_state": sub_state,
        "main_pid": main_pid,
        "uptime_seconds": uptime_seconds,
    }


def _services_status():
    return {
        name: _service_status(unit)
        for name, unit in SERVICE_UNITS.items()
    }


def _backup_status(now):
    files = []
    try:
        if BACKUP_DIR.exists():
            files = sorted(
                (
                    path for path in BACKUP_DIR.glob("stock_history-*.db.gz")
                    if path.is_file()
                ),
                key=lambda path: path.stat().st_mtime,
            )
    except Exception:
        files = []

    latest = files[-1] if files else None
    total_bytes = 0
    for path in files:
        try:
            total_bytes += path.stat().st_size
        except Exception:
            pass

    latest_timestamp = None
    latest_size_bytes = None
    latest_name = None
    if latest is not None:
        try:
            stat = latest.stat()
            latest_timestamp = int(stat.st_mtime)
            latest_size_bytes = int(stat.st_size)
            latest_name = latest.name
        except Exception:
            pass

    timer = _systemctl_properties(
        BACKUP_TIMER_UNIT,
        ["ActiveState", "SubState", "NextElapseUSecRealtime"],
    )

    return {
        "directory": str(BACKUP_DIR),
        "count": len(files),
        "total_bytes": int(total_bytes),
        "last_backup_timestamp": latest_timestamp,
        "last_backup_age_seconds": (
            max(0, int(now - latest_timestamp))
            if latest_timestamp is not None else None
        ),
        "last_backup_size_bytes": latest_size_bytes,
        "last_backup_name": latest_name,
        "timer_active": timer.get("ActiveState") == "active" if timer else None,
        "timer_state": timer.get("ActiveState") if timer else "unknown",
        "timer_sub_state": timer.get("SubState") if timer else "unknown",
        "next_backup": timer.get("NextElapseUSecRealtime") or None,
    }


def build_admin_health():
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
        "services": _services_status(),
        "backups": _backup_status(now),
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
