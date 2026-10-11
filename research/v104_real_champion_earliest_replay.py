"""V104 historical no-lookahead static side-by-side of champion vs EARLIEST.

Runs the ACTUAL Red Fox (analog) and Nessie (template) champion model on
the SAME past as-of queries. The unchanged incumbent selects its usual plan;
new variants pick the first qualifying arrival on the same raw score curve.
Observed stock is checked strictly AFTER choosing both departures.

This is an as-issued SINGLE-PREDICTION counterfactual: later automatic 5m
replanning and real player behavior are NOT simulated or certified. Original
champion evaluations did replan; do not compare V104 percentages directly to
the previously reported champion dynamic holdout percentages.

The Oct historical holdout was inspected during earlier model research, so
this is a diagnostic, NOT a pristine out-of-sample result. Event samples can
overlap the same stock windows; no country provider freshness certified.

Expensive context build and replay occur ONLY when explicitly invoked on the
user's VM, NOT in GitHub CI. Read-only SQLite, no collector writes.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from pathlib import Path

import numpy as np

from research.plushie_champions.common import (
    AnalogPlanner,TemplatePlanner,ResearchContext,PLUSHIES,valid_starts,
    TRAVEL_SECONDS,GRACE,MAX_WAIT
)
from research.plushie_champions.rf_localgrid import WINNING_CONFIG as FOX_CONFIG
from research.plushie_champions.recent_phase_select import WINNING_CONFIG as NESS_CONFIG
from research.v60_private_snapshot_probe import approved_collector_source
from research.v103_champion_score_curves import (
    score_curve,earliest_from_curve,analog_champion_from_curve,
    template_champion_from_curve
)

SOURCE="/opt/torn-fren/data/stock_history.db"
PILOTS={
    "redfox":("uni","Red Fox Plushie"),
    "nessie":("uni","Nessie Plushie"),
}
DEFAULT_FLOORS=(0.40,0.55,0.70)
MAX_EPISODES=30


def select_starts(starts,episodes):
    """Equally spaced chronological diagnostic samples from historic holdout."""
    hold=starts[int(.75*len(starts)):]
    if not hold:
        return []
    indices=np.linspace(0,len(hold)-1,min(len(hold),episodes),dtype=int)
    return [hold[int(k)] for k in sorted(set(indices))]


def model_for(ctx,target,train_cut):
    country,item=PILOTS[target]
    if target=="redfox":
        return AnalogPlanner(
            ctx,country,item,
            FOX_CONFIG["k"],FOX_CONFIG["global_regime_weight"],
            cutoff=train_cut)
    return TemplatePlanner(
        ctx,country,item,
        lags=NESS_CONFIG["lags"],
        lookback=NESS_CONFIG["lookback_h"]*3600,
        shift_range=NESS_CONFIG["shift_h"]*3600,
        minfit=NESS_CONFIG["minfit"])


def _score_windows(curve,q,travel,threshold):
    """Score-supported intervals, NOT predicted restock/depletion timestamps."""
    if curve is None:
        return []
    delays=curve["delay_seconds"]
    scores=curve["availability_score"]
    passing=[i for i,v in enumerate(scores) if v>=threshold]
    groups=[]
    for i in passing:
        if not groups or i!=groups[-1][-1]+1 or delays[i]-delays[groups[-1][-1]]!=300:
            groups.append([i])
        else:
            groups[-1].append(i)
    return [{
        "score_supported_arrival_start":int(q+travel+delays[g[0]]),
        "score_supported_arrival_end_exclusive":int(q+travel+delays[g[-1]]+300),
        "min_raw_score":float(min(scores[g])),
        "max_raw_score":float(max(scores[g])),
        "grid_points":len(g),
    } for g in groups]


def inspect_item(ctx,target,episodes,thresholds=DEFAULT_FLOORS,consecutive=1):
    country,item=PILOTS[target]
    travel=TRAVEL_SECONDS[country]
    tl=ctx.timelines[(country,item)]
    starts=valid_starts(ctx,country,item)
    hold=starts[int(.75*len(starts)):]
    qs=select_starts(starts,episodes)
    if not hold or not qs:
        return {"item_key":f"{country}:{item}","status":"INSUFFICIENT_HOLDOUT"}

    planner=model_for(ctx,target,hold[0])
    chosen=Counter()
    waits={label:[] for label in ["champion"]+[
        f"earliest_floor_{f:.2f}" for f in thresholds]}
    paired={f"earliest_floor_{f:.2f}":Counter() for f in thresholds}
    details=[]

    for qf in qs:
        q=int(qf)
        native=planner.plan(q)
        curve=score_curve(planner,q)
        if isinstance(planner,AnalogPlanner):
            parity=analog_champion_from_curve(q,curve)
        else:
            parity=template_champion_from_curve(q,curve)
        if (native is None)!=(parity is None):
            raise AssertionError("native score curve produced different availability")
        if native is not None:
            if int(native[0])!=int(parity[0]) or abs(native[1]-parity[1])>1e-9:
                raise AssertionError("model-native champion parity violated")
        plans={"champion":None if native is None else native[:2]}
        for f in thresholds:
            plans[f"earliest_floor_{f:.2f}"]=earliest_from_curve(
                q,curve,floor=f,min_consecutive_points=consecutive)

        row={"asof_epoch":q,"item_key":f"{country}:{item}",
             "native_model":"analog" if target=="redfox" else "template",
             "champion_departure":None if native is None else int(native[0]),
             "model_score_windows_floor_0_55":_score_windows(
                 curve,q,travel,.55)[:3],
             "options":{}}
        checked={}
        for label,candidate in plans.items():
            if candidate is None:
                row["options"][label]=None
                continue
            dep=int(candidate[0])
            if dep<q or dep>q+MAX_WAIT:
                raise AssertionError("candidate departure out of model horizon")
            ok=bool(tl.success(dep+travel,GRACE))
            wait=dep-q
            chosen[label]+=1
            chosen[label+"_hits"]+=int(ok)
            waits[label].append(wait)
            checked[label]=ok
            row["options"][label]={
                "departure_epoch":dep,
                "arrival_epoch":dep+travel,
                "delay_minutes":round(wait/60,1),
                "raw_model_score":round(float(candidate[1]),4),
                "historical_stock_proxy_hit":ok,
            }
        if "champion" in checked:
            for label,comp in paired.items():
                if label not in checked:
                    comp["unavailable"]+=1
                    continue
                champ=checked["champion"]
                alt=checked[label]
                if champ and alt:
                    comp["both_hit"]+=1
                elif champ:
                    comp["champion_only"]+=1
                elif alt:
                    comp["earliest_only"]+=1
                else:
                    comp["both_miss"]+=1
        details.append(row)

    def summarize_wait(values):
        if not values:
            return None
        mins=sorted(x/60 for x in values)
        return {
            "median_minutes":round(statistics.median(mins),1),
            "mean_minutes":round(statistics.mean(mins),1),
            "p75_minutes":round(mins[min(len(mins)-1,int(.75*(len(mins)-1)))],1),
        }

    stats={}
    for label,values in waits.items():
        departures=chosen[label]
        hits=chosen[label+"_hits"]
        stats[label]={
            "sample_queries":len(qs),
            "departures":departures,"proxy_successes":hits,
            "proxy_misses":departures-hits,
            "coverage_fraction":round(departures/len(qs),4),
            "success_fraction_when_recommended":round(hits/departures,4)
                                               if departures else None,
            "successful_flights_per_query":round(hits/len(qs),4),
            "waiting_time":summarize_wait(values),
            "matched_against_incumbent":dict(paired[label])
                                         if label in paired else None
        }
    return {
        "item_key":f"{country}:{item}",
        "model_type":"analog" if target=="redfox" else "template",
        "asof_holdout_query_count":len(qs),
        "available_holdout_query_count":len(hold),
        "stock_minimum":30,"arrival_grace_seconds":GRACE,
        "replanning_during_trip_simulated":False,
        "score_calibrated":False,
        "statistics":stats,
        "examples":details[:5],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=["redfox","nessie","both"],default="both")
    p.add_argument("--episodes",type=int,default=6)
    p.add_argument("--consecutive",type=int,choices=[1,2,3],default=1)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not 1<=args.episodes<=MAX_EPISODES:
        p.error(f"episodes must be 1 to {MAX_EPISODES}")
    if not approved_collector_source(SOURCE):
        raise SystemExit("STOP: unapproved stock source")
    start=time.monotonic()
    targets=["redfox","nessie"] if args.target=="both" else [args.target]
    ctx=ResearchContext.build(
        SOURCE,targets=PLUSHIES,readonly=True)
    try:
        out={
            "status":"V104_OFFLINE_CHAMPION_CURVE_DEPARTURE_COMPARISON",
            "research_only":True,"read_only":True,
            "production_services_changed":False,
            "training_future_rows_used_to_choose_departure":False,
            "actual_player_flights_observed":False,
            "stock_country_freshness_certified":False,
            "valid_out_of_sample_lockbox":False,
            "static_asof_only":True,
            "start_count_per_item_max":args.episodes,
            "research_score_thresholds":list(DEFAULT_FLOORS),
            "contiguous_score_points_required":args.consecutive,
            "items":{t:inspect_item(ctx,t,args.episodes,
                       thresholds=DEFAULT_FLOORS,
                       consecutive=args.consecutive) for t in targets}
        }
    finally:
        ctx.con.close()
    out["elapsed_seconds"]=round(time.monotonic()-start,2)
    if args.json:
        print(json.dumps(out,sort_keys=True))
        return
    print("===== V104 MODEL-NATIVE SCORE CURVE / DEPARTURE RESEARCH =====")
    print("No model training or live service was changed; no future stock used to choose a departure.")
    print("This is a static historical diagnostic, not an independent accuracy validation.")
    for target,data in out["items"].items():
        print(f'===== {target}: {data["item_key"]} =====')
        if "statistics" not in data:
            print(data["status"])
            continue
        print(f'Historic queries evaluated: {data["asof_holdout_query_count"]}')
        print(f'{"MODE":24} {"COVERED":>8} {"HITS":>6} {"MISSES":>7} {"PROXY HIT":>10} {"WAIT AVG":>9} {"WAIT P75":>9}')
        for name,stats in data["statistics"].items():
            wait=stats["waiting_time"] or {}
            frac=stats["success_fraction_when_recommended"]
            print(f'{name:24} {stats["departures"]:8} '
                  f'{stats["proxy_successes"]:6} {stats["proxy_misses"]:7} '
                  f'{str(frac):>10} {str(wait.get("mean_minutes")):>9} '
                  f'{str(wait.get("p75_minutes")):>9}')
            pair=stats["matched_against_incumbent"]
            if pair:
                print("    paired comparison:",json.dumps(pair,sort_keys=True))
        print("One scored opportunity example:",
              json.dumps(data["examples"][:1],sort_keys=True))
    print(f'Elapsed: {out["elapsed_seconds"]}s. Source opened read-only.')
    print("CAUTION: historic overlapping windows / no upstream country freshness / previously researched holdout.")


if __name__=="__main__":
    main()
