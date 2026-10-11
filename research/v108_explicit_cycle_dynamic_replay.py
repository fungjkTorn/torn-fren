"""V108 offline dynamic replay: explicit restock cycles vs incumbent champions.

V107 is a new simple replenishment->depletion model, NOT a champion.
Compare Red Fox and Nessie 25-start holdout:
 * unchanged champion five-minute replanning (native dynamic_replay)
 * V107 earliest expected, based only on previously completed cycles
 * V107 conservative projected window, only if empirical bounds overlap
 * leave immediately

Both window policies re-evaluate each five-minute tick; departures must
remain supported by the most recent cycle forecast. No automatic gameplay.
Use completed observation transitions no later than the simulated query.

This is a diagnostic on a previously inspected holdout; do not turn sampled
proxy outcomes into calibrated accuracy or a claim of independent restocks.
The historical collector is change-only and did not store per-country YATA
provider update epochs. The existing research preprocessing may use later
observations to filter isolated source bounces; results are not a pristine
causal prospective experiment. Open approved collector read-only.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter

import numpy as np

from research.plushie_champions.common import (
    PLUSHIES,ResearchContext,TRAVEL_SECONDS,STEP,MAX_WAIT,GRACE,
    dynamic_replay,valid_starts
)
from research.v104_real_champion_earliest_replay import (
    PILOTS,model_for,select_starts,SOURCE
)
from research.v107_explicit_restock_cycle_baseline import (
    StockObservation,next_windows
)
from research.v60_private_snapshot_probe import approved_collector_source

STRATEGIES=("champion","cycle_expected","cycle_cautious","depart_now")
MAX_EPISODES=25


def _window_proposals(research):
    windows=research["windows"]
    return {
        "cycle_expected":min((
            v["earliest_expected_departure"] for v in windows
            if v["earliest_expected_departure"] is not None),default=None),
        "cycle_cautious":min((
            v["earliest_conservative_departure"] for v in windows
            if v["earliest_conservative_departure"] is not None),default=None)
    }


def simulate_cycle_policies(start,item_key,observations,gaps,*,forecast=next_windows):
    start=int(start)
    dep={"depart_now":start,"cycle_expected":None,"cycle_cautious":None}
    status=Counter()
    first_window_examples=[]
    iterations=0
    for q in range(start,start+MAX_WAIT+1,STEP):
        if all(dep[x] is not None for x in (
            "cycle_expected","cycle_cautious")):
            break
        iterations+=1
        result=forecast(item_key,observations,asof=q,collection_gaps=gaps)
        status[result["status"]]+=1
        if not first_window_examples and result["windows"]:
            first_window_examples=result["windows"][:2]
        plans=_window_proposals(result)
        for label in ("cycle_expected","cycle_cautious"):
            if dep[label] is not None:
                continue
            candidate=plans[label]
            # Projection rechecked at current tick. It must be a currently
            # model-supported reachable departure, not a stale old plan.
            if candidate is not None and q<=candidate<=start+MAX_WAIT:
                if candidate<=q+STEP:
                    dep[label]=int(candidate)
    return {
        "departures":dep,"forecast_tick_count":iterations,
        "forecast_statuses":dict(status),
        "first_prediction_windows":first_window_examples
    }


def compare(ctx,target,episodes):
    country,item=PILOTS[target]
    item_key=f"{country}:{item}"
    starts=valid_starts(ctx,country,item)
    hold=starts[int(.75*len(starts)):]
    query_starts=[int(x) for x in select_starts(starts,episodes)]
    if not query_starts:
        return {"item_key":item_key,"status":"NO_HISTORIC_HOLDOUT_STARTS"}
    planner=model_for(ctx,target,hold[0])
    tl=ctx.timelines[(country,item)]
    flight=TRAVEL_SECONDS[country]
    champion=dynamic_replay(
        tl,planner.plan,[float(s) for s in query_starts],flight,
        refresh=STEP,max_wait=MAX_WAIT)
    champion_by_start={
        int(s):(None if d is None else int(d))
        for s,d,_,_ in champion["details"]
    }
    obs=[StockObservation(int(t),int(q),str(source))
         for t,q,source in tl.rows]
    gap_intervals=[
        (int(a),None if int(b)>=9_999_999_999 else int(b))
        for a,b in zip(ctx.gs,ctx.ge)]
    records=[]
    status=Counter()
    for start in query_starts:
        result=simulate_cycle_policies(start,item_key,obs,gap_intervals)
        depart={
            "champion":champion_by_start[start],
            **result["departures"]
        }
        _,qty,_=tl.vals(np.array([float(start)]))
        initial=("UNKNOWN" if np.isnan(qty[0]) else
                 "BELOW_30" if qty[0]<30 else "AT_LEAST_30")
        hits={
            k:(None if d is None else bool(tl.success(d+flight,GRACE)))
            for k,d in depart.items()
        }
        status.update(result["forecast_statuses"])
        records.append({
            "issue":start,"initial_stock":initial,
            "departures":depart,"hits":hits,
            "first_projected_windows":result["first_prediction_windows"],
        })
    def metrics(rows):
        output={}
        for label in STRATEGIES:
            good=[r for r in rows if r["departures"][label] is not None]
            win=sum(int(r["hits"][label]) for r in good)
            waits=[(r["departures"][label]-r["issue"])/60 for r in good]
            paired=Counter()
            if label!="champion":
                for r in rows:
                    a=r["hits"]["champion"]
                    b=r["hits"][label]
                    if a is None or b is None:paired["unpaired"]+=1
                    elif a and b:paired["both_success"]+=1
                    elif a:paired["champion_only"]+=1
                    elif b:paired["cycle_or_now_only"]+=1
                    else:paired["both_fail"]+=1
            output[label]={
                "start_count":len(rows),
                "departures":len(good),"proxy_hits":win,
                "proxy_misses":len(good)-win,
                "successes_per_start":round(win/len(rows),4) if rows else None,
                "mean_wait_minutes":round(statistics.mean(waits),1)
                                    if waits else None,
                "paired_with_champion":dict(paired),
            }
        return output
    return {
        "item_key":item_key,
        "start_count":len(records),
        "completed_cycles_required":5,
        "forecast_status_tick_counts":dict(status),
        "all":metrics(records),
        "below30":metrics([r for r in records
                           if r["initial_stock"]=="BELOW_30"]),
        "atleast30":metrics([r for r in records
                             if r["initial_stock"]=="AT_LEAST_30"]),
        "first_two_replay_samples":records[:2],
    }


def pretty(out):
    print("===== V108 PREDICT RESTOCK/DEPLETION -> EARLIEST REACHABLE FLIGHT =====")
    print("New V107 empirical baseline vs original champions, 5-minute replans.")
    for target,r in out["items"].items():
        print("====",target,r["item_key"],"====")
        print("starts:",r["start_count"])
        print("forecast_tick_statuses:",json.dumps(
            r["forecast_status_tick_counts"],sort_keys=True))
        for category in ("all","below30","atleast30"):
            print("----",category,"----")
            for name,d in r[category].items():
                print(f'{name:18} starts={d["start_count"]:2} '
                      f'departs={d["departures"]:2} hits={d["proxy_hits"]:2} '
                      f'misses={d["proxy_misses"]:2} '
                      f'avg_wait_min={d["mean_wait_minutes"]}')
                if name!="champion":
                    print("   matched:",json.dumps(
                        d["paired_with_champion"],sort_keys=True))
        print("first historical projected window:",
              json.dumps(r["first_two_replay_samples"][:1],sort_keys=True))
    print("===== RESEARCH ONLY: NO VERIFIED REAL PLAYER OUTCOMES =====")
    print("Prior inspected holdout; YATA per-country update epochs unavailable.")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=["redfox","nessie","both"],
                   default="both")
    p.add_argument("--episodes",type=int,default=5)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not 1<=args.episodes<=MAX_EPISODES:
        p.error(f"episodes outside 1..{MAX_EPISODES}")
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved historical collector source")
    targets=list(PILOTS) if args.target=="both" else [args.target]
    start=time.monotonic()
    ctx=ResearchContext.build(SOURCE,targets=PLUSHIES,readonly=True)
    try:
        out={
            "status":"V108_EXPLICIT_RESTOCK_CYCLE_DYNAMIC_REPLAY",
            "source_read_only":True,"actual_flights_observed":False,
            "replanning_seconds":STEP,"holdout_previously_inspected":True,
            "country_provider_freshness_verified":False,
            "independent_restock_cycles_verified":False,
            "item_specific_champions_changed":False,
            "items":{t:compare(ctx,t,args.episodes) for t in targets}
        }
    finally:
        ctx.con.close()
    out["elapsed_seconds"]=round(time.monotonic()-start,2)
    if args.json:
        print(json.dumps(out,sort_keys=True))
    else:
        pretty(out)
        print("total_elapsed_seconds:",out["elapsed_seconds"])


if __name__=="__main__":
    main()
