"""V117: TRUE-as-issued five-minute REPLAN replay for V75 frozen forecasts.

V116 reveals 49/50 first-UTC-hour candidate departures occur >5m after
issuance, beyond their 5m validity. Scoring that original future departure
as if executable is NOT a fair live-policy comparison.

For EXACTLY V116's representative first eligible candidate per item per UTC
hour, simulate waiting with the recorded frozen V75 candidate feed:
* at the start, compare an IMMEDIATE flight arriving in 106m
* observe each later recorded item tick in chronological time order, never
  accessing stock outcomes during the choice
* take the FIRST future tick that includes a valid, departure-within-5m
  research recommendation. The actual simulated flight departs at its
  issued timestamp or up to 5 minutes later as proposed.
* stop observing at start+8h, the same project wait horizon
* if the complete window has not elapsed, call it pending research
* if no executable future tick occurs, call it NO_ACTION (not a missed
  trip and not a future-stock success).

Score both counterfactual flights with the same V88 global poll heartbeat
proxy, but only if their arrivals are mature; record censoring separately.
Correlating adjacent issue starts are not independently sampled restocks.

This is a causal FROZEN-candidate replay from a separate V75 sidecar, not
proof of live website behavior or in-game purchases. No API/VM/service/model
writes; both SQLite input databases read-only, max 50k candidate rows.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import MAX_WAIT,STEP,TRAVEL_SECONDS
from research.v76_forward_research_report import (
    V75, eligible, ro, MAX_CANDIDATE_ROWS,MAX_PROXY_EVENTS
)
from research.v88_poll_state_forward_report import (
    SOURCE,observation as poll_observation
)
from research.v116_attributed_hourly_forward_audit import (
    select_candidates,first_per_item_hour,delay_bucket
)
from research.v115_targeted_v88_forward_evidence import ITEMS
from research.v60_private_snapshot_probe import approved_collector_source

MIN_ISSUES=1
MAX_HOURS=24


def future_candidate_timelines(conn,*,start,end,keys):
    marks=",".join("?" for _ in keys)
    clause=(
        "FROM v42_candidate_decisions "
        "WHERE computed_at>=? AND computed_at<=? "
        f"AND item_key IN ({marks})")
    args=[start,end,*keys]
    n=int(conn.execute("SELECT count(*) "+clause,args).fetchone()[0])
    if n>MAX_CANDIDATE_ROWS:
        raise ValueError("targeted tick timeline too large: narrow --hours")
    rows=conn.execute(
        "SELECT item_key,computed_at,stock_as_of,status,valid_until,"
        "departure,arrival,actual_player_departure,model_family,"
        "model_config "+clause+" ORDER BY computed_at ASC,id ASC",args
    ).fetchall()
    by_item=defaultdict(list)
    for r in rows:
        by_item[r["item_key"]].append(r)
    times={k:[int(r["computed_at"]) for r in x]
           for k,x in by_item.items()}
    return by_item,times,n


def first_actionable_tick(initial,timeline,times,*,now):
    """One forward online policy: earliest available actionable candidate.

    All future records are processed in time order, not scored or selected
    based on future stock. Respect the family of the original first issue.
    """
    begin=int(initial["computed_at"])
    deadline=begin+MAX_WAIT
    end=min(deadline,int(now))
    at=bisect.bisect_left(times,begin)
    seen=0
    rejected=Counter()
    for row in timeline[at:]:
        issued=int(row["computed_at"])
        if issued>end:break
        seen+=1
        if row["model_family"]!=initial["model_family"]:
            rejected["OTHER_FAMILY"]+=1
            continue
        if not eligible(row):
            rejected["INVALID_OR_ABSTAINED"]+=1
            continue
        dep=int(row["departure"])
        # Non-executable watches expire on their original 5m snapshot;
        # call them watches, not a failed attempt to depart.
        if dep-issued>STEP:
            rejected["FUTURE_WATCH_NOT_YET_EXECUTABLE"]+=1
            continue
        if dep>int(row["valid_until"]):
            rejected["EXPIRED_BEFORE_DEPARTURE"]+=1
            continue
        if dep>deadline:
            rejected["DEPARTURE_AFTER_8H_WAIT_BUDGET"]+=1
            continue
        if dep<issued:
            raise AssertionError("pre-issuance departure")
        return {
            "status":"EXECUTABLE_WITHIN_5M",
            "departure":dep,
            "arrival":int(row["arrival"]),
            "ready_issue":issued,
            "ticks_inspected":seen,
            "rejected_tick_reasons":dict(rejected),
            "original_departure_shift_seconds":dep-int(initial["departure"]),
        }
    return {
        "status":("STILL_WAITING_HORIZON_NOT_MATURE"
                  if now<deadline else "NO_EXECUTABLE_DEPARTURE_WITHIN_8H"),
        "departure":None,"arrival":None,"ready_issue":None,
        "ticks_inspected":seen,"rejected_tick_reasons":dict(rejected),
        "original_departure_shift_seconds":None,
    }


def materialize(c):
    d=dict(sorted(c.items()))
    paired=d.get("paired_scorable",0)
    d["model_minus_now_pairwise_proxy_hits"]=(
        d.get("ready_only_hit",0)-d.get("immediate_only_hit",0))
    d["ready_hit_rate_on_both_scorable"]=(
        round((d.get("both_hit",0)+d.get("ready_only_hit",0))/paired,4)
        if paired else None)
    d["immediate_hit_rate_on_both_scorable"]=(
        round((d.get("both_hit",0)+d.get("immediate_only_hit",0))/paired,4)
        if paired else None)
    return d


def audit(*,ledger=V75,stock=SOURCE,now=None,hours=24,
          keys=tuple(ITEMS.values()),limit=MAX_PROXY_EVENTS,
          scorer=poll_observation):
    if (not MIN_ISSUES<=hours<=MAX_HOURS
        or not 1<=limit<=MAX_PROXY_EVENTS
        or len(set(keys))!=len(keys)
        or not 1<=len(keys)<=len(ITEMS)
        or not set(keys)<=set(ITEMS.values())):
        raise ValueError("invalid bounded watch replay options")
    ledger=Path(ledger).resolve(strict=True)
    stock=Path(stock).resolve(strict=True)
    if ledger==stock:
        raise ValueError("source and sidecar must be separate databases")
    asof=int(time.time() if now is None else now)
    start=asof-hours*3600
    with closing(ro(ledger)) as db:
        initial_all,initial_raw,invalid=select_candidates(
            db,start=start,end=asof,keys=keys,limit=limit)
        starts=first_per_item_hour(initial_all)
        # Include later ticks for all starting points; narrow time range.
        events,times,all_raw=future_candidate_timelines(
            db,start=start,end=asof,keys=keys)
        decisions=[
            (original,first_actionable_tick(
                original,events[original["item_key"]],
                times[original["item_key"]],now=asof))
            for original in starts]
    all_out=Counter()
    by_item=defaultdict(Counter)
    by_family=defaultdict(Counter)
    by_delay=defaultdict(Counter)
    examples=[]
    with closing(ro(stock)) as source:
        for original,action in decisions:
            key=original["item_key"]
            country,item=key.split(":",1)
            wait_bucket=delay_bucket(
                int(original["departure"])-int(original["computed_at"]))
            buckets=(all_out,by_item[key],
                     by_family[original["model_family"]],
                     by_delay[wait_bucket])
            baseline_arrival=int(original["computed_at"])+TRAVEL_SECONDS[country]
            baseline_status,baseline_hit,_=scorer(
                source,country,item,baseline_arrival,asof)
            if action["arrival"] is None:
                ready_status=action["status"]
                ready_hit=None
            else:
                ready_status,ready_hit,_=scorer(
                    source,country,item,int(action["arrival"]),asof)
            for c in buckets:
                c["hourly_start_cohort"]+=1
                c[action["status"]]+=1
                c[f"immediate_{baseline_status}"]+=1
                c[f"first_ready_{ready_status}"]+=1
                if action["arrival"] is not None:
                    c["ready_departure_issued"]+=1
                    c["ready_wait_seconds_sum"]+=(
                        action["departure"]-int(original["computed_at"]))
                    c["ready_arrival_matured"]+=int(ready_hit is not None)
                if baseline_hit is not None:
                    c["immediate_arrival_matured"]+=1
                if ready_hit is not None and baseline_hit is not None:
                    c["paired_scorable"]+=1
                    tag=(
                        "both_hit" if ready_hit and baseline_hit else
                        "ready_only_hit" if ready_hit else
                        "immediate_only_hit" if baseline_hit else
                        "both_miss")
                    c[tag]+=1
            if len(examples)<8:
                examples.append({
                    "item":key,"original_issue":int(original["computed_at"]),
                    "model_family":original["model_family"],
                    "original_watch_delay_minutes":round((
                        int(original["departure"])-int(original["computed_at"])
                    )/60,2),
                    "first_executable_status":action["status"],
                    "executable_issue":action["ready_issue"],
                    "executable_departure":action["departure"],
                    "original_vs_executable_departure_shift_minutes":(
                        round(action["original_departure_shift_seconds"]/60,2)
                        if action["original_departure_shift_seconds"] is not None
                        else None),
                    "ready_arrival_status":ready_status,
                    "immediate_arrival_status":baseline_status,
                    "provider_country_age_verified":False,
                })
    return {
        "status":"V117_FROZEN_FIVE_MINUTE_REPLAN_FIRST_ACTIONABLE_AUDIT",
        "research_only":True,"read_only":True,
        "hours":hours,"asof_epoch":asof,
        "item_keys":list(keys),
        "raw_initial_candidate_rows":initial_raw,
        "invalid_initial_rows":invalid,
        "valid_unique_initial_arrival_targets":len(initial_all),
        "first_per_item_UTC_hour_start_cohort":len(starts),
        "raw_ticks_in_window":all_raw,
        "policy":"FIRST_VALID_5M_ACTIONABLE_AS_ISSUED_TICK_WITHIN_8H",
        "must_count_no_trip_and_pending_separately":True,
        "same_cohort_as_v116":True,
        "departure_scheduled_without_future_stock_outcome":True,
        "observed_player_travel_verified":False,
        "country_specific_provider_age_verified":False,
        "per_item":{k:materialize(v) for k,v in sorted(by_item.items())},
        "per_model_family":{k:materialize(v) for k,v in sorted(by_family.items())},
        "by_original_watch_delay":{
            k:materialize(v) for k,v in sorted(by_delay.items())},
        "overall":materialize(all_out),
        "examples":examples,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--items",nargs="+",choices=tuple(ITEMS),
                   default=["redfox","nessie"])
    p.add_argument("--limit",type=int,default=MAX_PROXY_EVENTS)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved collector source")
    r=audit(
        hours=a.hours,
        keys=tuple(ITEMS[k] for k in dict.fromkeys(a.items)),
        limit=a.limit)
    if a.json:
        print(json.dumps(r,sort_keys=True))
        return
    print("===== V117 FROZEN 5M REPLANNING: FIRST EXECUTABLE DEPARTURE =====")
    print("Same cohort as V116, target items:",r["item_keys"])
    print("hourly start units:",r["first_per_item_UTC_hour_start_cohort"],
          "valid initial targets:",r["valid_unique_initial_arrival_targets"],
          "raw tick records:",r["raw_ticks_in_window"])
    print("overall:",json.dumps(r["overall"],sort_keys=True))
    print("per item:",json.dumps(r["per_item"],sort_keys=True))
    print("per champion model family:",
          json.dumps(r["per_model_family"],sort_keys=True))
    print("by original delay:",
          json.dumps(r["by_original_watch_delay"],sort_keys=True))
    print("examples:",json.dumps(r["examples"][:3],sort_keys=True))
    print("NOTE: candidate replay not actual execution. No fresh UK country epochs.")


if __name__=="__main__":
    main()
