"""Read-only V39 audit-worker liveness gate before private V38 canary.

V38 specialist shadow inference never consumes the V39 audit backlog: it
reads source stock directly. Therefore an old pending V39 target job is an
observable performance warning, not proof that the independent V38 research
worker is unsafe. Require real audit-worker progress, then separately require
fresh source/CPU admission in the V38 launcher and worker.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time

MAX_SUCCESS_AGE = 900
MAX_HIGH_PRIORITY_AGE = 1200  # warning boundary; never used to block inference


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
        "oldest_general_pending_age_seconds": None,
        "warnings": [],
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
            # A completed item may be requeued as soon as its stock changes.
            # Retain its real last_finished_at evidence even when status moves
            # from done -> pending; never use count(done) as completion rate.
            latest = conn.execute("""
                SELECT MAX(last_finished_at) FROM routine_audit_jobs_v39
            """).fetchone()[0]
            # V39.1 prioritizes the six frozen-canary/legacy Xanax evidence
            # items at priority >=100; other 236-item audits stay visible
            # as backlog but don't turn a research readiness check into a
            # requirement to clear the entire catalog at 35% of one CPU.
            oldest = conn.execute("""
                SELECT MIN(queued_at) FROM routine_audit_jobs_v39
                WHERE priority>=100 AND status IN ('pending','running')
            """).fetchone()[0]
            general_oldest = conn.execute("""
                SELECT MIN(queued_at) FROM routine_audit_jobs_v39
                WHERE priority<100 AND status IN ('pending','running')
            """).fetchone()[0]
        output["last_completion_age_seconds"] = (
            now-int(latest) if latest is not None else None)
        output["oldest_high_priority_pending_age_seconds"] = (
            now-int(oldest) if oldest is not None else None)
        output["oldest_general_pending_age_seconds"] = (
            now-int(general_oldest) if general_oldest is not None else None)
        if latest is None:
            output["reason"]="NO_COMPLETED_AUDITS_YET"
        elif (output["last_completion_age_seconds"] is None
              or not 0<=output["last_completion_age_seconds"]<=MAX_SUCCESS_AGE):
            output["reason"]="AUDIT_WORKER_NOT_COMPLETING_RECENTLY"
        else:
            output["status"]="AUDIT_QUEUE_PROGRESSING"
            output["reason"]=None
        if (output["oldest_high_priority_pending_age_seconds"] is not None
                and output["oldest_high_priority_pending_age_seconds"]>
                MAX_HIGH_PRIORITY_AGE):
            output["warnings"].append("URGENT_STOCK_AUDITS_LAGGING")
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
