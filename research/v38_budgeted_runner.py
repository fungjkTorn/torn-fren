"""V38 one-shot, serial, resource-bounded research scheduler. Not a systemd unit.

The public site, V2, bot, poller and V37 timer are never invoked or modified.
--execute is opt-in, and work stops if the source delta has not caught up.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from research.v38_readonly_resource_probe import ALL as PINNED_WORKERS
from research.v38_prediction_store import open_writer, record, read
from research.v38_incremental_observer import observe

ROSTER=Path(__file__).with_name("v38_roster.json")


def choose(roster, snapshots, *, now, active=(), changed=(), limit=4):
    """Fixed source-pinned 16 of 22; never substitute for six missing winners."""
    active,changed=set(active),set(changed)
    due=[]
    pending=[]
    for key,meta in roster.items():
        if key not in PINNED_WORKERS:
            pending.append(key)
            continue
        snap=snapshots.get(key) or {}
        dep=snap.get("recommended_departure_timestamp")
        near=dep is not None and now<=dep<=now+28800
        is_due=key in active or key in changed or snap.get("next_due_at",0)<=now
        if is_due:
            last=snap.get("computed_at",0)
            due.append((0 if key in active else 1 if near else
                        2 if key in changed else 3,
                        last,key))
    due.sort()
    return {"execute":[x[2] for x in due[:limit]],
            "deferred":[x[2] for x in due[limit:]],
            "pending_specialists":sorted(pending)}


def run_tick(*, stock_db, sidecar_db, execute=False, active=(),
             max_rows=10000, max_jobs=4, worker_seconds=20,
             budget_seconds=85, now=None, runner=subprocess.run,
             clock=time.monotonic):
    if not 1<=max_jobs<=16 or not 1<=worker_seconds<=60:
        raise ValueError("invalid concurrency/resource limits")
    if not worker_seconds<=budget_seconds<=240:
        raise ValueError("invalid total wall budget")
    now=int(time.time() if now is None else now)
    roster=json.loads(ROSTER.read_text(encoding="utf-8"))["items"]
    # Plan-only does not even create the sidecar or access the stock database.
    if not execute:
        snapshots={p["item_key"]:p for p in read(sidecar_db,now) if "item_key" in p}
        return {"mode":"PLAN_ONLY","plan":choose(roster,snapshots,now=now,
                active=active,limit=max_jobs),"collector_written":False}
    side=open_writer(sidecar_db)
    try:
        delta=observe(stock_db,side,max_rows=max_rows)
        if not delta["caught_up"]:
            return {"mode":"SOURCE_BOOTSTRAP","delta":delta,
                    "executed":[],"collector_written":False}
        snaps={p["item_key"]:p for p in read(sidecar_db,now) if "item_key" in p}
        plan=choose(roster,snaps,now=now,active=active,
                    changed=delta["affected_keys"],limit=max_jobs)
        start=clock()
        results=[]
        for key in plan["execute"]:
            remaining=budget_seconds-(clock()-start)
            if remaining<1:
                results.append({"item_key":key,"status":"DEFERRED_BUDGET"})
                continue
            country,item=key.split(":",1)
            args=[sys.executable,"-m",PINNED_WORKERS[key],"--db",
                  str(stock_db),"--country",country,"--item",item,
                  "--now",str(now)]
            t0=clock()
            try:
                p=runner(args,capture_output=True,text=True,check=False,
                         timeout=min(worker_seconds,remaining))
                if p.returncode or len(p.stdout)>8192:
                    output={"status":"WORKER_ERROR"}
                else:
                    output=json.loads(p.stdout)
                    if not isinstance(output,dict):
                        output={"status":"INVALID_WORKER_OUTPUT"}
            except subprocess.TimeoutExpired:
                output={"status":"WORKER_TIMEOUT"}
            except (OSError,ValueError,json.JSONDecodeError):
                output={"status":"WORKER_ERROR"}
            row=side.execute("SELECT stock_as_of FROM v38_stock_state WHERE item_key=?",
                             (key,)).fetchone()
            last=row[0] if row else None
            elapsed=int((clock()-t0)*1000)
            model=roster[key]
            status=record(side,key=key,family=model["model_family"],
                          config=model.get("config_name"),
                          output=output,now=now,stock_as_of=last,
                          executed=True,elapsed_ms=elapsed)
            results.append({"item_key":key,"status":status,"elapsed_ms":elapsed})
        return {"mode":"EXECUTED_RESEARCH_ONLY","delta":delta,
                "plan":plan,"executed":results,"collector_written":False}
    finally:
        side.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",default="/opt/torn-fren/data/stock_history.db")
    p.add_argument("--sidecar",required=True)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--active",action="append",default=[])
    p.add_argument("--max-rows",type=int,default=10000)
    p.add_argument("--max-jobs",type=int,default=4)
    p.add_argument("--per-worker",type=float,default=20)
    p.add_argument("--budget",type=float,default=85)
    args=p.parse_args()
    out=run_tick(stock_db=args.db,sidecar_db=args.sidecar,
                 execute=args.execute,active=args.active,max_rows=args.max_rows,
                 max_jobs=args.max_jobs,worker_seconds=args.per_worker,
                 budget_seconds=args.budget)
    print(json.dumps(out,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
