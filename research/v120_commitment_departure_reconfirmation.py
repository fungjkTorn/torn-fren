"""V120: fixed-cohort recheck of V119 future departure commitments.

V119's three-forecast commitment offered 25/25 scheduled Nessie flights,
but the flight-stock proxy on matched scorable arrivals was 11/16 versus
12/16 depart-now, and future commitments may later be contradicted by
as-issued five-minute model updates.

On the EXACT SAME 50 earliest eligible V75 item/hour starts and frozen
as-of, select the unchanged V119 policy. AFTER selection, audit the LAST
as-issued research tick in the ten minutes before the chosen departure:
- fresh recommender still supports within +/-5 minutes AND original
  departure is inside the new five-minute snapshot;
- target approximately the same, but new snapshot expires too early;
- predicted departure shifted earlier/later;
- invalid/abstained tick;
- missing recent tick;
- departure time not reached yet.

Late rechecks use ONLY information that existed at/before the selected
departure epoch; a future planned departure receives PENDING, not a
retroactive validation. Rechecks are DIAGNOSTIC: they never change the
V119 decision or select a flight based on future availability.

Score already-selected arrivals with the same V88 historical polling
proxy, separately by recheck classification. Missing data and pending
outcomes remain unknown, not failures. One heartbeat != fresh UK country
provider stock. The cohort shares restocks and is previously inspected.

No production/code/service/VM timer/API modifications, no player actions.
Both source SQLite files always opened read-only. No model retraining.
"""
from __future__ import annotations

import argparse
import bisect
import json
import time
from collections import Counter,defaultdict
from contextlib import closing

from research.plushie_champions.common import MAX_WAIT,TRAVEL_SECONDS
from research.v76_forward_research_report import V75,eligible,ro,MAX_PROXY_EVENTS
from research.v88_poll_state_forward_report import (
    SOURCE,observation as poll_observation
)
from research.v115_targeted_v88_forward_evidence import ITEMS
from research.v116_attributed_hourly_forward_audit import (
    select_candidates,first_per_item_hour
)
from research.v117_first_executable_replan_audit import future_candidate_timelines
from research.v119_stable_commitment_vs_fresh_replay import frozen_policy
from research.v60_private_snapshot_probe import approved_collector_source

RECHECK_LOOKBACK=600
MATCH_TOLERANCE=300
MAX_HOURS=24


def recheck_selected_departure(*,selection,original,rows,times,asof):
    """Check LAST recorded source-pinned model tick just before departure.

    Selection must be made independently before this diagnostic is called.
    No stock observations or after-departure predictions are consulted.
    """
    departed_at=selection["departure"]
    if departed_at is None:
        return {
            "status":"NO_SCHEDULED_FLIGHT",
            "scheduled_departure":None,
            "departure_reached_asof":False,
        }
    dep=int(departed_at)
    if not int(original["computed_at"])<=dep<=int(original["computed_at"])+MAX_WAIT:
        raise AssertionError("scheduled outside initial wait budget")
    if asof<dep:
        return {
            "status":"SCHEDULED_DEPARTURE_NOT_YET_REACHED",
            "scheduled_departure":dep,
            "departure_reached_asof":False,
        }
    if selection["committed_issue"]>dep:
        raise AssertionError("plan committed after departure")
    end=bisect.bisect_right(times,dep)
    start=bisect.bisect_left(times,dep-RECHECK_LOOKBACK)
    nearby=[r for r in rows[start:end]
            if r["model_family"]==original["model_family"]]
    if not nearby:
        return {
            "status":"NO_REPLAN_WITHIN_10M_OF_DEPARTURE",
            "scheduled_departure":dep,
            "departure_reached_asof":True,
        }
    latest=nearby[-1]
    at=int(latest["computed_at"])
    if at>dep:
        raise AssertionError("future replan used to recheck departure")
    if not eligible(latest):
        return {
            "status":"LATEST_REPLAN_INVALID_OR_ABSTAINED",
            "scheduled_departure":dep,
            "last_issue":at,
            "last_status":latest["status"],
            "departure_reached_asof":True,
        }
    new_departure=int(latest["departure"])
    delta=new_departure-dep
    if abs(delta)<=MATCH_TOLERANCE:
        if (int(latest["valid_until"])>=dep
            and new_departure<=int(latest["valid_until"])):
            status="RECONFIRMED_INSIDE_FRESH_5M_SNAPSHOT"
        else:
            status="NEAR_SAME_TARGET_BUT_NOT_FRESHLY_EXECUTABLE"
    elif delta>0:
        status="LATEST_FORECAST_SHIFTED_LATER"
    else:
        status="LATEST_FORECAST_SHIFTED_EARLIER"
    return {
        "status":status,
        "scheduled_departure":dep,
        "departure_reached_asof":True,
        "last_issue":at,
        "last_forecast_departure":new_departure,
        "drift_seconds":delta,
        "last_valid_until":int(latest["valid_until"]),
        "last_wait_from_issue_seconds":new_departure-at,
    }


def materialize(records):
    c=Counter()
    by_status=defaultdict(Counter)
    for r in records:
        check=r["recheck"]
        code=check["status"]
        cs=(c,by_status[code])
        for counter in cs:
            counter["selected_committed_starts"]+=1
            counter["status_"+code]+=1
            counter["departure_reached_asof"]+=int(
                check["departure_reached_asof"])
            if r["stock"]=="POLL_STATE_PROXY_SUCCESS":
                counter["arrival_stock_proxy_hit"]+=1
            elif r["stock"]=="POLL_STATE_PROXY_MISS":
                counter["arrival_stock_proxy_miss"]+=1
            else:
                counter["arrival_stock_proxy_unknown"]+=1
            if r["stock"]=="PENDING_ARRIVAL":
                counter["future_arrival_pending"]+=1
    return {
        "total":dict(sorted(c.items())),
        "by_latest_departure_recheck":{
            key:dict(sorted(value.items()))
            for key,value in sorted(by_status.items())
        }
    }


def audit(*,ledger=V75,stock=SOURCE,now=None,hours=24,
          keys=tuple(ITEMS.values()),limit=MAX_PROXY_EVENTS,
          scorer=poll_observation):
    if (not 1<=hours<=MAX_HOURS
        or not 1<=limit<=MAX_PROXY_EVENTS
        or not 1<=len(keys)<=len(ITEMS)
        or len(set(keys))!=len(keys)
        or not set(keys)<=set(ITEMS.values())):
        raise ValueError("invalid bounded recheck options")
    asof=int(time.time() if now is None else now)
    if asof>time.time()+300:
        raise ValueError("cannot inspect future research tick")
    if str(ledger)==str(stock):
        raise ValueError("collector and research ledger must differ")
    start=asof-hours*3600
    with closing(ro(ledger)) as db:
        raw,raw_count,invalid=select_candidates(
            db,start=start,end=asof,keys=keys,limit=limit)
        cohort=first_per_item_hour(raw)
        timelines,times,raw_ticks=future_candidate_timelines(
            db,start=start,end=asof,keys=keys)
        decisions=[]
        for original in cohort:
            item_key=original["item_key"]
            selection=frozen_policy(
                original,timelines[item_key],times[item_key],asof=asof)
            recheck=recheck_selected_departure(
                selection=selection,original=original,
                rows=timelines[item_key],times=times[item_key],
                asof=asof)
            decisions.append((original,selection,recheck))
    results=[]
    with closing(ro(stock)) as collector:
        for original,choice,recheck in decisions:
            country,item=original["item_key"].split(":",1)
            departure=choice["departure"]
            if departure is None:
                stock_status="NO_TRIP"
            else:
                arrival=int(departure)+TRAVEL_SECONDS[country]
                if arrival+190>asof:
                    stock_status="PENDING_ARRIVAL"
                else:
                    stock_status,hit,_=scorer(
                        collector,country,item,arrival,asof)
            results.append({
                "item_key":original["item_key"],
                "start":int(original["computed_at"]),
                "model_family":original["model_family"],
                "chosen_basis":choice["basis"],
                "policy_status":choice["status"],
                "scheduled_departure":departure,
                "committed_at":choice["committed_issue"],
                "recheck":recheck,
                "stock":stock_status,
            })
    committed=[r for r in results if r["chosen_basis"]=="three_as_issued"]
    fresh=[r for r in results if r["chosen_basis"]=="fresh"]
    by_item=defaultdict(list)
    for r in committed:
        by_item[r["item_key"]].append(r)
    return {
        "status":"V120_FIXED_ASOF_DEPARTURE_COMMITMENT_RECONFIRMATION",
        "read_only":True,
        "asof_epoch":asof,
        "hours":hours,
        "cohort_first_item_UTC_hour":len(cohort),
        "valid_unique_initial_arrivals":len(raw),
        "raw_candidate_rows":raw_count,
        "tracked_ticks":raw_ticks,
        "stable_commitment_selected":len(committed),
        "fresh_selected":len(fresh),
        "no_selection":len(results)-len(committed)-len(fresh),
        "same_cohort_and_original_selection_as_v119":True,
        "late_rechecks_do_not_change_departure_selection":True,
        "country_provider_freshness_verified":False,
        "gameplay_flights_verified":False,
        "previously_examined_validation_window":True,
        "stable_commitments":materialize(committed),
        "stable_commitments_by_item":{
            key:materialize(rs) for key,rs in sorted(by_item.items())
        },
        "examples":[{
            "item":r["item_key"],
            "issued":r["start"],
            "departure":r["scheduled_departure"],
            "committed_at":r["committed_at"],
            "recheck":r["recheck"],
            "stock":r["stock"]
        } for r in committed[:6]],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asof",type=int,default=None)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--items",nargs="+",choices=tuple(ITEMS),
                   default=["redfox","nessie"])
    p.add_argument("--limit",type=int,default=MAX_PROXY_EVENTS)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved collector source")
    result=audit(
        now=a.asof,hours=a.hours,limit=a.limit,
        keys=tuple(ITEMS[k] for k in dict.fromkeys(a.items)))
    if a.json:
        print(json.dumps(result,sort_keys=True))
        return
    print("===== V120 SAME V119 STABLE COMMITMENTS: DEPARTURE RECHECK =====")
    print("asof:",result["asof_epoch"],
          "hourly starts:",result["cohort_first_item_UTC_hour"],
          "stable:",result["stable_commitment_selected"],
          "fresh:",result["fresh_selected"],
          "none:",result["no_selection"])
    print("ALL STABLE:",json.dumps(
        result["stable_commitments"],sort_keys=True))
    for name,entry in result["stable_commitments_by_item"].items():
        print(name,json.dumps(entry,sort_keys=True))
    print("examples:",json.dumps(result["examples"][:4],sort_keys=True))
    print("READ ONLY, POST-COMMITMENT RECHECK IS DIAGNOSTIC NOT FLIGHT SELECTION.")


if __name__=="__main__":
    main()
