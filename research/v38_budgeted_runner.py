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
from research.v38_adaptive_policy import next_due_seconds
from research.v38_capacity_guard import inspect as capacity_status

ROSTER=Path(__file__).with_name("v38_roster.json")
RED_FOX_KEY="uni:Red Fox Plushie"
RED_FOX_WORKER="research.v38_red_fox_single_tick"

# V42 requires an explicit opt-in. Default 16-candidate worker routing and
# all V38 callers stay unchanged; Japan Xanax is NOT a generic candidate.
V42_XANAX_ROSTER = {
    "can:Xanax": {"category":"other", "model_family":"v19", "config_name":"dyn8"},
    "uni:Xanax": {"category":"other", "model_family":"v19", "config_name":"dyn3"},
}
V42_XANAX_ROUTES = {
    key: "research.v42_xanax_candidate_tick" for key in V42_XANAX_ROSTER
}



def choose(roster, snapshots, *, now, active=(), changed=(), limit=4, routes=None):
    """Fixed source-pinned 16 of 22; never substitute for six missing winners."""
    active,changed=set(active),set(changed)
    routes = PINNED_WORKERS if routes is None else routes
    due=[]
    pending=[]
    for key,meta in roster.items():
        if key not in routes:
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
             approved_keys=None, max_rows=10000, max_jobs=4, worker_seconds=20,
             budget_seconds=85, now=None, with_xanax=False, with_redfox=False, runner=subprocess.run,
             clock=time.monotonic, capacity_probe=capacity_status):
    if with_redfox and not with_xanax:
        raise ValueError("Red Fox requires the measured 18-worker base")
    capacity=19 if with_redfox else 18 if with_xanax else 16
    if not 1<=max_jobs<=capacity or not 1<=worker_seconds<=60:
        raise ValueError("invalid concurrency/resource limits")
    if not worker_seconds<=budget_seconds<=240:
        raise ValueError("invalid total wall budget")
    live_clock = now is None
    now=int(time.time() if live_clock else now)
    roster=json.loads(ROSTER.read_text(encoding="utf-8"))["items"]
    workers=dict(PINNED_WORKERS)
    if with_xanax:
        roster={**roster, **V42_XANAX_ROSTER}
        workers.update(V42_XANAX_ROUTES)
    if with_redfox:
        # The original k18/global-0.5 adapter was separately VM benchmarked.
        # This flag never changes the default 16 or existing 18-item routing.
        workers[RED_FOX_KEY]=RED_FOX_WORKER
    # Explicit allowlisting supports a first-five isolation test without
    # accidentally executing every runnable model in the 21-item roster.
    # Unknown keys abort before any collector or research DB access.
    if approved_keys is not None:
        approved=set(approved_keys)
        unknown=approved.difference(roster)
        if unknown:
            raise ValueError(f"unknown research allowlisted items: {sorted(unknown)}")
        roster={key:meta for key,meta in roster.items() if key in approved}
    # Plan-only does not even create the sidecar or access the stock database.
    if not execute:
        snapshots={p["item_key"]:p for p in read(sidecar_db,now) if "item_key" in p}
        return {"mode":"PLAN_ONLY","plan":choose(roster,snapshots,now=now,
                active=active,limit=max_jobs,routes=workers),"collector_written":False}
    capacity=capacity_probe()
    if not capacity["allowed"]:
        return {"mode":"DEFERRED_CPU_PRESSURE","capacity":capacity,
                "executed":[],"collector_written":False}
    side=open_writer(sidecar_db)
    try:
        delta=observe(stock_db,side,max_rows=max_rows,fast_bootstrap=True)
        if not delta["caught_up"]:
            return {"mode":"SOURCE_BOOTSTRAP","delta":delta,
                    "executed":[],"collector_written":False}
        # The collector saves stock_history rows only on quantity changes.
        # Do not mark a quiet but successfully-polled item as stale, nor
        # consider an old changed-row sufficient proof of fresh observation.
        heartbeat=delta.get("verified_heartbeat")
        if heartbeat is None or not 0 <= now-int(heartbeat) <= 180:
            return {"mode":"COLLECTOR_STALE_OR_NO_HEARTBEAT",
                    "delta":delta,"executed":[],"collector_written":False}
        snaps={p["item_key"]:p for p in read(sidecar_db,now) if "item_key" in p}
        plan=choose(roster,snaps,now=now,active=active,
                    changed=delta["affected_keys"],limit=max_jobs,routes=workers)
        start=clock()
        results=[]
        for key in plan["execute"]:
            remaining=budget_seconds-(clock()-start)
            if remaining<1:
                results.append({"item_key":key,"status":"DEFERRED_BUDGET"})
                continue
            country,item=key.split(":",1)
            # The poller continues inserting stock rows while 5 independent
            # models run serially. The first tick timestamp becomes stale;
            # never feed later models that old --now or they will (correctly)
            # reject newly observed rows as FUTURE_RECORDS_PRESENT.
            # Explicit 'now' remains frozen for deterministic historical tests.
            worker_now=max(now,int(time.time())) if live_clock else now
            args=[sys.executable,"-m",workers[key],"--db",
                  str(stock_db),"--country",country,"--item",item,
                  "--now",str(worker_now)]
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
            # Attest the current observation with the verified poll cycle,
            # not the last item CHANGE row. A quiet market is still observed.
            last=int(heartbeat)
            elapsed=int((clock()-t0)*1000)
            model=roster[key]
            delay=next_due_seconds(worker_status=str(output.get("status")),
                active=key in active,stock_changed=key in delta["affected_keys"])
            status=record(side,key=key,family=model["model_family"],
                          config=model.get("config_name"),
                          output=output,now=worker_now,stock_as_of=last,
                          # Replan cadence is anchored to the 5-minute tick,
                          # not each serial worker's variable start offset.
                          executed=True,elapsed_ms=elapsed,next_due=now+delay)
            item_result={"item_key":key,"status":status,"elapsed_ms":elapsed}
            # Private journal identifiers only: never log raw paths or errors.
            if status!="RESEARCH_PROPOSAL_ONLY":
                value=output.get("error_type")
                if isinstance(value,str) and len(value)<=80:
                    item_result["error_type"]=value
                # Research-only exception fingerprint. Never propagate raw
                # exception messages, raw SQL, paths or arbitrary model data.
                # These fields appear in the PRIVATE systemd journal only;
                # nothing is added to prediction_store or the public API.
                import re
                tag=output.get("error_tag")
                if isinstance(tag,str) and re.fullmatch(r"[A-Z0-9_]{1,72}",tag):
                    item_result["error_tag"]=tag
                module=output.get("error_module")
                if module in (
                    "history_service.py","private_v18_champion_worker_v35.py",
                    "frozen_candidate_worker_v31.py","common.py",
                    "plushie_flower_dynamic_planner_v18.py",
                    "plushie_flower_dynamic_planner_v19.py",
                    "plushie_flower_dynamic_planner_v20.py",
                    "v38_v18_single_tick.py","v38_v19_single_tick.py",
                    "v38_red_fox_single_tick.py","v38_readonly_retry.py"):
                    item_result["error_module"]=module
                    line=output.get("error_line")
                    if type(line) is int and 0<line<100000:
                        item_result["error_line"]=line
            results.append(item_result)
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
    p.add_argument("--with-xanax",action="store_true",help="Opt into two frozen generic v19 Canada and UK candidates; NOT Japan")
    p.add_argument("--with-redfox",action="store_true",help="Opt into source-pinned Red Fox k18 global-regime analog after VM resource gate")
    p.add_argument("--allow-item",action="append",default=None,
                   help="Repeat to limit runs to an explicitly approved subset")
    p.add_argument("--max-rows",type=int,default=10000)
    p.add_argument("--max-jobs",type=int,default=4)
    p.add_argument("--per-worker",type=float,default=20)
    p.add_argument("--budget",type=float,default=85)
    args=p.parse_args()
    out=run_tick(stock_db=args.db,sidecar_db=args.sidecar,
                 execute=args.execute,active=args.active,max_rows=args.max_rows,
                 max_jobs=args.max_jobs,worker_seconds=args.per_worker,
                 approved_keys=args.allow_item,budget_seconds=args.budget,
                 with_xanax=args.with_xanax,
                 with_redfox=args.with_redfox)
    print(json.dumps(out,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
