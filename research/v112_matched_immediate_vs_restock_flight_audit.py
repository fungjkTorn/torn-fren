"""V112 matched causal third-restock flight vs depart-now evidence audit.

At the SAME distinct below-30 observed depletion events used in V111,
compare the unchanged V107 estimated first reachable flight departure and
immediately departing at issue time. Score both landings with the SAME
raw-collector evidence function, not the stricter V110 k-th restock matching
which right-censored most third-cycle arrivals.

Report:
 * paired observation-bracket proxy classifications (hit/miss/uncertain)
 * weak last-known proxy separately
 * conservative best/worst-case difference from UNKNOWN outcomes
 * model wait minutes, saved departures, model-target k
Do not treat two-sided unchanged provider states as certified continuous
game availability, or confidence bounds as statistical confidence intervals.

Causal candidate: only raw stock rows whose epoch <= issue. Future rows
are exclusively used by arrival_evidence to evaluate the hypothetical
counterfactual. Both choices depart >= issue and within 8h. No live writes.
Historical holdout is previously inspected, provider freshness unavailable.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import statistics
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS,MAX_WAIT
from research.v107_explicit_restock_cycle_baseline import next_windows
from research.v109_raw_restock_transition_event_audit import (
    SOURCE,TARGETS,read_collector_item,transition_episodes
)
from research.v110_multicycle_restock_horizon_audit import choose_anchor_events
from research.v111_arrival_proxy_evidence_audit import arrival_evidence
from research.v60_private_snapshot_probe import approved_collector_source

MAX_ISSUES=100


def state(value):
    if value is True:return "HIT"
    if value is False:return "MISS"
    return "UNKNOWN"


def paired_summary(episodes):
    """Proxy accounting with identical starting opportunities for both.

    Deterministic outcome-identification bounds only, NOT confidence intervals:
      delta_lower = (certain model hits - maximal now hits) / n
      delta_upper = (maximal model hits - certain now hits) / n
    Unknown stock can be either success or failure, so no point claim allowed.
    """
    n=len(episodes)
    result={
        "anchors":n,
        "forecasted_departures":sum(r["departure"] is not None for r in episodes),
        "model":Counter(),"depart_now":Counter(),
        "weak_model":Counter(),"weak_depart_now":Counter(),
        "joint":Counter(),"weak_joint":Counter(),
        "waits":[(r["departure"]-r["issue"])/60 for r in episodes
                 if r["departure"] is not None],
    }
    for rec in episodes:
        for label,key in (("model","model_evidence"),("depart_now","now_evidence")):
            ev=rec[key]
            s=state(None if ev is None else ev["strict_bracket_proxy"])
            w=state(None if ev is None else ev["last_known_proxy"])
            result[label][s]+=1
            result["weak_"+label][w]+=1
        result["joint"][(
            state(rec["model_evidence"]["strict_bracket_proxy"]
                  if rec["model_evidence"] else None),
            state(rec["now_evidence"]["strict_bracket_proxy"]
                  if rec["now_evidence"] else None))]+=1
        result["weak_joint"][(
            state(rec["model_evidence"]["last_known_proxy"]
                  if rec["model_evidence"] else None),
            state(rec["now_evidence"]["last_known_proxy"]
                  if rec["now_evidence"] else None))]+=1

    model=result["model"];now=result["depart_now"]
    delta_low=(model["HIT"]-(now["HIT"]+now["UNKNOWN"]))/n if n else None
    delta_high=((model["HIT"]+model["UNKNOWN"])-now["HIT"])/n if n else None
    certain_better=result["joint"][("HIT","MISS")]
    certain_worse=result["joint"][("MISS","HIT")]
    both_known=sum(count for (a,b),count in result["joint"].items()
                   if a!="UNKNOWN" and b!="UNKNOWN")
    def summarize(label):
        c=result[label]
        return {
            "evidence_hits":c["HIT"],
            "evidence_misses":c["MISS"],
            "uncertain":c["UNKNOWN"],
            "scorable":c["HIT"]+c["MISS"],
            "evidence_fraction_of_all_anchors":round(c["HIT"]/n,4) if n else None,
        }
    waits=result["waits"]
    return {
        "anchors":n,
        "forecasted_departures":result["forecasted_departures"],
        "forecasted_departure_coverage":round(
            result["forecasted_departures"]/n,4) if n else None,
        "model":summarize("model"),
        "depart_now":summarize("depart_now"),
        "weak_last_known_model":dict(result["weak_model"]),
        "weak_last_known_now":dict(result["weak_depart_now"]),
        "paired_known_comparisons":both_known,
        "certain_model_better_now_worse":certain_better,
        "certain_model_worse_now_better":certain_worse,
        "joint_strict_evidence":{
            f"{a}_vs_{b}":value
            for (a,b),value in sorted(result["joint"].items())
        },
        "joint_weak_evidence":{
            f"{a}_vs_{b}":value
            for (a,b),value in sorted(result["weak_joint"].items())
        },
        "possible_delta_success_per_anchor_bounds":{
            "lower":round(delta_low,4) if delta_low is not None else None,
            "upper":round(delta_high,4) if delta_high is not None else None,
            "meaning":"deterministic unknown-outcome sensitivity bounds; NOT statistical CI"
        },
        "model_wait_minutes":{
            "mean":round(statistics.mean(waits),2) if waits else None,
            "median":round(statistics.median(waits),2) if waits else None,
        },
    }


def audit_item(observations,gaps,*,item_key,max_events=25,
               predictor=next_windows,scorer=arrival_evidence):
    episodes,rejected=transition_episodes(observations,gaps)
    anchors=choose_anchor_events(
        observations,episodes,max_events=max_events)
    times=[r.epoch for r in observations]
    flight=TRAVEL_SECONDS[item_key.split(":",1)[0]]
    results=[]
    evidence_reasons=Counter()
    hops=Counter()
    examples=[]
    for idx in anchors:
        issue=int(episodes[idx]["issue"])
        if episodes[idx]["phase"]!="DEPLETED":
            raise AssertionError("invalid reference event cohort")
        past=observations[:bisect.bisect_right(times,issue)]
        if not past or past[-1].epoch>issue:
            raise AssertionError("future stock in forecast input")
        prediction=predictor(
            item_key,past,asof=issue,collection_gaps=gaps)
        windows=prediction.get("windows",[])
        choices=[
            (int(w["earliest_expected_departure"]),k+1)
            for k,w in enumerate(windows)
            if w["earliest_expected_departure"] is not None
            and issue<=int(w["earliest_expected_departure"])<=issue+MAX_WAIT
        ]
        picked=min(choices) if choices else None
        departure=None if picked is None else picked[0]
        if picked:
            hops[picked[1]]+=1
        now_arrival=issue+flight
        model_arrival=None if departure is None else departure+flight
        before=scorer(observations,times,gaps,now_arrival)
        after=None if model_arrival is None else scorer(
            observations,times,gaps,model_arrival)
        evidence_reasons["depart_now:"+before["reason"]]+=1
        if after is not None:
            evidence_reasons["model:"+after["reason"]]+=1
        results.append({
            "issue":issue,"departure":departure,
            "now_evidence":before,"model_evidence":after,
        })
        if len(examples)<5:
            examples.append({
                "issue_epoch":issue,
                "issue_quantity":past[-1].quantity,
                "selected_target_cycle":None if picked is None else picked[1],
                "model_departure":departure,
                "model_arrival":model_arrival,
                "now_arrival":now_arrival,
                "now_stock_evidence":before["reason"],
                "now_proxy":state(before["strict_bracket_proxy"]),
                "model_stock_evidence":after["reason"] if after else None,
                "model_proxy":state(after["strict_bracket_proxy"]
                                    if after else None),
            })
    summary=paired_summary(results)
    summary.update({
        "item_key":item_key,
        "raw_stock_rows":len(observations),
        "continuous_completed_phases":len(episodes),
        "rejected_phases":dict(rejected),
        "hop_distribution":{str(k):v for k,v in sorted(hops.items())},
        "arrival_evidence_reasons":dict(evidence_reasons),
        "examples":examples,
        "only_observed_stock_evidence_not_game_world_truth":True,
        "country_provider_asof_verified":False,
        "no_future_rows_used_to_choose_departure":True,
    })
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=["redfox","nessie","both"],default="both")
    p.add_argument("--events",type=int,default=25)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not 1<=a.events<=MAX_ISSUES:
        p.error("events must be 1..100")
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved collector data source")
    targets=TARGETS if a.target=="both" else {
        a.target:TARGETS[a.target]}
    beginning=time.monotonic()
    with closing(sqlite3.connect(
        Path(SOURCE).resolve(strict=True).as_uri()+"?mode=ro",
        uri=True,timeout=15)) as db:
        db.execute("PRAGMA query_only=ON")
        items={}
        for name,(country,item) in targets.items():
            obs,gaps=read_collector_item(db,country,item)
            items[name]=audit_item(
                obs,gaps,item_key=f"{country}:{item}",
                max_events=a.events)
    out={
        "status":"V112_MATCHED_DEPART_NOW_VS_MULTI_CYCLE_FLIGHT_EVIDENCE",
        "read_only":True,"same_depletion_event_cohort_as_v111":True,
        "historical_holdout_previously_inspected":True,
        "genuine_player_flights_verified":False,
        "country_provider_freshness_verified":False,
        "duration_seconds":round(time.monotonic()-begin,2),
        "items":items,
    }
    if a.json:
        print(json.dumps(out,sort_keys=True))
    else:
        print("===== V112 MATCHED DEPART NOW VS MULTI-RESTOCK FLIGHT =====")
        for key,d in items.items():
            print("==",key,d["item_key"],"==")
            print("depleted anchors",d["anchors"],
                  "model departed",d["forecasted_departures"],
                  "target restock distribution",d["hop_distribution"])
            print("same-source two-sided 15m model:",
                  json.dumps(d["model"],sort_keys=True))
            print("same-source two-sided 15m now:",
                  json.dumps(d["depart_now"],sort_keys=True))
            print("paired strict evidence:",
                  json.dumps(d["joint_strict_evidence"],sort_keys=True))
            print("certain model-only positive:",d["certain_model_better_now_worse"],
                  "certain now-only positive:",d["certain_model_worse_now_better"])
            print("possible delta bounds:",
                  json.dumps(d["possible_delta_success_per_anchor_bounds"],sort_keys=True))
            print("model waiting:",d["model_wait_minutes"])
            print("weak last known model:",
                  json.dumps(d["weak_last_known_model"],sort_keys=True))
            print("weak last known now:",
                  json.dumps(d["weak_last_known_now"],sort_keys=True))
            print("arrival reasons:",json.dumps(d["arrival_evidence_reasons"],sort_keys=True))
            print("examples:",json.dumps(d["examples"][:2],sort_keys=True))
        print("RESEARCH: paired historical stock proxies, NOT game-verified flights.")
        print("elapsed seconds:",out["duration_seconds"])


if __name__=="__main__":
    main()
