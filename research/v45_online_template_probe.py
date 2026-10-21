"""V45: one causally resolved original Monkey/Chamois expert replay probe.

Research only, no scheduling or predictions, no collector writes.
"""
from __future__ import annotations
import argparse
import json
import math
import time
from types import SimpleNamespace
from research.v46_fast_template import FastTemplatePlanner

from services.frozen_candidate_worker_v31 import inspect_live_source
from research.plushie_champions.common import (
    connect, load_gaps, Timeline, TemplatePlanner, gap_overlap,
    STEP, MAX_WAIT, DAY, GRACE, TRAVEL_SECONDS,
)

EXPERTS=tuple(
    (lags,look,shift)
    for lags in ((1,),(2,),(7,),(1,2),(1,7),(1,2,7))
    for look in (7200,14400)
    for shift in (3600,7200)
)
TARGETS={"monkey":("arg","Monkey Plushie",2),
         "chamois":("swi","Chamois Plushie",3)}
STRIDE=1800

def latest_fully_resolved_start(timeline,gs,ge,country,now):
    latest=math.floor((now-MAX_WAIT-TRAVEL_SECONDS[country]-GRACE)/STRIDE)*STRIDE
    earliest=math.ceil((timeline.ts[0]+8*DAY)/STRIDE)*STRIDE
    if latest<earliest:
        return None
    for start in range(latest,max(earliest,latest-2*DAY)-1,-STRIDE):
        state,_,_=timeline.vals([start])
        if math.isnan(float(state[0])):
            continue
        if gap_overlap(gs,ge,start,start+MAX_WAIT+TRAVEL_SECONDS[country]+GRACE):
            continue
        return start
    return None

def simulate_one(planner,timeline,start,travel):
    q=float(start);deadline=float(start+MAX_WAIT);sched=None
    while q<=deadline:
        z=planner(q)
        if z and z[0]<=deadline:
            sched=z
        if sched and sched[0]<=q+STEP:
            dep=max(q,sched[0])
            return {"status":"RESOLVED_EXPERT_DECISION",
                    "success":int(timeline.success(dep+travel,GRACE)),
                    "departure":int(dep),"arrival":int(dep+travel),
                    "resolved_at":int(dep+travel+GRACE)}
        q+=STEP
    return {"status":"NO_RESOLVED_EXPERT_DECISION",
            "success":None,"resolved_at":None}

def probe(db,target,expert_index,now,*,compare_fast=False):
    if target not in TARGETS or not 0<=expert_index<len(EXPERTS):
        raise ValueError("unsupported target or expert")
    country,item,days=TARGETS[target];now=int(now)
    source=inspect_live_source(db,now)
    if source.get("status")!="FRESH":
        return {"status":source.get("status","COLLECTOR_STALE_OR_FUTURE")}
    con=connect(db,readonly=True)
    try:
        con.execute("BEGIN")
        gs,ge=load_gaps(con)
        timeline=Timeline(con,gs,ge,country,item)
        if timeline.ts[-1]>now:
            return {"status":"FUTURE_STOCK_ROWS_REJECTED"}
        start=latest_fully_resolved_start(timeline,gs,ge,country,now)
        if start is None:
            return {"status":"NO_RESOLVED_ANCHOR"}
        lags,look,shift=EXPERTS[expert_index]
        ctx=SimpleNamespace(timelines={(country,item):timeline})
        planner=TemplatePlanner(ctx,country,item,
                                lags=lags,lookback=look,shift_range=shift)
        t0=time.monotonic()
        outcome=simulate_one(planner.plan,timeline,start,TRAVEL_SECONDS[country])
        original_seconds=round(time.monotonic()-t0,3)
        comparison=None
        if compare_fast:
            accelerated=FastTemplatePlanner(ctx,country,item,
                                            lags=lags,lookback=look,
                                            shift_range=shift)
            t1=time.monotonic()
            fast_outcome=simulate_one(accelerated.plan,timeline,start,
                                     TRAVEL_SECONDS[country])
            fast_seconds=round(time.monotonic()-t1,3)
            if fast_outcome!=outcome:
                return {"status":"SOURCE_PARITY_MISMATCH",
                        "key":f"{country}:{item}",
                        "expert_index":expert_index,
                        "original_decision":outcome,
                        "accelerated_decision":fast_outcome}
            comparison={"original_seconds":original_seconds,
                        "optimized_seconds":fast_seconds,
                        "same_outcome":True}
    finally:
        con.close()
    return {"status":"EXPERT_REPLAY_PARITY_OK" if compare_fast else outcome["status"],
            "comparison":comparison,
            "key":f"{country}:{item}",
            "expert_index":expert_index,
            "expert":{"lags":list(lags),"lookback_seconds":look,
                      "shift_seconds":shift},
            "start":start,"resolved_performance_window_days":days,
            "decision":outcome,
            "research_only":True,
            "source":"SOURCE_PINNED_CHECKPOINT4_EXPERT_REPLAY",
            "writes_to_collector":False,
            "published_to_website":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--target",choices=tuple(TARGETS),required=True)
    p.add_argument("--expert-index",type=int,default=0)
    p.add_argument("--now",required=True,type=int)
    p.add_argument("--compare-fast",action="store_true",help="Check identical original and optimized decisions")
    a=p.parse_args()
    try:
        result=probe(a.db,a.target,a.expert_index,a.now,compare_fast=a.compare_fast)
    except Exception as exc:
        result={"status":"EXPERT_REPLAY_ERROR","error_type":type(exc).__name__}
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
