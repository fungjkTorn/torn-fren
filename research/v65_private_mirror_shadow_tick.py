"""V65 opt-in private 19-model shadow tick using a fresh SQLite mirror.

Installed ONLY by the guarded private-service overlay. The production
collector, V2 website and bot are never modified. Fail closed on stale
heartbeat or snapshot failure; never fall back to the live WAL DB.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from research.v60_private_snapshot_probe import approved_collector_source, snapshot_once
from research.v63_full_mirror_smoke import exact_roster, source_age
from research.v38_budgeted_runner import run_tick
from research.v38_capacity_guard import inspect as capacity_guard
from research.v57_exception_fingerprint import fingerprint

SOURCE=Path("/opt/torn-fren/data/stock_history.db")
ROOT=Path("/var/lib/torn-fren-v38")
SNAPSHOT=ROOT/"v65_stock_snapshot.db"
SIDECAR=ROOT/"private_predictions.db"
WORKER_SECONDS=30
WALL_BUDGET=220
MAX_JOBS=19
SAFE_SNAPSHOT_RETRY_CODES={
    sqlite3.SQLITE_CANTOPEN,sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED,
    getattr(sqlite3,"SQLITE_READONLY_RECOVERY",264),
}
FAILURE_STATUSES={
    "V65_PREFLIGHT_ERROR","V65_SNAPSHOT_ERROR","V65_RUNNER_ERROR",
    "V65_FINAL_FRESHNESS_ERROR","V65_NO_FRESH_SNAPSHOT",
}


def stage_error(stage, exc):
    return {"status":f"V65_{stage}_ERROR","research_only":True,
            "collector_written":False,**fingerprint(exc)}


def snapshot_with_retry(source, dest, *, snapshotter=snapshot_once,
                        sleep=time.sleep, delays=(0.25,0.75)):
    """Retry transient WAL opening/recovery errors only; never stale results.

    The snapshot helper cleans unpublished temporary files on exceptions.
    The collector is opened mode=ro on each attempt; no DB writes allowed.
    """
    for i in range(len(delays)+1):
        try:
            return snapshotter(source,dest)
        except sqlite3.OperationalError as exc:
            code=getattr(exc,"sqlite_errorcode",None)
            family=code & 255 if isinstance(code,int) else None
            recover=getattr(sqlite3,"SQLITE_READONLY_RECOVERY",264)
            transient=((code==recover) or
                       (family in (sqlite3.SQLITE_CANTOPEN,
                                   sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)))
            if not transient or i==len(delays):
                raise
            sleep(delays[i])
    raise AssertionError("unreachable")


def tick(*,source=SOURCE,snapshot=SNAPSHOT,sidecar=SIDECAR,
         snapshotter=snapshot_with_retry,infer=run_tick,
         capacity_probe=capacity_guard,clock=time.time):
    # Never accept arbitrary source or sidecar paths for scheduled operation.
    src=Path(source).resolve(strict=True)
    dst=Path(snapshot).resolve(strict=False)
    ledger=Path(sidecar).resolve(strict=False)
    if src==dst or src==ledger or dst==ledger:
        raise ValueError("source/snapshot/sidecar must be distinct")
    keys=exact_roster()
    capacity=capacity_probe()
    if not capacity["allowed"]:
        return {"status":"V65_DEFERRED_CPU_PRESSURE","collector_written":False,
                "research_only":True,"executed":[]}
    try:
        snap=snapshotter(src,dst)
    except Exception as exc:
        return stage_error("SNAPSHOT",exc)
    if not snap.get("published") or snap.get("status")!="PRIVATE_SNAPSHOT_READY":
        return {"status":"V65_NO_FRESH_SNAPSHOT","collector_written":False,
                "research_only":True,"snapshot":snap,"executed":[]}
    try:
        result=infer(
            stock_db=dst,sidecar_db=ledger,execute=True,
            with_xanax=True,with_redfox=True,
            approved_keys=keys,
            max_jobs=MAX_JOBS,worker_seconds=WORKER_SECONDS,
            budget_seconds=WALL_BUDGET,max_rows=10000,
        )
    except Exception as exc:
        return stage_error("RUNNER",exc)
    rows=result.get("executed",[])
    try:
        final_age=source_age(dst,clock=clock)
    except Exception as exc:
        return stage_error("FINAL_FRESHNESS",exc)
    return {
        "status": ("V65_EXECUTED_RESEARCH_ONLY" if
                   result.get("mode")=="EXECUTED_RESEARCH_ONLY" else
                   "V65_DEFERRED_"+str(result.get("mode","UNKNOWN"))[:48]),
        "runner_mode":result.get("mode"),
        "collector_written":False,
        "public_routing_changed":False,
        "research_only":True,
        "snapshot":snap,
        "end_heartbeat_age_seconds":final_age,
        "executed":rows,
        "executed_count":len(rows),
        "proposal_count":sum(r.get("status")=="RESEARCH_PROPOSAL_ONLY" for r in rows),
        "error_count":sum(str(r.get("status","")).endswith("_ERROR") for r in rows),
        "stale_count":sum(r.get("status")=="COLLECTOR_STALE_OR_NO_HEARTBEAT"
                          for r in rows),
    }


def preflight():
    if not approved_collector_source(SOURCE):
        raise ValueError("not the approved collector")
    if not ROOT.is_dir() or not ROOT.resolve(strict=True).is_dir():
        raise ValueError("private research directory absent")
    for path in (SNAPSHOT,SIDECAR):
        if path.parent.resolve(strict=True)!=ROOT.resolve(strict=True):
            raise ValueError("research path escaped private directory")
        if path.is_symlink():
            raise ValueError("private research output cannot be symlink")
    exact_roster()


def main():
    try:
        preflight()
        output=tick()
    except Exception as exc:
        output=stage_error("PREFLIGHT",exc)
    print(json.dumps(output,sort_keys=True))
    if output["status"] in FAILURE_STATUSES:
        raise SystemExit(1)


if __name__=="__main__":
    main()
