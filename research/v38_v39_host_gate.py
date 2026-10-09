"""Read-only V39 audit-backlog health gate before private V38 canary.

A fresh collector and spare CPU are not enough if durable background
forecast auditing is deadlocked or repeatedly failing. Protect existing
shadow outcome evidence; don't enable additional research workers until
there is proof that the V39 audit worker actually completes real jobs.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

MAX_SUCCESS_AGE = 900
MAX_HIGH_PRIORITY_AGE = 1200


def inspect(path, *, now=None):
    now = int(time.time() if now is None else now)
    output = {
        "status": "DEFER_PRIVATE_CANARY",
        "reason": None,
        "read_only": True,
        "queue": {},
        "completed_count": 0,
        "last_completion_age_seconds": None,
        "oldest_high_priority_pending_age_seconds": None,
    }
    try:
        p = Path(path).resolve(strict=True)
        with closing(sqlite3.connect(
                p.as_uri()+"?mode=ro",uri=True,timeout=2.0)) as conn:
            conn.execute("PRAGMA query_only=ON")
            output["queue"] = {str(status):count for status,count in conn.execute("""
                SELECT status,COUNT(*) FROM routine_audit_jobs_v39
                GROUP BY status
            """)}
            output["completed_count"] = int(output["queue"].get("done",0))
            latest = conn.execute("""
                SELECT MAX(last_finished_at) FROM routine_audit_jobs_v39
                WHERE status='done'
            """).fetchone()[0]
            oldest = conn.execute("""
                SELECT MIN(queued_at) FROM routine_audit_jobs_v39
                WHERE priority>0 AND status IN ('pending','running')
            """).fetchone()[0]
        output["last_completion_age_seconds"] = (
            now-int(latest) if latest is not None else None)
        output["oldest_high_priority_pending_age_seconds"] = (
            now-int(oldest) if oldest is not None else None)
        if output["completed_count"]==0:
            output["reason"]="NO_COMPLETED_AUDITS_YET"
        elif (output["last_completion_age_seconds"] is None
              or not 0<=output["last_completion_age_seconds"]<=MAX_SUCCESS_AGE):
            output["reason"]="AUDIT_WORKER_NOT_COMPLETING_RECENTLY"
        elif (output["oldest_high_priority_pending_age_seconds"] is not None
              and output["oldest_high_priority_pending_age_seconds"]>
              MAX_HIGH_PRIORITY_AGE):
            output["reason"]="URGENT_STOCK_AUDITS_TOO_OLD"
        else:
            output["status"]="AUDIT_QUEUE_PROGRESSING"
            output["reason"]=None
    except (OSError,sqlite3.Error,ValueError) as exc:
        output["reason"]="AUDIT_QUEUE_UNREADABLE"
        output["error_type"]=type(exc).__name__
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",default="/opt/torn-fren/data/stock_history.db")
    args=p.parse_args()
    result=inspect(args.db)
    print(json.dumps(result,sort_keys=True,indent=2))
    if result["status"]!="AUDIT_QUEUE_PROGRESSING":
        raise SystemExit(2)


if __name__=="__main__":
    main()
