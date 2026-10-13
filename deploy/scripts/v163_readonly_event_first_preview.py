#!/usr/bin/env python3
"""V163 read-only event-first restock timeline; no publication or game action.

Unlike V151's single first eligible arrival-bin, enumerate the predicted
threshold restocks themselves, then derive travel windows for EACH event.
Future event timestamps are estimates, not established 90% forecasts.
The collector is change-only; current zero can remain valid between polls.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v128_full24_earliest_shadow import _read_item,exact_roster
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v60_private_snapshot_probe import read_heartbeat

COLLECTOR=Path("/opt/torn-fren/data/stock_history.db")
STEP=300
MAX_HORIZON=28800
MIN_QTY=30
GRACE=10
MAX_EVENTS=64
MAX_GAPS=15000
MIN_BOUNDED=3
MAX_HEARTBEAT_AGE=180


def quantile(items,prob):
    """Discrete empirical quantile, without interpolation."""
    if not items or type(prob) is not float or not 0<=prob<=1:
        raise ValueError("invalid quantile request")
    ordered=sorted(items)
    if any(type(x) is not int or x<=0 for x in ordered):
        raise ValueError("invalid phase duration history")
    return ordered[max(0,math.ceil(len(ordered)*prob)-1)]


def phase_quantiles(observed,*,age=0):
    if type(age) is not int or age<0:
        raise ValueError("invalid conditioned phase age")
    residuals=[x-age for x in observed if x>age]
    if not residuals:
        return None
    return {p:quantile(residuals,q) for p,q in
            (("early",.25),("middle",.50),("late",.75))}


def _window(item,asof,start,stocked_duration,early_start,late_start,early_lifetime):
    flight=TRAVEL_SECONDS[item.split(":",1)[0]]
    end=start+stocked_duration
    # Arrival scoring includes +10s: do not land exactly on the
    # boundary before a restock or after the predicted sellout.
    first=max(asof,start-flight-GRACE)
    arrival=first+flight+GRACE
    latest=end-flight-GRACE-1
    expected=first if arrival>=start and first<=latest and first<=asof+MAX_HORIZON else None
    conservative_first=max(asof,late_start-flight-GRACE)
    conservative_latest=early_start+early_lifetime-flight-GRACE-1
    conservative=(conservative_first if
                  conservative_first<=conservative_latest
                  and conservative_first<=asof+MAX_HORIZON
                  else None)
    return {
        "predicted_restock_epoch":start,
        "predicted_stock_below_30_epoch":end,
        "restock_early_epoch":early_start,
        "restock_late_epoch":late_start,
        "estimated_stocked_duration_seconds":stocked_duration,
        "expected_departure_epoch":expected,
        "expected_latest_departure_epoch":latest if expected is not None else None,
        "expected_arrival_epoch":expected+flight+GRACE if expected is not None else None,
        "conservative_estimate_departure_epoch":conservative,
        "expected_departure_reachable":expected is not None,
        "conservative_estimate_available":conservative is not None,
        "reason":("MODELED_REACHABLE_RECONFIRM" if expected is not None else
                  "MODELED_RESTOCK_NOT_REACHABLE_WITH_CURRENT_FLIGHT"),
    }


def predict_events(item,phases,*,asof,horizon=MAX_HORIZON,
                   max_events=MAX_EVENTS,min_bounded=MIN_BOUNDED):
    """All modeled replenishments up to horizon, not just selected flights.

    Causal input: phase evidence closed at or before asof, plus the
    known ongoing phase/censoring age. Model future cycle uncertainty
    grows; these are *estimates*, with no calibrated forecast accuracy.
    """
    if (type(asof) is not int or asof<=0 or type(horizon) is not int
        or not 300<=horizon<=MAX_HORIZON or type(max_events) is not int
        or not 1<=max_events<=MAX_EVENTS or
        type(min_bounded) is not int or not 1<=min_bounded<=20 or
        not isinstance(item,str) or item.count(":")!=1 or
        item.split(":",1)[0] not in TRAVEL_SECONDS):
        raise ValueError("invalid event forecast policy")
    common={
        "item_key":item,"asof_epoch":asof,
        "status":"INSUFFICIENT_BOUNDED_RESTOCK_HISTORY",
        "predictions_are_provisional":True,
        "restock_accuracy_verified":False,
        "not_a_success_probability":True,
        "arrival_stock_threshold":MIN_QTY,
        "flight_seconds":TRAVEL_SECONDS[item.split(":",1)[0]],
        "restock_events":[],"current_stock_window":None,
        "forecast_event_count":0,
        "currently_supported_departures":0,
        "unreachable_restock_events":0,
        "current_phase":phases.get("phase"),
        "phase_age_seconds":None,
        "history_stocked_phases":len(phases.get("stocked_durations") or []),
        "history_depleted_phases":len(phases.get("depleted_durations") or []),
    }
    high=phases.get("stocked_durations")
    low=phases.get("depleted_durations")
    if (not isinstance(high,list) or not isinstance(low,list)
        or min(len(high),len(low))<min_bounded):
        return common
    onset=phases.get("phase_onset")
    phase=phases.get("phase")
    last=phases.get("last_observation")
    if (phase not in ("HIGH","LOW") or type(onset) is not int
        or onset>asof or onset<=0 or last is None
        or type(last.epoch) is not int or last.epoch>asof
        or asof-last.epoch>86400):
        return dict(common,status="CURRENT_PHASE_UNKNOWN")
    age=asof-onset
    active=phase_quantiles(high if phase=="HIGH" else low,age=age)
    if active is None:
        return dict(common,status="CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS",
                    phase_age_seconds=age)
    hi=phase_quantiles(high)
    lo=phase_quantiles(low)
    if hi is None or lo is None:
        return common
    common["phase_age_seconds"]=age
    common["status"]="EVENT_TIMELINE_FORECAST_AVAILABLE"
    # Maintain separate early/median/late EVENT clocks so uncertain future
    # restocks are shown with widening bounds, not perfect point estimates.
    if phase=="HIGH":
        now_window=_window(
            item,asof,asof,active["middle"],asof,asof,
            active["early"])
        common["current_stock_window"]=now_window
        low_start={
            p:asof+active[p] for p in ("early","middle","late")}
        next_restock={p:low_start[p]+lo[p] for p in ("early","middle","late")}
    else:
        next_restock={p:asof+active[p] for p in ("early","middle","late")}
    events=[]
    for idx in range(max_events):
        median=next_restock["middle"]
        if median>asof+horizon:
            break
        remaining=max(0,asof+horizon-median)
        window=_window(
            item,asof,median,hi["middle"],next_restock["early"],
            next_restock["late"],hi["early"])
        window["event_index"]=idx+1
        window["restock_relative_to_now_seconds"]=median-asof
        window["restock_window_width_seconds"]=(
            next_restock["late"]-next_restock["early"])
        window["projected_beyond_first_cycle"]=idx>0
        events.append(window)
        # Repeated future cycles: include *all* predicted restocks within
        # the horizon, whether or not the user can travel to that event.
        next_restock={
            p:next_restock[p]+hi[p]+lo[p] for p in ("early","middle","late")}
        if remaining<=0:
            break
    common["restock_events"]=events
    common["forecast_event_count"]=len(events)
    common["currently_supported_departures"]=sum(
        event["expected_departure_epoch"] is not None for event in events)
    common["unreachable_restock_events"]=sum(
        event["expected_departure_epoch"] is None for event in events)
    common["event_horizon_seconds"]=horizon
    common["bounded_event_list_truncated"]=(
        len(events)==max_events and next_restock["middle"]<=asof+horizon)
    return common


def forecast_all(*,source=COLLECTOR,asof=None,roster=None,
                 horizon=MAX_HORIZON):
    now=int(time.time()) if asof is None else asof
    if type(now) is not int or now<=0:
        raise ValueError("invalid issue epoch")
    catalog=exact_roster() if roster is None else roster
    if not isinstance(catalog,dict) or len(catalog)!=24:
        raise ValueError("unexpected foreign item roster")
    dbfile=Path(source).resolve(strict=True)
    with closing(sqlite3.connect(dbfile.as_uri()+"?mode=ro",uri=True,timeout=12)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        try:
            heartbeat=read_heartbeat(db)
            age=now-heartbeat if type(heartbeat) is int else None
            if age is None or not 0<=age<=MAX_HEARTBEAT_AGE:
                raise ValueError("collector successful poll heartbeat not recent")
            gaps=db.execute(
                """SELECT start_timestamp,end_timestamp FROM collection_gaps
                   WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?""",
                (now,MAX_GAPS+1)).fetchall()
            if len(gaps)>MAX_GAPS:
                raise ValueError("too many collection gap events")
            all_items={}
            for item in sorted(catalog):
                rows,error=_read_item(db,item,now)
                if error or not rows:
                    all_items[item]={
                        "status":"NO_VALID_ITEM_STOCK_HISTORY",
                        "restock_events":[],"forecast_event_count":0,
                        "current_stock_window":None}
                    continue
                phases=provider_continuous_phases(rows,asof=now,gaps=gaps)
                all_items[item]=predict_events(
                    item,phases,asof=now,horizon=horizon)
        finally:
            db.execute("ROLLBACK")
    return {"status":"V163_READ_ONLY_MULTI_RESTOCK_EVENT_TIMELINE",
            "asof_epoch":now,"source_heartbeat_age_seconds":age,
            "roster":len(all_items),"items":all_items,
            "restock_events_forecast":sum(v.get("forecast_event_count",0)
                                          for v in all_items.values()),
            "item_count_with_event_forecast":sum(
                v.get("forecast_event_count",0)>0 for v in all_items.values()),
            "lookahead_used":False,
            "collector_written":False,"private_ledgers_written":False,
            "public_websites_modified":False,
            "validated_restock_timing_success":None,
            "validated_stock_on_arrival_success":None}


def format_report(report):
    header=[
        "V163 EVENT-FIRST 24 ITEM PREVIEW — ONLY FUTURE RESTOCK ESTIMATES",
        "Issue epoch "+str(report["asof_epoch"])+
          " | source successful poll age "+
          str(report["source_heartbeat_age_seconds"])+" s",
        "Event forecasts: "+str(report["restock_events_forecast"])+
         "; items forecast: "+str(report["item_count_with_event_forecast"])+"/24",
        "RESTOCK TIMING ACCURACY: NOT YET MEASURED. "
        "Expected arrival >=30 success: NOT YET MEASURED for V163.",
        "A restock may be projected but UNREACHABLE for your country flight. "
        "Unreachable does NOT mean the event was ignored.",
        "",
        f"{'ITEM':<27} {'PHASE':<5} {'EVENTS':>6} {'REACHABLE':>9} {'FIRST RESTOCK':>15} {'NEXT DEPARTURE':>15}  STATUS",
        "-"*117,
    ]
    for item,v in sorted(report["items"].items()):
        events=v["restock_events"]
        first=events[0] if events else {}
        first_departure=next((x["expected_departure_epoch"]
            for x in events if x["expected_departure_epoch"] is not None),None)
        header.append(
            f"{item[:27]:<27} {str(v.get('current_phase','?')):<5} "
            f"{len(events):>6} {str(v.get('currently_supported_departures',0)):>9} "
            f"{str(first.get('predicted_restock_epoch','—')):>15} "
            f"{str(first_departure if first_departure is not None else '—'):>15}  "
            f"{v['status']}")
    for item in ("uni:Nessie Plushie","jap:Xanax"):
        v=report["items"][item]
        header.append("\n"+item+" FULL ESTIMATED EVENT LIST:")
        for event in v["restock_events"][:30]:
            header.append(json.dumps(event,sort_keys=True))
        if not v["restock_events"]:
            header.append("No forecastable future restock; reason="+v["status"])
    return "\n".join(header)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours",type=int,default=8)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    if not 1<=args.hours<=8:
        parser.error("horizon must be 1-8 hours")
    result=forecast_all(horizon=args.hours*3600)
    print(json.dumps(result,sort_keys=True) if args.json else format_report(result))


if __name__=="__main__":
    main()
