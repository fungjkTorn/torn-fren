"""V105 actual champion-versus-earliest 5-minute dynamic travel replay.

For historic starts, recompute the SAME champion model every five minutes.
Compare (a) incumbent untouched champion; (b) earliest departure on the
SAME as-of arrival availability curve at three PREDECLARED raw-score floors;
(c) leave immediately. Preserve original eight-hour planning limit, same
flight duration, >=30 stock threshold, and +10s evaluation grace.

A model only sees its own historical-score observations at/before query.
Observed future stock is consulted ONLY to score after a plan is executed.
Episodes may overlap actual restocks; results are diagnostic, not independent
samples or provider-fresh exact availability. Previously inspected historical
holdout is not a pristine blind test. Research-only read-only source.

No modifications to production, champion code, DB, prediction workers, site
or gameplay. One shared model-score curve per 5-minute tick / item.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter, defaultdict
from functools import lru_cache

import numpy as np

from research.plushie_champions.common import (
    AnalogPlanner,TemplatePlanner,ResearchContext,PLUSHIES,valid_starts,
    TRAVEL_SECONDS,GRACE,MAX_WAIT,STEP,dynamic_replay
)
from research.v103_champion_score_curves import score_curve,earliest_from_curve
from research.v104_real_champion_earliest_replay import (
    PILOTS,DEFAULT_FLOORS,model_for,select_starts,SOURCE
)
from research.v60_private_snapshot_probe import approved_collector_source

MAX_EPISODES=25
MAX_TOTAL_TICKS=20000
THRESHOLD=30
STRATEGIES=("champion","earliest_0.40","earliest_0.55","earliest_0.70","depart_now")


def _strategy_decisions(*,start,planner,curve_at,labels=STRATEGIES):
    """Generate every strategy from as-of information, score none here."""
    start=int(start)
    deadline=start+MAX_WAIT
    schedules={label:None for label in labels if label!="depart_now"}
    finished={"depart_now":start}
    candidates_seen=Counter()
    iterations=0
    q=start
    while q<=deadline and len(finished)<len(labels):
        iterations+=1
        # Get model decisions without touching future result state.
        active=[label for label in schedules if label not in finished]
        if "champion" in active:
            candidate=planner.plan(q)
            if candidate is not None and q<=candidate[0]<=deadline:
                schedules["champion"]=(int(candidate[0]),float(candidate[1]))
                candidates_seen["champion"]+=1
        curve=None
        if any(label.startswith("earliest_") for label in active):
            curve=curve_at(q)
        for label in active:
            if label=="champion":
                continue
            floor=float(label.removeprefix("earliest_"))
            candidate=earliest_from_curve(q,curve,floor=floor)
            if candidate is not None and q<=candidate[0]<=deadline:
                schedules[label]=candidate
                candidates_seen[label]+=1
        # Identical five-minute replanning trigger as common.dynamic_replay.
        for label in active:
            current=schedules[label]
            if current is not None and current[0]<=q+STEP:
                finished[label]=max(q,int(current[0]))
        q+=STEP
    return {
        "departures":{label:finished.get(label) for label in labels},
        "ticks":iterations,"candidates_seen":dict(candidates_seen),
    }


def compare_policy_dynamic(starts,*,tl,planner,curve_function,travel,
                           thresholds=DEFAULT_FLOORS):
    """Directly comparable same-start replay with original incumbent parity."""
    labels=("champion",)+tuple(
        f"earliest_{t:.2f}" for t in thresholds)+("depart_now",)
    cache={}
    model_calls=0
    def curve_at(q):
        nonlocal model_calls
        if q not in cache:
            cache[q]=curve_function(planner,q)
            model_calls+=1
        return cache[q]
    episode_results=[]
    for start in starts:
        s=int(start)
        selected=_strategy_decisions(
            start=s,planner=planner,curve_at=curve_at,labels=labels)
        if selected["ticks"]>MAX_WAIT//STEP+1:
            raise AssertionError("unbounded planner replay")
        for label,depart in selected["departures"].items():
            if depart is not None and not s<=depart<=s+MAX_WAIT:
                raise AssertionError("invalid replay departure")
        active,qty,_=tl.vals(np.array([float(s)]))
        stock_at_start=(None if np.isnan(qty[0]) else float(qty[0]))
        initial_state=("UNSCORABLE_SOURCE" if stock_at_start is None else
                       "BELOW_30" if stock_at_start<THRESHOLD else
                       "AT_LEAST_30")
        observed={}
        for label,depart in selected["departures"].items():
            observed[label]=None if depart is None else bool(
                tl.success(depart+travel,GRACE))
        episode_results.append({
            "issue_epoch":s,
            "initial_stock_state":initial_state,
            "initial_quantity":stock_at_start,
            "departures":selected["departures"],
            "hits":observed,
            "ticks":selected["ticks"],
        })
    # Compare directly to the native champion's independent dynamic replay
    # over the EXACT SAME historical start set, not to historic global scores.
    original=dynamic_replay(
        tl,planner.plan,[float(s) for s in starts],travel,
        refresh=STEP,max_wait=MAX_WAIT)
    expected={int(s):(
        None if dep is None else int(dep),
        bool(hit) if dep is not None else None)
        for s,dep,arr,hit in original["details"]}
    for rec in episode_results:
        s=rec["issue_epoch"]
        dep,hit=expected[s]
        if rec["departures"]["champion"]!=dep or rec["hits"]["champion"]!=hit:
            raise AssertionError("CHAMPION_DYNAMIC_REPLAY_PARITY_FAILED")

    totals={}
    by_start_state={}
    for key in ("ALL","BELOW_30","AT_LEAST_30","UNSCORABLE_SOURCE"):
        recs=episode_results if key=="ALL" else [
            r for r in episode_results if r["initial_stock_state"]==key]
        counts={}
        n=len(recs)
        for label in labels:
            valid=[r for r in recs if r["departures"][label] is not None]
            wins=sum(int(r["hits"][label] is True) for r in valid)
            waits=[(r["departures"][label]-r["issue_epoch"])/60
                   for r in valid]
            paired=Counter()
            if label!="champion":
                for r in recs:
                    a=r["hits"]["champion"]
                    b=r["hits"][label]
                    if a is None or b is None:
                        paired["abstention_in_pair"]+=1
                    elif a and b:
                        paired["both_win"]+=1
                    elif a:
                        paired["champion_only"]+=1
                    elif b:
                        paired["alternative_only"]+=1
                    else:
                        paired["both_miss"]+=1
            counts[label]={
                "episodes":n,
                "departures":len(valid),"proxy_successes":wins,
                "proxy_misses":len(valid)-wins,
                "coverage":round(len(valid)/n,4) if n else None,
                "success_per_issued_start":round(wins/n,4) if n else None,
                "proxy_hit_rate_when_departed":round(wins/len(valid),4)
                                              if valid else None,
                "average_wait_minutes":round(statistics.mean(waits),2)
                                       if waits else None,
                "median_wait_minutes":round(statistics.median(waits),2)
                                      if waits else None,
                "matched_vs_champion":dict(paired),
            }
        if key=="ALL":
            totals=counts
        else:
            by_start_state[key]=counts
    return {
        "start_count":len(starts),
        "distinct_model_score_queries":model_calls,
        "replay_total_ticks":sum(r["ticks"] for r in episode_results),
        "champion_dynamic_parity_verified":True,
        "methods":totals,
        "by_initial_stock_state":by_start_state,
        "illustrative_episodes":episode_results[:3],
    }


def inspect_item(ctx,target,episodes):
    country,item=PILOTS[target]
    tl=ctx.timelines[(country,item)]
    starts=valid_starts(ctx,country,item)
    hold=starts[int(.75*len(starts)):]
    selected=select_starts(starts,episodes)
    if not hold or not selected:
        return {"item_key":f"{country}:{item}",
                "status":"NO_HOLDOUT_REPLAY_EPISODES"}
    planner=model_for(ctx,target,hold[0])
    t0=time.monotonic()
    results=compare_policy_dynamic(
        [int(s) for s in selected],
        tl=tl,planner=planner,curve_function=score_curve,
        travel=TRAVEL_SECONDS[country])
    results["item_key"]=f"{country}:{item}"
    results["historical_holdout_start_count"]=len(hold)
    results["elapsed_seconds"]=round(time.monotonic()-t0,2)
    return results


def pretty(report):
    print("===== V105 CHAMPION DYNAMIC 5M REPLAY VS EARLIEST SCORED RESTOCK WINDOW =====")
    print("Model raw scores are NOT calibrated actual success probabilities.")
    print("Simulated hypothetical departures, NOT player flights. Previously inspected holdout.")
    for key,entry in report["items"].items():
        print(f'===== {key.upper()} / {entry["item_key"]} =====')
        print("starts:",entry["start_count"],
              "score_curve_model_queries:",entry["distinct_model_score_queries"],
              "replay_ticks:",entry["replay_total_ticks"],
              "elapsed_s:",entry["elapsed_seconds"])
        print(f'{"METHOD":24} {"COVER":>6} {"HITS":>5} {"MISS":>5} {"HIT/START":>9} {"HIT/DEPART":>10} {"WAIT AVG":>9}')
        for name,c in entry["methods"].items():
            print(f'{name:24} {c["departures"]:6} '
                  f'{c["proxy_successes"]:5} {c["proxy_misses"]:5} '
                  f'{str(c["success_per_issued_start"]):>9} '
                  f'{str(c["proxy_hit_rate_when_departed"]):>10} '
                  f'{str(c["average_wait_minutes"]):>9}')
            if name!="champion":
                print("    versus champion:",json.dumps(
                    c["matched_vs_champion"],sort_keys=True))
        print("STOCK BELOW 30 AT ORIGINAL ISSUE:")
        for name,c in entry["by_initial_stock_state"]["BELOW_30"].items():
            print(f'  {name:24} start_n={c["episodes"]} '
                  f'hits={c["proxy_successes"]} departures={c["departures"]} '
                  f'avg_wait={c["average_wait_minutes"]}')
        print("STOCK ALREADY >=30 AT ORIGINAL ISSUE:")
        for name,c in entry["by_initial_stock_state"]["AT_LEAST_30"].items():
            print(f'  {name:24} start_n={c["episodes"]} '
                  f'hits={c["proxy_successes"]} departures={c["departures"]} '
                  f'avg_wait={c["average_wait_minutes"]}')
        print("first replay samples:",json.dumps(
            entry["illustrative_episodes"][:1],sort_keys=True))
    print("===== NO LIVE CHANGES / RESULTS NOT INDEPENDENT RESTOCKS =====")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=["redfox","nessie","both"],default="both")
    p.add_argument("--episodes",type=int,default=6)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not 1<=args.episodes<=MAX_EPISODES:
        p.error(f"episodes must be 1..{MAX_EPISODES}")
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved source")
    targets=list(PILOTS) if args.target=="both" else [args.target]
    t0=time.monotonic()
    ctx=ResearchContext.build(SOURCE,targets=PLUSHIES,readonly=True)
    try:
        report={
            "status":"V105_SAME_MODEL_DYNAMIC_5M_EARLIEST_VS_CHAMPION",
            "read_only":True,
            "sidecar_or_live_services_changed":False,
            "actual_player_flights_observed":False,
            "certified_country_provider_freshness":False,
            "calibrated_hit_probabilities":False,
            "independent_restock_events":False,
            "holdout_previously_inspected":True,
            "episodes_per_target":args.episodes,
            "raw_score_thresholds":[.40,.55,.70],
            "items":{target:inspect_item(ctx,target,args.episodes)
                     for target in targets},
        }
    finally:
        ctx.con.close()
    report["total_elapsed_seconds"]=round(time.monotonic()-t0,2)
    if args.json:
        print(json.dumps(report,sort_keys=True))
    else:
        pretty(report)
        print("total_elapsed_seconds:",report["total_elapsed_seconds"])


if __name__=="__main__":
    main()
