"""V38 recovery-gap jobs, durable and decoupled from stock polling.

A gap is persisted before asynchronous invalidation. Retrying the same gap
is idempotent because the original auditor only changes 'pending' points.
Never modify collector stock history or fabricate resolved outcomes.
"""
from __future__ import annotations

import time

from services import history_service
from services.forecast_auditor import invalidate_pending_forecasts_crossing_gap

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecast_recovery_jobs_v38 (
    gap_start INTEGER NOT NULL,
    gap_end INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    retry_after INTEGER NOT NULL DEFAULT 0,
    completed_at INTEGER,
    invalidated_count INTEGER,
    last_error TEXT,
    PRIMARY KEY (gap_start, gap_end)
)
"""


def enqueue(gap_start, gap_end, reason="collector heartbeat recovery gap",
            *, connect=None):
    connect = connect or history_service._connect
    start, end = int(gap_start), int(gap_end)
    if start <= 0 or end <= start:
        raise ValueError("invalid recovery gap timestamps")
    with connect() as db:
        db.execute(SCHEMA)
        db.execute("""
            INSERT OR IGNORE INTO forecast_recovery_jobs_v38
            (gap_start,gap_end,reason,status)
            VALUES(?,?,?,'pending')
        """,(start,end,str(reason)[:200]))
    return {"status":"ENQUEUED","gap_start":start,"gap_end":end}


def pending(*, connect=None, now=None):
    connect=connect or history_service._connect
    now=int(time.time() if now is None else now)
    with connect() as db:
        db.execute(SCHEMA)
        row=db.execute("""
            SELECT COUNT(*) FROM forecast_recovery_jobs_v38
            WHERE status='pending'
        """).fetchone()
        ready=db.execute("""
            SELECT COUNT(*) FROM forecast_recovery_jobs_v38
            WHERE status='pending' AND retry_after<=?
        """,(now,)).fetchone()
    return {"pending":int(row[0]),"ready":int(ready[0])}


def process_one(*, connect=None, invalidator=None, now=None, retry_delay=300):
    """One durable recovery job. Never hold a write lock while classifying."""
    connect=connect or history_service._connect
    invalidator=invalidator or invalidate_pending_forecasts_crossing_gap
    now=int(time.time() if now is None else now)
    with connect() as db:
        db.execute(SCHEMA)
        row=db.execute("""
            SELECT gap_start,gap_end,reason
            FROM forecast_recovery_jobs_v38
            WHERE status='pending' AND retry_after<=?
            ORDER BY gap_start,gap_end LIMIT 1
        """,(now,)).fetchone()
    if row is None:
        return {"status":"NO_DUE_GAPS"}
    start,end,reason=int(row[0]),int(row[1]),str(row[2])
    try:
        count=int(invalidator(start,end,reason=reason))
    except Exception as exc:
        with connect() as db:
            db.execute("""
                UPDATE forecast_recovery_jobs_v38
                SET attempts=attempts+1,retry_after=?,last_error=?
                WHERE gap_start=? AND gap_end=? AND status='pending'
            """,(now+max(30,int(retry_delay)),type(exc).__name__,start,end))
        return {"status":"RETRY_SCHEDULED","gap_start":start,
                "gap_end":end,"error_type":type(exc).__name__}
    with connect() as db:
        db.execute("""
            UPDATE forecast_recovery_jobs_v38
            SET status='done',attempts=attempts+1,
                completed_at=?,invalidated_count=?,last_error=NULL
            WHERE gap_start=? AND gap_end=? AND status='pending'
        """,(now,count,start,end))
    return {"status":"COMPLETED","gap_start":start,"gap_end":end,
            "invalidated_count":count}
