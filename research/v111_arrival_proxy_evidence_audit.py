"""V111: score forecasted FLIGHT ARRIVAL, not only intended restock index.

Research-only diagnostic for V110's severe 3rd-restock right-censoring.
The model still issues EXACTLY the same V107 1-4 cycle forecast at each
distinct observed depletion event. No model training/selection changes.

An arrival during the 2nd actual stocked window can succeed even if the
forecast aimed for the 3rd. Score observed quantity in two SEPARATE ways:
  * strict: same-provider stock rows on both sides within 15m, agreeing on
    >=30 state, no known collector gaps. A narrowly bracketed PROXY, not
    certified real in-game availability.
  * last-known: stock row before arrival within 15m, no known gap. This is
    WEAKER, change-only forward-filled stock; NEVER present as actual truth.
Provider switches and state changes straddling arrival are counted separately,
not silently called a success or failure.

Do not use future rows to construct predictions, only to score historical
counterfactual landings. No live system modifications or API calls.
Past holdout has been inspected; event samples are not verified independent
game restocks. Country provider as-of epochs are unknown.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v107_explicit_restock_cycle_baseline import next_windows
from research.v109_raw_restock_transition_event_audit import (
    SOURCE,TARGETS,read_collector_item,transition_episodes
)
from research.v110_multicycle_restock_horizon_audit import (
    choose_anchor_events,chained_future_restock_windows
)
from research.v60_private_snapshot_probe import approved_collector_source

MAX_ISSUES=100
BRACKET_SECONDS=900
MIN_QTY=30


def known_gap(gaps,first,last):
    """Any collector-wide gap intersecting observation->arrival interval."""
    return any(a<=last and (b is None or b>=first) for a,b in gaps)


def arrival_evidence(observations, epochs, gaps, arrival, *,
                     max_age=BRACKET_SECONDS):
    """Classify future-observed stock proxy with explicit evidence strength."""
    if not isinstance(arrival,int):
        raise ValueError("arrival must be epoch second integer")
    pos=bisect.bisect_right(epochs,arrival)
    prev=observations[pos-1] if pos else None
    nextobs=observations[pos] if pos<len(observations) else None
    age=None if prev is None else arrival-prev.epoch
    lag=None if nextobs is None else nextobs.epoch-arrival
    out={
        "arrival_epoch":arrival,
        "last_stock_row_age_seconds":age,
        "next_stock_row_lag_seconds":lag,
        "last_known_proxy":None,
        "strict_bracket_proxy":None,
        "source_switch_across_bracket":False,
        "transition_straddles_arrival":False,
        "reason":None,
    }
    if prev is None or age>max_age:
        out["reason"]="NO_RECENT_BEFORE_ARRIVAL"
        return out
    if known_gap(gaps,prev.epoch,arrival):
        out["reason"]="COLLECTION_GAP_BEFORE_ARRIVAL"
        return out
    state=prev.quantity>=MIN_QTY
    out["last_known_proxy"]=state
    if age==0:
        out["strict_bracket_proxy"]=state
        out["reason"]="EXACT_STOCK_ROW_TIMESTAMP"
        return out
    if nextobs is None or lag>max_age:
        out["reason"]="NO_NEARBY_AFTER_ARRIVAL"
        return out
    if known_gap(gaps,arrival,nextobs.epoch):
        out["reason"]="COLLECTION_GAP_AFTER_ARRIVAL"
        return out
    if prev.source!=nextobs.source:
        out["source_switch_across_bracket"]=True
        out["reason"]="SOURCE_SWITCH_ACROSS_ARRIVAL"
        return out
    if (nextobs.quantity>=MIN_QTY)!=state:
        out["transition_straddles_arrival"]=True
        out["reason"]="STOCK_THRESHOLD_CROSSED_AROUND_ARRIVAL"
        return out
    out["strict_bracket_proxy"]=state
    out["reason"]="SAME_SOURCE_BRACKETED_STATE"
    return out


def audit_item(observations,gaps,*,item_key,max_events=25,
               forecast=next_windows):
    """Causal issue selection, same V110 earliest reachable cycle policy."""
    episodes,rejected=transition_episodes(observations,gaps)
    anchors=choose_anchor_events(observations,episodes,max_events=max_events)
    epochs=[row.epoch for row in observations]
    travel=TRAVEL_SECONDS[item_key.split(":",1)[0]]
    total=Counter()
    example=[]
    landing_states=Counter()
    matching_states=Counter()
    for idx in anchors:
        start=episodes[idx]["issue"]
        past=observations[:bisect.bisect_right(epochs,start)]
        if not past or past[-1].epoch>start:
            raise AssertionError("future evidence supplied to model")
        pred=forecast(item_key,past,asof=start,collection_gaps=gaps)
        projected=pred.get("windows",[])
        selection=[
            (k+1,w["earliest_expected_departure"])
            for k,w in enumerate(projected)
            if w["earliest_expected_departure"] is not None
        ]
        total["anchors"]+=1
        if not selection:
            total["no_reachable_prediction"]+=1
            continue
        hop,departure=min(selection,key=lambda v:(v[1],v[0]))
        arrival=int(departure+travel)
        total["departures_issued"]+=1
        total[f"target_hop_{hop}"]+=1
        evidence=arrival_evidence(
            observations,epochs,gaps,arrival)
        label=evidence["reason"]
        landing_states[label]+=1
        strict=evidence["strict_bracket_proxy"]
        prior=evidence["last_known_proxy"]
        if strict is not None:
            total["strict_scorable"]+=1
            total["strict_success"]+=int(strict)
            total["strict_fail"]+=int(not strict)
        if prior is not None:
            total["last_known_scorable"]+=1
            total["last_known_success"]+=int(prior)
            total["last_known_fail"]+=int(not prior)
        real_windows=chained_future_restock_windows(episodes,idx)
        if hop>len(real_windows):
            matching_states["target_hop_censored"]+=1
        else:
            window=real_windows[hop-1]
            if window["restock"]-10<=arrival<window["depletion"]:
                matching_states["target_hop_stocked"]+=1
            else:
                matching_states["target_hop_unstocked"]+=1
        if len(example)<7:
            example.append({
                "issue":start,"departure":departure,"arrival":arrival,
                "target_hop":hop,
                "forecasted_target_window":{
                    "start":projected[hop-1]["expected_stocked_start"],
                    "end":projected[hop-1]["expected_drop_below_30"],
                },
                "evidence":evidence,
                "completed_true_future_windows":len(real_windows),
            })
    return {
        "item_key":item_key,
        "source_raw_stock_rows":len(observations),
        "completed_provider_continuous_phases":len(episodes),
        "raw_phase_exclusions":dict(rejected),
        "selected_distinct_depletion_anchors":total["anchors"],
        "forecasted_departures":total["departures_issued"],
        "no_reachable_forecast":total["no_reachable_prediction"],
        "target_hop_histogram":{
            str(i):total[f"target_hop_{i}"] for i in range(1,5)
        },
        "strict_same_source_two_sided_15m_proxy":{
            "scorable":total["strict_scorable"],
            "hits":total["strict_success"],"misses":total["strict_fail"]
        },
        "weak_last_known_15m_proxy":{
            "scorable":total["last_known_scorable"],
            "hits":total["last_known_success"],"misses":total["last_known_fail"]
        },
        "stock_evidence_classifications":dict(landing_states),
        "matching_third_restock_evidence":dict(matching_states),
        "examples":example,
        "strict_player_success_verified":False,
        "country_provider_asof_verified":False,
        "flight_recommendations_read_only":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=["redfox","nessie","both"],
                   default="both")
    p.add_argument("--events",type=int,default=25)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not 1<=args.events<=MAX_ISSUES:
        p.error("number of distinct issue events must be 1..100")
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved production stock source")
    names=TARGETS if args.target=="both" else {
        args.target:TARGETS[args.target]}
    start=time.monotonic()
    with closing(sqlite3.connect(
        Path(SOURCE).resolve(strict=True).as_uri()+"?mode=ro",
        uri=True,timeout=15)) as con:
        con.execute("PRAGMA query_only=ON")
        items={}
        for name,(country,item) in names.items():
            obs,gaps=read_collector_item(con,country,item)
            items[name]=audit_item(
                obs,gaps,item_key=f"{country}:{item}",
                max_events=args.events)
    report={
        "status":"V111_FLIGHT_ARRIVAL_PROXY_SOURCE_SENSITIVITY_AUDIT",
        "asof_no_lookahead":True,"read_only":True,
        "same_restocks_as_v110":True,
        "real_flight_success_verified":False,
        "total_elapsed_seconds":round(time.monotonic()-start,2),
        "items":items,
    }
    if args.json:
        print(json.dumps(report,sort_keys=True))
        return
    print("===== V111: LANDING DURING ANY STOCKED CYCLE, NOT ONLY THE 3RD =====")
    for name,info in items.items():
        print("====",name,info["item_key"],"====")
        print("anchors",info["selected_distinct_depletion_anchors"],
              "departs",info["forecasted_departures"],
              "target_hops",info["target_hop_histogram"])
        print("strict_two_sided_15m:",json.dumps(
            info["strict_same_source_two_sided_15m_proxy"],sort_keys=True))
        print("weak_last_known_15m:",json.dumps(
            info["weak_last_known_15m_proxy"],sort_keys=True))
        print("arrival evidence statuses:",json.dumps(
            info["stock_evidence_classifications"],sort_keys=True))
        print("target-hop truth:",json.dumps(
            info["matching_third_restock_evidence"],sort_keys=True))
        print("examples:",json.dumps(info["examples"][:2],sort_keys=True))
    print("Raw/change-only source, provider-age not certified, both views are PROXIES.")
    print("elapsed:",report["total_elapsed_seconds"],"seconds")


if __name__=="__main__":
    main()
