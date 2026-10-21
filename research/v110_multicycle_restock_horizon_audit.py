"""V110: causal MULTI-CYCLE restock forecast and earliest viable UK landing audit.

V109 only scored the NEXT restock after observed depletion, even when that
next stocked interval ends before the UK flight can land. V110 scores the
first, second, third, and fourth distinct observed restock transitions from
the SAME as-of depleted-state forecast. No repeated 5-minute issue targets.

Each future restock and following depletion must be observed without a
provider switch, gap, or short bounce; otherwise that hop is CENSORED, not
scored a miss. Predictions use only prior raw stock-change observations and
the source's uninterrupted completed phases as of issue time.

We also evaluate the as-issued earliest model-reachable departure, at
country flight time, against the *matching k-th observed stock window*.
This is hypothetical historical stock observation, NOT an actual flight or
verified country-fresh game stock.

Sampled previously researched holdout, not a pristine lockbox.
Raw timestamps are collector-observed, not exact in-game restock events.
No API calls or production file/database/service writes.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS,GRACE
from research.v107_explicit_restock_cycle_baseline import next_windows
from research.v109_raw_restock_transition_event_audit import (
    TARGETS,SOURCE,MIN_HISTORY_DAYS,HOLDOUT_FRACTION,
    read_collector_item,transition_episodes
)
from research.v60_private_snapshot_probe import approved_collector_source

MAX_RESTOCK_HOPS=4
MAX_ANCHORS=100


def chained_future_restock_windows(episodes, anchor_idx,
                                   max_hops=MAX_RESTOCK_HOPS):
    """Actual future k-th >=30 window with censoring at ANY discontinuity.

    Completed phases are one transition to the next and always alternate.
    Requiring the previous phase's end to match the next phase's issue epoch
    prevents silently skipping provider-switch, short-bounce or gap events.
    """
    anchor=episodes[anchor_idx]
    if anchor["phase"]!="DEPLETED":
        raise ValueError("anchor is not observed depletion")
    seg=anchor["segment"]
    out=[]
    previous=None
    for j in range(anchor_idx,len(episodes)):
        ep=episodes[j]
        if ep["segment"]!=seg or (
            previous is not None and
            previous["actual_next_transition"]!=ep["issue"]
        ):
            break
        if (previous is not None and
            previous["phase"]==ep["phase"]):
            break
        if ep["phase"]=="DEPLETED":
            if j+1>=len(episodes):
                break
            following=episodes[j+1]
            if (following["segment"]!=seg
                or following["phase"]!="STOCKED"
                or following["issue"]!=ep["actual_next_transition"]):
                break
            out.append({
                "restock":ep["actual_next_transition"],
                "depletion":following["actual_next_transition"],
            })
            if len(out)>=max_hops:
                break
        previous=ep
    return out


def choose_anchor_events(observations,episodes,max_events=25):
    """Chronological 25%-tail event cohort, choose DEPLETED phase starts."""
    if not observations or not 1<=max_events<=MAX_ANCHORS:
        return []
    first=observations[0].epoch
    cutoff=first+int(
        (observations[-1].epoch-first)*(1-HOLDOUT_FRACTION))
    eligible=[j for j,e in enumerate(episodes)
              if e["phase"]=="DEPLETED" and e["issue"]>=cutoff
              and e["issue"]>=first+MIN_HISTORY_DAYS*86400]
    if len(eligible)>max_events:
        # Equally spread among distinct replenishment cycles. A single
        # depleted episode may be selected only once.
        chosen=[
            int((i*(len(eligible)-1))/(max_events-1))
            for i in range(max_events)] if max_events>1 else [len(eligible)//2]
        eligible=[eligible[j] for j in sorted(set(chosen))]
    return eligible


def summarize(values):
    if not values:return None
    x=sorted(values)
    return {
        "median_abs_minutes":round(statistics.median(x),2),
        "p75_abs_minutes":round(x[min(len(x)-1,math.ceil(.75*len(x))-1)],2)
    }


def evaluate_multihop(obs,episodes,gaps,*,item_key,max_events=25,
                      forecast=next_windows):
    indexes=choose_anchor_events(obs,episodes,max_events=max_events)
    country=item_key.split(":",1)[0]
    travel=TRAVEL_SECONDS[country]
    bucket=defaultdict(Counter)
    errors=defaultdict(list)
    expected_window_counts=Counter()
    total=Counter()
    examples=[]
    for i in indexes:
        issue=episodes[i]["issue"]
        # Prediction input is strictly past and present raw observations.
        past=[r for r in obs if r.epoch<=issue]
        if not past or max(r.epoch for r in past)>issue:
            raise AssertionError("future evidence in predictor")
        pred=forecast(item_key,past,asof=issue,collection_gaps=gaps)
        actual=chained_future_restock_windows(episodes,i)
        projected=pred.get("windows",[])
        total["anchors"]+=1
        if not projected:
            total["model_no_windows"]+=1
        if len(actual)<4:
            total["right_censored_before_4_completed_windows"]+=1

        for k in range(1,MAX_RESTOCK_HOPS+1):
            stat=bucket[k]
            stat["anchors"]+=1
            if k>len(actual):
                stat["truth_censored"]+=1
                continue
            stat["truth_observed"]+=1
            if k>len(projected):
                stat["prediction_missing"]+=1
                continue
            stat["scorable"]+=1
            expected=projected[k-1]["expected_stocked_start"]
            onset=actual[k-1]["restock"]
            delta=expected-onset
            a=abs(delta)
            errors[k].append(a/60)
            stat["absolute_error_seconds_sum"]+=a
            if a<=300:stat["within_5m"]+=1
            if a<=900:stat["within_15m"]+=1
            if a<=1800:stat["within_30m"]+=1
            if delta<0:stat["early"]+=1
            elif delta>0:stat["late"]+=1

        # Flight evaluation only on first predicted reachable window, and
        # matching actual k-th restock interval; never score a different
        # observed replenishment as success for the same forecast.
        selected=[
            (k+1,w["earliest_expected_departure"])
            for k,w in enumerate(projected)
            if w["earliest_expected_departure"] is not None
        ]
        if not selected:
            total["no_reachable_forecast_window"]+=1
        else:
            k,departure=min(selected,key=lambda x:(x[1],x[0]))
            expected_window_counts[k]+=1
            total["flight_proposal"]+=1
            if k>len(actual):
                total["flight_truth_censored"]+=1
            else:
                arrival=departure+travel
                start=actual[k-1]["restock"]
                end=actual[k-1]["depletion"]
                success=(start-GRACE<=arrival<end)
                total["flight_scorable"]+=1
                total["flight_proxy_hit"]+=int(success)
                total["flight_proxy_miss"]+=int(not success)
                if arrival<start-GRACE:
                    total["arrival_before_target_restock"]+=1
                elif arrival>=end:
                    total["arrival_after_target_depletion"]+=1

        if len(examples)<6:
            examples.append({
                "issue_epoch":issue,
                "observed_stock_at_issue":past[-1].quantity,
                "actual_future_observed_stock_windows":actual,
                "predicted_future_stocked_windows":[{
                    "start":w["expected_stocked_start"],
                    "end":w["expected_drop_below_30"],
                    "departure":w["earliest_expected_departure"]
                } for w in projected],
            })

    by_hop={}
    for k in range(1,MAX_RESTOCK_HOPS+1):
        c=bucket[k]
        n=c["scorable"]
        by_hop[str(k)]={
            "anchors":c["anchors"],
            "observed_truth_windows":c["truth_observed"],
            "right_censored_truth":c["truth_censored"],
            "missing_predictions":c["prediction_missing"],
            "scorable":n,
            "within_5m":c["within_5m"],
            "within_15m":c["within_15m"],
            "within_30m":c["within_30m"],
            "within_15m_fraction":round(c["within_15m"]/n,4) if n else None,
            "errors":summarize(errors[k]),
            "earlier_than_actual":c["early"],
            "later_than_actual":c["late"],
        }

    return {
        "item_key":item_key,
        "selected_distinct_depletion_events":len(indexes),
        "by_predicted_restock_hop":by_hop,
        "first_reachable_window_hop_counts":dict(sorted(expected_window_counts.items())),
        "flight_proposals":total["flight_proposal"],
        "flight_proxy_scorable":total["flight_scorable"],
        "flight_proxy_successes":total["flight_proxy_hit"],
        "flight_proxy_misses":total["flight_proxy_miss"],
        "flight_truth_censored":total["flight_truth_censored"],
        "no_reachable_forecast_window":total["no_reachable_forecast_window"],
        "arrival_before_target_restock":total[
            "arrival_before_target_restock"],
        "arrival_after_target_depletion":total[
            "arrival_after_target_depletion"],
        "example_forecasts":examples,
        "causal_asof_prediction":True,
        "actual_player_flights_verified":False,
        "country_source_freshness_verified":False,
    }


def pretty(report):
    print("===== V110 MULTI-RESTOCK HORIZON / 106-MIN UK FLIGHT FORECAST =====")
    for name,item in report["items"].items():
        print("====",name,item["item_key"],"====")
        print("raw rows:",item["raw_rows"],
              "continuous phases:",item["continuous_phases"],
              "distinct depletion issue events:",
              item["selected_distinct_depletion_events"])
        for k,m in item["by_predicted_restock_hop"].items():
            print(
                f'  restock #{k}: observed={m["observed_truth_windows"]} '
                f'scorable={m["scorable"]} within5={m["within_5m"]} '
                f'within15={m["within_15m"]} '
                f'median_error_min={m["errors"]["median_abs_minutes"] if m["errors"] else None} '
                f'p75_error_min={m["errors"]["p75_abs_minutes"] if m["errors"] else None} '
                f'truth_censored={m["right_censored_truth"]}')
        print("first reachable modeled window distribution:",
              json.dumps(item["first_reachable_window_hop_counts"],sort_keys=True))
        print("earliest matching-k future flight proposals:",
              item["flight_proposals"],
              "proxy successes:",item["flight_proxy_successes"],
              "misses:",item["flight_proxy_misses"],
              "censored:",item["flight_truth_censored"])
        print("reasons: too early",item["arrival_before_target_restock"],
              "after depletion",item["arrival_after_target_depletion"])
        print("example:",json.dumps(item["example_forecasts"][:1]))
    print("===== READ-ONLY; HISTORICAL OBSERVED EVENTS NOT VERIFIED LIVE STOCK =====")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",choices=["redfox","nessie","both"],
                        default="both")
    parser.add_argument("--events",type=int,default=25)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    if not 1<=args.events<=MAX_ANCHORS:
        parser.error("events must be 1..100")
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved collector source")
    targets=TARGETS if args.target=="both" else {
        args.target:TARGETS[args.target]}
    begin=time.monotonic()
    with closing(sqlite3.connect(
            Path(SOURCE).resolve(strict=True).as_uri()+"?mode=ro",
            uri=True,timeout=15)) as con:
        con.execute("PRAGMA query_only=ON")
        results={}
        for name,(country,item) in targets.items():
            obs,gaps=read_collector_item(con,country,item)
            episodes,exclusions=transition_episodes(obs,gaps)
            x=evaluate_multihop(
                obs,episodes,gaps,item_key=f"{country}:{item}",
                max_events=args.events)
            x["raw_rows"]=len(obs)
            x["continuous_phases"]=len(episodes)
            x["excluded_phases"]=dict(exclusions)
            results[name]=x
    report={
        "status":"V110_MULTIHOP_RESTOCK_EVENT_FLIGHT_GEOMETRY_AUDIT",
        "read_only":True,"live_changes":False,
        "holdout_independent":False,"estimated_window_not_exact_game_state":True,
        "issue_cohort":"distinct DEPLETED transition events",
        "elapsed_seconds":round(time.monotonic()-begin,2),
        "items":results,
    }
    if args.json:print(json.dumps(report,sort_keys=True))
    else:
        pretty(report)
        print("elapsed_seconds:",report["elapsed_seconds"])


if __name__=="__main__":
    main()
