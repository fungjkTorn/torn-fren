"""V106 research-only item-aware risk-adjusted earliest departure replay.

Evaluate original champion against SAME champion model's earliest-supported
departure using a *relative loss budget* from the strongest projected
availability on the future arrival curve. For analog models require both
raw availability score and robust score to stay near their respective peak;
template models use their model-native raw curve. Require a contiguous
10-minute score-supported window (2 adjacent 5-minute points).

This is a model-derived stock availability WINDOW, not a made-up 10/20m
delay. It is NOT the actual predicted restock onset/depletion timing:
original champions predict probability-like >=30 state, not exact boundaries.

For each historic starting time, each policy replans at the same 5m cadence,
with identical 8h original horizon and +10s/quantity>=30 outcome criterion.
Champion is checked against original dynamic_replay for exact parity.
Historical stock outcomes are read ONLY after departures are selected.
The same 25 inspected holdout starting points are exploratory, NOT a
pristine lockbox or independent 25 restocks. Source read-only.

No live VM, API, collectors, website, source DB, or stock manipulation.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter

import numpy as np

from research.plushie_champions.common import (
    ResearchContext,PLUSHIES,valid_starts,TRAVEL_SECONDS,GRACE,
    STEP,MAX_WAIT,dynamic_replay,AnalogPlanner
)
from research.v103_champion_score_curves import score_curve,earliest_from_curve
from research.v104_real_champion_earliest_replay import (
    PILOTS,model_for,select_starts,SOURCE
)
from research.v60_private_snapshot_probe import approved_collector_source

# Prespecified RESEARCH parameters, not calibrated rates or selected winners.
DELTA_BUDGETS=(.03,.08,.15)
ABSOLUTE_FLOOR=.55
CONTIGUOUS_POINTS=2
MAX_EPISODES=25


def earliest_risk_budget(q,curve,*,loss_budget,
                         absolute_floor=ABSOLUTE_FLOOR,
                         min_points=CONTIGUOUS_POINTS,
                         previous_departure=None):
    """Earliest supported future arrival, within gap of model's own peak.

    Analog models additionally require nearby robustness to remain within
    the same loss budget; cannot choose an isolated high-score spike.
    """
    if curve is None:
        return None
    delays=np.asarray(curve["delay_seconds"])
    score=np.asarray(curve["availability_score"])
    if (len(delays)!=len(score) or len(score)==0
        or not np.all(np.isfinite(score))
        or not 0<=loss_budget<=1):
        return None
    peak=float(np.max(score))
    threshold=max(absolute_floor,peak-loss_budget)
    robust=curve.get("robust_score")
    if robust is not None:
        robust=np.asarray(robust)
        if len(robust)!=len(score) or not np.all(np.isfinite(robust)):
            return None
        robust_min=float(np.max(robust))-loss_budget
    else:
        robust_min=None

    # Restrict candidate score points to those near both model-native peaks.
    qualifying=[]
    for idx in range(len(delays)):
        okay=(score[idx]>=threshold
              and (robust_min is None or robust[idx]>=robust_min))
        if okay:
            qualifying.append(idx)
    # Mark every grid point within a contiguous well-supported forecast
    # window. If an existing absolute departure is still supported in the
    # NEW as-of score curve, retain it rather than chasing a shifting peak.
    supported=set()
    for i in qualifying:
        if all((i+j<len(delays)
                and int(delays[i+j])-int(delays[i])==j*STEP
                and score[i+j]>=threshold
                and (robust_min is None or robust[i+j]>=robust_min))
               for j in range(min_points)):
            for j in range(min_points):
                supported.add(i+j)
    if not supported:
        return None
    if previous_departure is not None:
        if int(previous_departure)>=int(q):
            for idx in sorted(supported):
                if int(q)+int(delays[idx])==int(previous_departure):
                    return (int(previous_departure),float(score[idx]))
    i=min(supported)
    return (int(q)+int(delays[i]),float(score[i]))


def simulate_one(start,planner,curve_for,labels):
    start=int(start);limit=start+MAX_WAIT;q=start
    schedules={label:None for label in labels if label!="now"}
    chosen={"now":start}
    ticks=0
    while q<=limit and len(chosen)<len(labels):
        ticks+=1
        outstanding=[label for label in schedules if label not in chosen]
        if "champion" in outstanding:
            p=planner.plan(q)
            if p and q<=p[0]<=limit:
                schedules["champion"]=(int(p[0]),float(p[1]))
        curve=curve_for(q) if any(label!="champion"
                                  for label in outstanding) else None
        for label in outstanding:
            if label=="champion":continue
            if label=="floor_0.55":
                p=earliest_from_curve(q,curve,floor=.55)
            else:
                delta=float(label.removeprefix("nearpeak_"))
                p=earliest_risk_budget(
                    q,curve,loss_budget=delta,
                    previous_departure=(
                        schedules[label][0] if schedules[label] else None))
            if p and q<=p[0]<=limit:
                schedules[label]=p
            elif label!="floor_0.55":
                # Never execute a stale near-peak flight if the current
                # model has withdrawn its availability support.
                schedules[label]=None
        for label in outstanding:
            s=schedules[label]
            if s is not None and s[0]<=q+STEP:
                chosen[label]=max(q,int(s[0]))
        q+=STEP
    return {label:chosen.get(label) for label in labels},ticks


def evaluate(starts,*,tl,planner,travel,
             curve_generator=score_curve):
    labels=("champion","nearpeak_0.03","nearpeak_0.08",
            "nearpeak_0.15","floor_0.55","now")
    cache={}
    def curve_for(q):
        if q not in cache:
            cache[q]=curve_generator(planner,q)
        return cache[q]
    episodes=[]
    for start in starts:
        chosen,ticks=simulate_one(start,planner,curve_for,labels)
        state,qty,_=tl.vals(np.array([float(start)]))
        if np.isnan(qty[0]):
            inventory="UNKNOWN"
        elif qty[0]<30:
            inventory="BELOW_30"
        else:
            inventory="AT_LEAST_30"
        outcome={
            label:(None if dep is None else bool(
                tl.success(dep+travel,GRACE)))
            for label,dep in chosen.items()}
        episodes.append({
            "start":int(start),"stock":inventory,
            "departure":chosen,"hit":outcome,"ticks":ticks
        })
    native=dynamic_replay(
        tl,planner.plan,[float(s) for s in starts],travel,
        refresh=STEP,max_wait=MAX_WAIT)
    truth={int(s):(None if d is None else int(d),
                    None if d is None else bool(ok))
           for s,d,a,ok in native["details"]}
    for ep in episodes:
        dep,ok=truth[ep["start"]]
        if (ep["departure"]["champion"]!=dep
            or ep["hit"]["champion"]!=ok):
            raise AssertionError("ORIGINAL_CHAMPION_PARITY_MISMATCH")

    def metrics(group):
        n=len(group)
        report={}
        for label in labels:
            valid=[r for r in group if r["departure"][label] is not None]
            good=sum(int(r["hit"][label]) for r in valid)
            waits=[(r["departure"][label]-r["start"])/60 for r in valid]
            matched=Counter()
            if label!="champion":
                for r in group:
                    a=r["hit"]["champion"];b=r["hit"][label]
                    if a is None or b is None:matched["unpaired"]+=1
                    elif a and b:matched["both_hit"]+=1
                    elif a:matched["champion_only"]+=1
                    elif b:matched["candidate_only"]+=1
                    else:matched["both_miss"]+=1
            report[label]={
                "starts":n,"departures":len(valid),
                "hits":good,"misses":len(valid)-good,
                "hit_fraction_per_start":round(good/n,4) if n else None,
                "hit_fraction_per_departure":round(good/len(valid),4)
                                             if valid else None,
                "mean_wait_minutes":round(statistics.mean(waits),2)
                                    if waits else None,
                "median_wait_minutes":round(statistics.median(waits),2)
                                      if waits else None,
                "paired_vs_champion":dict(matched)
            }
        return report
    return {
        "episodes":len(episodes),
        "champion_dynamic_parity":True,
        "distinct_score_curve_queries":len(cache),
        "stats":metrics(episodes),
        "initial_below_30":metrics([r for r in episodes
                                  if r["stock"]=="BELOW_30"]),
        "initial_at_least_30":metrics([r for r in episodes
                                     if r["stock"]=="AT_LEAST_30"]),
        "example_episodes":episodes[:2],
    }


def inspect(ctx,target,episodes):
    country,item=PILOTS[target]
    starts=valid_starts(ctx,country,item)
    hold=starts[int(len(starts)*.75):]
    sample=select_starts(starts,episodes)
    if not sample:
        return {"item":f"{country}:{item}","status":"NO_VALID_STARTS"}
    planner=model_for(ctx,target,hold[0])
    t0=time.monotonic()
    result=evaluate([int(s) for s in sample],
                    tl=ctx.timelines[(country,item)],planner=planner,
                    travel=TRAVEL_SECONDS[country])
    result["item"]=f"{country}:{item}"
    result["seconds"]=round(time.monotonic()-t0,2)
    return result


def pretty(r):
    print("===== V106 ACTUAL CHAMPION VS RISK-BUDGET EARLIEST DEPARTURES =====")
    print("Raw forecast scores uncalibrated. Holdout previously inspected.")
    for key,d in r["items"].items():
        print("====",key,d["item"],"====")
        print("starts",d["episodes"],"score_queries",
              d["distinct_score_curve_queries"],"elapsed",d["seconds"])
        print(f'{"POLICY":18} {"HITS":>5} {"MISSES":>6} {"WAIT AVG MIN":>13}')
        for label,s in d["stats"].items():
            print(f'{label:18} {s["hits"]:5} {s["misses"]:6} '
                  f'{str(s["mean_wait_minutes"]):>13}')
            if label!="champion":
                print("  paired:",json.dumps(s["paired_vs_champion"]))
        for state in ("initial_below_30","initial_at_least_30"):
            m=d[state]
            print(state,"sample_starts",
                  next(iter(m.values()))["starts"] if m else 0)
            for label,s in m.items():
                print(" ",label,"hits",s["hits"],"of",s["starts"],
                      "mean_wait",s["mean_wait_minutes"])
    print("===== RESEARCH ONLY: NOT CERTIFIED PLAYER SUCCESS =====")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--target",choices=["redfox","nessie","both"],default="both")
    p.add_argument("--episodes",type=int,default=10)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not 1<=args.episodes<=MAX_EPISODES:
        p.error("episode count outside bound")
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved historical stock source")
    keys=list(PILOTS) if args.target=="both" else [args.target]
    t0=time.monotonic()
    ctx=ResearchContext.build(SOURCE,targets=PLUSHIES,readonly=True)
    try:
        out={
            "status":"V106_RISK_BUDGET_EARLIEST_REPLAY",
            "source_read_only":True,"replanning_seconds":300,
            "actual_flights_observed":False,
            "country_provider_freshness_verified":False,
            "independent_restock_events":False,
            "holdout_unseen":False,
            "restock_boundary_estimation":False,
            "champions_unchanged":True,
            "research_loss_budgets":list(DELTA_BUDGETS),
            "absolute_minimum_raw_score":ABSOLUTE_FLOOR,
            "contiguous_score_points":CONTIGUOUS_POINTS,
            "items":{key:inspect(ctx,key,args.episodes) for key in keys}
        }
    finally:
        ctx.con.close()
    out["total_elapsed_seconds"]=round(time.monotonic()-t0,2)
    if args.json:
        print(json.dumps(out,sort_keys=True))
    else:
        pretty(out)
        print("TOTAL SECONDS:",out["total_elapsed_seconds"])


if __name__=="__main__":
    main()
