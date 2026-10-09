"""Durable, coalesced forecast-audit queue; stock collector never computes models.

All queue writes use the existing collector SQLite transaction. Each
(country,item) has one queued revision, so repeated stock changes coalesce.
An in-progress job cannot erase a newer event. Expired leases are retryable.
"""
from __future__ import annotations

import argparse
import json
import time
from services import history_service as hs

SCHEMA = """
CREATE TABLE IF NOT EXISTS routine_audit_jobs_v39 (
    country TEXT NOT NULL,
    item_name TEXT NOT NULL,
    queued_at INTEGER NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_due_at INTEGER NOT NULL DEFAULT 0,
    lease_until INTEGER NOT NULL DEFAULT 0,
    last_finished_at INTEGER,
    last_error TEXT,
    PRIMARY KEY(country,item_name)
)
"""
META_SCHEMA = """
CREATE TABLE IF NOT EXISTS routine_audit_meta_v39 (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


def ensure_schema(conn):
    conn.execute(SCHEMA)
    conn.execute(META_SCHEMA)
    conn.execute("""
      CREATE INDEX IF NOT EXISTS idx_routine_audit_ready_v39
      ON routine_audit_jobs_v39(status,next_due_at,priority,queued_at)
    """)


def enqueue(conn, country, item_name, now=None, *, priority=10):
    now=int(time.time() if now is None else now)
    country=str(country).lower().strip()
    item_name=str(item_name).strip()
    if not country or not item_name:
        raise ValueError("country and item are required")
    # The caller's existing stock-row transaction commits this UPSERT
    # atomically with the observation that caused the audit.
    conn.execute("""
      INSERT INTO routine_audit_jobs_v39(
        country,item_name,queued_at,generation,priority,status,next_due_at,
        lease_until)
      VALUES(?,?,?,1,?,'pending',0,0)
      ON CONFLICT(country,item_name) DO UPDATE SET
        queued_at=excluded.queued_at,
        generation=routine_audit_jobs_v39.generation+1,
        priority=MAX(routine_audit_jobs_v39.priority,excluded.priority),
        status='pending',next_due_at=0,lease_until=0,
        last_error=NULL
    """,(country,item_name,now,int(priority)))


def claim(now=None, *, lease_seconds=360):
    hs.init_db()
    now=int(time.time() if now is None else now)
    with hs._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("""
          SELECT country,item_name,generation,attempts
          FROM routine_audit_jobs_v39
          WHERE (status='pending' AND next_due_at<=?)
             OR (status='running' AND lease_until<=?)
          ORDER BY priority DESC,queued_at DESC
          LIMIT 1
        """,(now,now)).fetchone()
        if row is None:
            return None
        country,item_name,generation,attempts=row
        con.execute("""
          UPDATE routine_audit_jobs_v39
          SET status='running',attempts=attempts+1,
              lease_until=?,next_due_at=0
          WHERE country=? AND item_name=? AND generation=?
        """,(now+int(lease_seconds),country,item_name,generation))
    return {"country":country,"item_name":item_name,
            "generation":int(generation),"attempts":int(attempts)+1}


def finish(job, *, error=None, now=None):
    now=int(time.time() if now is None else now)
    generation=int(job["generation"])
    retry_delay=min(1800,30*2**min(6,max(0,int(job["attempts"])-1)))
    with hs._connect() as con:
        if error is None:
            result=con.execute("""
              UPDATE routine_audit_jobs_v39
              SET status='done',last_finished_at=?,last_error=NULL,
                  lease_until=0,priority=0
              WHERE country=? AND item_name=? AND generation=?
                AND status='running'
            """,(now,job["country"],job["item_name"],generation))
        else:
            result=con.execute("""
              UPDATE routine_audit_jobs_v39
              SET status='pending',next_due_at=?,last_error=?,
                  lease_until=0
              WHERE country=? AND item_name=? AND generation=?
                AND status='running'
            """,(now+retry_delay,str(error)[:400],
                 job["country"],job["item_name"],generation))
    # 0 means newer stock was observed while this work was running;
    # the newer queue revision remains pending and must be computed.
    return bool(result.rowcount)


def status():
    hs.init_db()
    with hs._connect() as con:
        rows=con.execute("""
          SELECT status,COUNT(*) FROM routine_audit_jobs_v39
          GROUP BY status
        """).fetchall()
    return dict(rows)


def bootstrap():
    """One-time only: enqueue existing audited items without poller CPU work.

    The legacy historical baseline table is retained, not rewritten. Each
    profile/tracked item gets a future chance to refresh, at low priority.
    """
    hs.init_db()
    with hs._connect() as con:
        if con.execute("""
          SELECT 1 FROM routine_audit_meta_v39 WHERE key='bootstrap_done'
        """).fetchone():
            return 0
    from services.forecast_auditor import get_profiled_items,get_tracked_items
    items=set((c.lower(),n) for c,n in get_profiled_items())
    items.update((c.lower(),n) for c,n in get_tracked_items())
    now=int(time.time())
    with hs._connect() as con:
        if con.execute("""
          SELECT 1 FROM routine_audit_meta_v39 WHERE key='bootstrap_done'
        """).fetchone():
            return 0
        for country,item in sorted(items):
            # Do not override a newer high-priority change event already queued.
            con.execute("""
              INSERT OR IGNORE INTO routine_audit_jobs_v39
               (country,item_name,queued_at,generation,priority,status)
              VALUES (?,?,?,1,0,'pending')
            """,(country,item,now))
        con.execute("""
          INSERT OR IGNORE INTO routine_audit_meta_v39(key,value)
          VALUES('bootstrap_done',?)
        """,(str(now),))
    return len(items)


def audit_item(country,item_name):
    from services.history_service import update_prediction_audits_for_item
    from services.forecast_auditor import is_tracked_item,resolve_forecast_audits
    from services.prediction_v2_live import build_live_prediction_v2
    from services.shadow_model_auditor import update_shadow_models

    # Any partial failure remains retryable. All individual forecasts
    # already deduplicate identical signatures in existing audit tables.
    baseline=update_prediction_audits_for_item(country,item_name)
    resolved=resolve_forecast_audits(country,item_name)
    active=None
    if is_tracked_item(country,item_name):
        refreshed=build_live_prediction_v2(
            country,item_name,audit_source="routine-audit-v39",record_audit=True)
        active=(refreshed.get("display_prediction") or {}).get("prediction_number")
    shadow=None
    if country.lower()=="jap" and item_name.lower()=="xanax":
        shadow=update_shadow_models(country,item_name)
    return {"baseline":baseline,"resolved":resolved,"active":active,"shadow":shadow}


def drain(*,max_jobs=4,max_seconds=40,now_fn=time.time,
          runner=audit_item):
    if not 1<=max_jobs<=16 or not 5<=max_seconds<=120:
        raise ValueError("invalid batch budget")
    from research.v38_gap_recovery import pending as recovery_pending
    from services.history_service import get_collector_recovery_status
    recovery=recovery_pending()
    collector=get_collector_recovery_status()
    if recovery["pending"] or collector.get("stale"):
        return {"status":"DEFERRED_RECOVERY_OR_STALE_COLLECTOR",
                "recovery":recovery,"collector":collector}
    seeded=bootstrap()
    started=time.monotonic()
    results=[]
    while len(results)<max_jobs and time.monotonic()-started<max_seconds:
        job=claim()
        if job is None:
            break
        try:
            outcome=runner(job["country"],job["item_name"])
            updated=finish(job)
            results.append({"item":f"{job['country']}:{job['item_name']}",
                            "status":"COMPLETED" if updated else "SUPERSEDED",
                            "outcome":outcome})
        except Exception as exc:
            updated=finish(job,error=f"{type(exc).__name__}: {str(exc)[:150]}")
            results.append({"item":f"{job['country']}:{job['item_name']}",
                            "status":"RETRY_SCHEDULED" if updated else "SUPERSEDED",
                            "error_type":type(exc).__name__})
    return {"status":"BATCH_COMPLETED","bootstrap_candidates":seeded,
            "results":results,"queue":status()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once",action="store_true",required=True)
    p.add_argument("--max-jobs",type=int,default=4)
    p.add_argument("--max-seconds",type=int,default=40)
    args=p.parse_args()
    print(json.dumps(drain(max_jobs=args.max_jobs,
                           max_seconds=args.max_seconds),
                     default=str,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
