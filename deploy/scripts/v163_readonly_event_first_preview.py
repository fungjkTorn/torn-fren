#!/usr/bin/env python3
"""V163 read-only event-first restock timeline; no publication or game action.

Unlike V151's single first eligible arrival-bin, enumerate the predicted
threshold restocks themselves, then derive travel windows for EACH event.
Future event timestamps are estimates, not established 90% forecasts.
The collector is change-only; current zero can remain valid between polls.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter,namedtuple
from contextlib import closing
from pathlib import Path

# The VM keeps V128/V145 and dependencies in an immutable staged research
# directory. A source file streamed to `python -` is not guaranteed to
# inherit that research package path from the mutable checkout. The live
# one-item recheck explicitly pins research.__path__; the standalone CLI
# must do the same. When the stage does not exist (e.g., GitHub CI), normal
# checked-out research modules remain in use.
PINNED_RESEARCH_STAGE=Path(os.environ.get(
    "TORNFREN_REPLAY_PINNED_RESEARCH",
    "/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research"
))
if PINNED_RESEARCH_STAGE.is_dir():
    WORK=Path(os.environ.get(
        "TORNFREN_REPLAY_WORK","/home/ubuntu/torn-fren-v38-probe"))
    if not WORK.is_dir():
        raise RuntimeError("pinned replay research checkout missing")
    sys.path.insert(0,str(WORK))
    import research
    research.__path__=[str(PINNED_RESEARCH_STAGE)]

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v128_full24_earliest_shadow import _gap_index,_read_item,exact_roster
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v60_private_snapshot_probe import read_heartbeat

COLLECTOR=Path("/opt/torn-fren/data/stock_history.db")
STEP=300
MAX_HORIZON=None  # legacy compatibility only; no product time horizon
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
    expected=first if arrival>=start and first<=latest else None
    conservative_first=max(asof,late_start-flight-GRACE)
    conservative_latest=early_start+early_lifetime-flight-GRACE-1
    conservative=(conservative_first if
                  conservative_first<=conservative_latest
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


def predict_events(item,phases,*,asof,horizon=None,
                   max_events=MAX_EVENTS,min_bounded=MIN_BOUNDED,
                   recent_cycles=None):
    """All modeled replenishments up to horizon, not just selected flights.

    Causal input: phase evidence closed at or before asof, plus the
    known ongoing phase/censoring age. Model future cycle uncertainty
    grows; these are *estimates*, with no calibrated forecast accuracy.
    """
    if (type(asof) is not int or asof<=0
        or (horizon is not None and (type(horizon) is not int or horizon<300))
        or type(max_events) is not int
        or not 1<=max_events<=MAX_EVENTS or
        type(min_bounded) is not int or not 1<=min_bounded<=20 or
        not isinstance(item,str) or item.count(":")!=1 or
        item.split(":",1)[0] not in TRAVEL_SECONDS or
        (recent_cycles is not None and (
            type(recent_cycles) is not int or not 4<=recent_cycles<=128))):
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
        "observed_current_quantity":getattr(phases.get("last_observation"),"quantity",None),
        "last_quantity_change_epoch":getattr(phases.get("last_observation"),"epoch",None),
        "phase_age_seconds":None,
        "history_stocked_phases":len(phases.get("stocked_durations") or []),
        "history_depleted_phases":len(phases.get("depleted_durations") or []),
    }
    high=phases.get("stocked_durations")
    low=phases.get("depleted_durations")
    if (not isinstance(high,list) or not isinstance(low,list)
        or min(len(high),len(low))<min_bounded):
        return common
    # Optional research challenger: recent completed cycles, never future data.
    if recent_cycles is not None:
        high=high[-recent_cycles:]
        low=low[-recent_cycles:]
    common["cycle_window"]=recent_cycles if recent_cycles is not None else "all"
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
    hi=phase_quantiles(phases.get("future_stocked_durations",high))
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
        if horizon is not None and median>asof+horizon:
            break
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
    common["restock_events"]=events
    common["forecast_event_count"]=len(events)
    common["currently_supported_departures"]=sum(
        event["expected_departure_epoch"] is not None for event in events)
    common["unreachable_restock_events"]=sum(
        event["expected_departure_epoch"] is None for event in events)
    common["event_horizon_seconds"]=horizon
    common["event_horizon_type"]="EVENT_COUNT_ONLY" if horizon is None else "LEGACY_TIME_BOUND"
    common["bounded_event_list_truncated"]=(
        len(events)==max_events and
        (horizon is None or next_restock["middle"]<=asof+horizon))
    return common


def forecast_all(*,source=COLLECTOR,asof=None,roster=None,
                 horizon=None):
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
                        "item_key":item,"asof_epoch":now,
                        "flight_seconds":TRAVEL_SECONDS[item.split(":",1)[0]],
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


OBS=namedtuple("OBS",["epoch","quantity","source"])
BACKTEST_WINDOW=4*3600
MAX_ITEM_CHANGE_ROWS=50000


def confirmed_restocks(rows,gaps,*,start,end):
    """Clean <30 -> >=30 transitions, no cross-provider/gap inventions."""
    events=[]
    ambiguous=0
    prev=None
    for obs in rows:
        if obs.epoch>end:
            break
        if prev is not None and start<obs.epoch<=end:
            if prev.quantity<MIN_QTY<=obs.quantity:
                if obs.source!=prev.source or any(
                    gap_start<=obs.epoch and
                    (gap_end is None or gap_end>=prev.epoch)
                    for gap_start,gap_end in gaps
                ):
                    ambiguous+=1
                else:
                    events.append(obs.epoch)
        prev=obs
    return events,ambiguous


def match_events(predicted,actual,*,tolerance=600):
    """Optimal one-to-one, ORDER-PRESERVING event matching.

    Maximize number of restocks matched before minimizing the summed
    absolute timing error. A greedy nearest-neighbor can undercount real
    successful forecast events when adjacent restock windows overlap.
    The optimal matching for sorted one-dimensional absolute distances
    admits noncrossing assignments, so dynamic programming is exact.
    """
    if type(tolerance) is not int or tolerance<0:
        raise ValueError("invalid event timing tolerance")
    if (len(predicted)>MAX_EVENTS or len(actual)>MAX_ITEM_CHANGE_ROWS or
        any(type(t) is not int for t in predicted+actual)):
        raise ValueError("invalid or unbounded event lists")
    p=sorted(predicted)
    a=sorted(actual)
    # Score (number matched, negative absolute error): lexicographic max.
    # Use rolling rows: O(predicted * actual) time, O(actual) memory.
    old=[(0,0)]*(len(a)+1)
    for issue in p:
        new=[(0,0)]
        for j,event in enumerate(a,1):
            skip_prediction=old[j]
            skip_observed=new[j-1]
            best=max(skip_prediction,skip_observed)
            delta=abs(issue-event)
            if delta<=tolerance:
                matched,error_score=old[j-1]
                best=max(best,(matched+1,error_score-delta))
            new.append(best)
        old=new
    matched,negative_error=old[-1]
    return {
        "matched":matched,
        "missed_actual":len(a)-matched,
        "false_predicted":len(p)-matched,
        "sum_absolute_timing_error_seconds":-negative_error,
    }



class _ReplayPhases:
    """Incremental causal equivalent of the V145 completed-phase tracker."""
    def __init__(self,crosses):
        self.crosses=crosses
        self.last=None
        self.current=None
        self.onset=None
        self.high=[]
        self.low=[]

    def add(self,obs):
        high=obs.quantity>=MIN_QTY
        prev=self.last
        if prev is None:
            self.current,self.onset=high,None
        else:
            gap=(obs.epoch<=prev.epoch or
                 self.crosses(prev.epoch,obs.epoch))
            if gap or (obs.source!=prev.source and high!=self.current):
                self.current,self.onset=high,None
            elif high!=self.current:
                if self.onset is not None and obs.epoch>self.onset:
                    (self.high if self.current else self.low).append(
                        obs.epoch-self.onset)
                self.current,self.onset=high,obs.epoch
        self.last=obs

    def asof(self):
        return {
            "phase":"HIGH" if self.current is True else
                    "LOW" if self.current is False else "UNKNOWN",
            "phase_onset":self.onset,
            "last_observation":self.last,
            "stocked_durations":self.high.copy(),
            "depleted_durations":self.low.copy(),
        }


def _replay_restock_index(observations,gaps,now):
    crosses=_gap_index(gaps,now)
    clean=[]
    ambiguous=[]
    prev=None
    for obs in observations:
        if prev is not None and prev.quantity<MIN_QTY<=obs.quantity:
            if obs.source!=prev.source or crosses(prev.epoch,obs.epoch):
                ambiguous.append(obs.epoch)
            else:
                clean.append(obs.epoch)
        prev=obs
    return crosses,clean,ambiguous



def replay_events(*,source=COLLECTOR,roster=None,asof=None,days=7,
                  tolerance=600,max_changes=MAX_ITEM_CHANGE_ROWS,
                  limit_items=24,progress=None,cycle_windows=()):
    """Historical as-of replay only; NEVER a truly issued V160/163 forecast.

    One fixed, nonoverlapping 4-hour historical cohort per item; every
    eligible observed restock within that window is counted. Reconstruct
    predictions using ONLY <= cutoff data, then score after the cutoff.
    This is not 5-minute replanning accuracy or a calibrated 90% result.
    """
    if (type(days) is not int or not 1<=days<=14
        or type(tolerance) is not int or not 60<=tolerance<=1800
        or type(max_changes) is not int or not 100<=max_changes<=MAX_ITEM_CHANGE_ROWS
        or type(limit_items) is not int or not 1<=limit_items<=24
        or not isinstance(cycle_windows,tuple)
        or len(cycle_windows)>4
        or len(cycle_windows)!=len(set(cycle_windows))
        or any(type(x) is not int or not 4<=x<=128 for x in cycle_windows)):
        raise ValueError("unbounded replay parameters")
    now=int(time.time()) if asof is None else asof
    start=now-days*86400
    cutoffs=range(((start+BACKTEST_WINDOW-1)//BACKTEST_WINDOW)*BACKTEST_WINDOW,
                  (now//BACKTEST_WINDOW)*BACKTEST_WINDOW,BACKTEST_WINDOW)
    catalog=exact_roster() if roster is None else roster
    if not isinstance(catalog,dict) or len(catalog)!=24:
        raise ValueError("unexpected item identities")
    all_results={}
    with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+
                                 "?mode=ro",uri=True,timeout=12)) as conn:
        conn.execute("PRAGMA query_only=ON")
        gaps=conn.execute(
            """SELECT start_timestamp,end_timestamp FROM collection_gaps
               WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?""",
            (now,MAX_GAPS+1)
        ).fetchall()
        if len(gaps)>MAX_GAPS:
            raise ValueError("too many gaps")
        for item in sorted(catalog)[:limit_items]:
            country,name=item.split(":",1)
            raw=conn.execute(
                """SELECT timestamp,quantity,source FROM stock_history
                   WHERE country=? AND lower(item_name)=lower(?)
                     AND timestamp<=?
                   ORDER BY timestamp ASC,id ASC LIMIT ?""",
                (country,name,now,max_changes+1)
            ).fetchall()
            if len(raw)>max_changes:
                raise ValueError("change history limit exceeded for "+item)
            observations=[OBS(int(t),int(q),str(provider))
                          for t,q,provider in raw if
                          t is not None and q is not None and provider
                          and int(q)>=0]
            crosses,restocks,ambiguous=_replay_restock_index(
                observations,gaps,now)
            phases=_ReplayPhases(crosses)
            cursor=0
            c=Counter()
            statuses=Counter()
            challengers={n:Counter() for n in cycle_windows}
            challenger_statuses={n:Counter() for n in cycle_windows}
            for issue in cutoffs:
                while cursor<len(observations) and observations[cursor].epoch<=issue:
                    phases.add(observations[cursor])
                    cursor+=1
                first=bisect.bisect_right(restocks,issue)
                last=bisect.bisect_right(restocks,issue+BACKTEST_WINDOW)
                truth=restocks[first:last]
                ambiguous_count=(bisect.bisect_right(ambiguous,issue+BACKTEST_WINDOW)-
                                 bisect.bisect_right(ambiguous,issue))
                c["actual_observed_restocks"]+=len(truth)
                c["ambiguous_threshold_crossings"]+=ambiguous_count
                c["issued_four_hour_cohorts"]+=1
                evidence=phases.asof() if cursor else None
                if cursor:
                    forecast=predict_events(item,evidence,asof=issue,
                                            horizon=BACKTEST_WINDOW)
                    proposals=[x["predicted_restock_epoch"]
                               for x in forecast["restock_events"]
                               if issue<x["predicted_restock_epoch"]<=issue+BACKTEST_WINDOW]
                    statuses[forecast["status"]]+=1
                else:
                    proposals=[]
                    statuses["NO_PRIOR_STOCK_HISTORY"]+=1
                results=match_events(proposals,truth,tolerance=tolerance)
                # Tight timing is indispensable for fast Japan-style sellouts;
                # coarse +/-10 minute matches must not be sold as precision.
                c["matched_within_15s"]+=match_events(
                    proposals,truth,tolerance=15)["matched"]
                c["matched_within_60s"]+=match_events(
                    proposals,truth,tolerance=60)["matched"]
                for key,value in results.items():
                    c[key]+=value
                c["predicted_restock_events"]+=len(proposals)
                for window,stats in challengers.items():
                    if evidence is None:
                        alternative=[]
                        challenger_statuses[window]["NO_PRIOR_STOCK_HISTORY"]+=1
                    else:
                        attempt=predict_events(item,evidence,asof=issue,
                            horizon=BACKTEST_WINDOW,recent_cycles=window)
                        alternative=[v["predicted_restock_epoch"]
                            for v in attempt["restock_events"]
                            if issue<v["predicted_restock_epoch"]<=issue+BACKTEST_WINDOW]
                        challenger_statuses[window][attempt["status"]]+=1
                    strict15=match_events(alternative,truth,tolerance=15)
                    strict60=match_events(alternative,truth,tolerance=60)
                    broad=match_events(alternative,truth,tolerance=tolerance)
                    stats["events"]+=len(alternative)
                    stats["matched15"]+=strict15["matched"]
                    stats["matched60"]+=strict60["matched"]
                    stats["matched"]+=broad["matched"]
            all_results[item]={
                "cohorts":c["issued_four_hour_cohorts"],
                "observed_restocks":c["actual_observed_restocks"],
                "forecast_restocks":c["predicted_restock_events"],
                "matched_timing":c["matched"],
                "missed_observed_restocks":c["missed_actual"],
                "unmatched_forecasts":c["false_predicted"],
                "matched_within_15s":c["matched_within_15s"],
                "matched_within_60s":c["matched_within_60s"],
                "recall_within_15s":(
                    round(c["matched_within_15s"]/c["actual_observed_restocks"],4)
                    if c["actual_observed_restocks"] else None),
                "recall_within_60s":(
                    round(c["matched_within_60s"]/c["actual_observed_restocks"],4)
                    if c["actual_observed_restocks"] else None),
                "restock_recall":(
                    round(c["matched"]/c["actual_observed_restocks"],4)
                    if c["actual_observed_restocks"] else None),
                "restock_precision":(
                    round(c["matched"]/c["predicted_restock_events"],4)
                    if c["predicted_restock_events"] else None),
                "matched_median_absolute_error_seconds":None,
                "matched_mean_absolute_error_seconds":(
                    round(c["sum_absolute_timing_error_seconds"]/c["matched"],1)
                    if c["matched"] else None),
                "ambiguous_crossings_excluded":c["ambiguous_threshold_crossings"],
                "forecast_statuses":dict(statuses),
                "recent_cycle_challengers":{
                    f"recent_{window}":{
                        "forecast_restocks":stats["events"],
                        "matched_within_15s":stats["matched15"],
                        "matched_within_60s":stats["matched60"],
                        "matched_timing":stats["matched"],
                        "observed_restocks":c["actual_observed_restocks"],
                        "recall_within_15s":round(stats["matched15"]/
                            c["actual_observed_restocks"],4) if c["actual_observed_restocks"] else None,
                        "recall_within_60s":round(stats["matched60"]/
                            c["actual_observed_restocks"],4) if c["actual_observed_restocks"] else None,
                        "restock_recall":round(stats["matched"]/
                            c["actual_observed_restocks"],4) if c["actual_observed_restocks"] else None,
                        "restock_precision":round(stats["matched"]/
                            stats["events"],4) if stats["events"] else None,
                        "forecast_statuses":dict(challenger_statuses[window]),
                    } for window,stats in challengers.items()
                },
            }
            if progress is not None:
                progress(item,len(all_results),limit_items)
    matched=sum(v["matched_timing"] for v in all_results.values())
    actual=sum(v["observed_restocks"] for v in all_results.values())
    projected=sum(v["forecast_restocks"] for v in all_results.values())
    hits15=sum(v["matched_within_15s"] for v in all_results.values())
    hits60=sum(v["matched_within_60s"] for v in all_results.values())
    variant_totals={}
    for window in cycle_windows:
        sub=[v["recent_cycle_challengers"][f"recent_{window}"]
             for v in all_results.values()]
        match15=sum(v["matched_within_15s"] for v in sub)
        match60=sum(v["matched_within_60s"] for v in sub)
        match=sum(v["matched_timing"] for v in sub)
        forecasted=sum(v["forecast_restocks"] for v in sub)
        variant_totals[f"recent_{window}"]={
            "observed_restocks":actual,"forecast_restocks":forecasted,
            "matched_within_15s":match15,"matched_within_60s":match60,
            "matched_timing":match,
            "recall_within_15s":round(match15/actual,4) if actual else None,
            "recall_within_60s":round(match60/actual,4) if actual else None,
            "restock_recall":round(match/actual,4) if actual else None,
            "restock_precision":round(match/forecasted,4) if forecasted else None,
        }
    return {
        "status":"V163_HISTORICAL_ASOF_EVENT_REPLAY_NOT_GENUINE_LIVE_ISSUANCE",
        "asof_epoch":now,"window_days":days,
        "cohort_spacing_seconds":BACKTEST_WINDOW,
        "timing_tolerance_seconds":tolerance,
        "items":all_results,"items_evaluated":len(all_results),
        "actual_observed_restocks":actual,
        "predicted_events":projected,"matched_timing":matched,
        "matched_within_15s":hits15,"matched_within_60s":hits60,
        "recall_within_15s":round(hits15/actual,4) if actual else None,
        "recall_within_60s":round(hits60/actual,4) if actual else None,
        "restock_recall":round(matched/actual,4) if actual else None,
        "restock_precision":round(matched/projected,4) if projected else None,
        "recent_cycle_challengers":variant_totals,
        "recent_cycle_windows_tested":list(cycle_windows),
        "not_live_forward_validation":True,
        "not_five_minute_replanning":True,
        "lookahead_used_in_prediction":False,
        "collector_written":False,
        "private_ledgers_written":False,
    }


def format_replay(result):
    output=[
        "V163 HISTORICAL REPLAY, NOT LIVE FORWARD ACCURACY",
        f"Past {result['window_days']} days; fixed 4h issuance cohorts; "
        f"event match within +/-{result['timing_tolerance_seconds']//60} min",
        f"Observed clean restocks={result['actual_observed_restocks']}; "
        f"predicted events={result['predicted_events']}; "
        f"matched={result['matched_timing']}",
        f"Observed-event recall within 15s={result['recall_within_15s']}, "
        f"within 60s={result['recall_within_60s']}, "
        f"within +/-{result['timing_tolerance_seconds']//60}m={result['restock_recall']}.",
        "ALL recall denominators include every clean observed restock in scored windows.",
        f"Forecast-event precision={result['restock_precision']} "
        f"(denominator ALL projected events within cohorts)",
        "Neither value is departure-success accuracy; no winner is promoted.",
        "",
        f"{'ITEM':<27} {'ACTUAL':>6} {'PRED':>6} {'MATCH':>6} "
        f"{'RECALL':>8} {'PRECISION':>9}  PRIMARY REASONS",
        "-"*108,
    ]
    for key,v in sorted(result["items"].items()):
        out=sorted(v["forecast_statuses"].items(),
                   key=lambda x:-x[1])[:2]
        output.append(
            f"{key[:27]:<27} {v['observed_restocks']:>6} "
            f"{v['forecast_restocks']:>6} {v['matched_timing']:>6} "
            f"{str(v['restock_recall']):>8} {str(v['restock_precision']):>9}  "
            +", ".join(f"{a}={b}" for a,b in out))
    if result.get("recent_cycle_challengers"):
        output+=["","CAUSAL CYCLE-HISTORY TOURNAMENT (SAME RESTOCKS AND 4-HOUR COHORTS)",
                 "Research-only comparison; no champion or thresholds selected from this data.",
                 f"{'POLICY':<14} {'ACTUAL':>7} {'PREDICTED':>10} {'MATCHED':>8} "
                 f"{'RECALL15s':>10} {'RECALL60s':>10} {'RECALL10m':>10} {'PRECISION10m':>14}"]
        baseline={
            "observed_restocks":result["actual_observed_restocks"],
            "forecast_restocks":result["predicted_events"],
            "matched_timing":result["matched_timing"],
            "recall_within_15s":result["recall_within_15s"],
            "recall_within_60s":result["recall_within_60s"],
            "restock_recall":result["restock_recall"],
            "restock_precision":result["restock_precision"],
        }
        for name,r in (("all_history",baseline),
                       *sorted(result["recent_cycle_challengers"].items())):
            output.append(
                f"{name:<14} {r['observed_restocks']:>7} "
                f"{r['forecast_restocks']:>10} {r['matched_timing']:>8} "
                f"{str(r['recall_within_15s']):>10} "
                f"{str(r['recall_within_60s']):>10} "
                f"{str(r['restock_recall']):>10} "
                f"{str(r['restock_precision']):>14}"
            )
        for key in ("jap:Xanax","uni:Nessie Plushie"):
            if key in result["items"]:
                row=result["items"][key]
                output.append(f"{key} comparison: all={row['restock_recall']} "+
                    " ".join(f"{name}={r['restock_recall']}"
                    for name,r in sorted(row["recent_cycle_challengers"].items())))
    return "\n".join(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours",type=int,default=8)
    parser.add_argument("--source",type=Path,default=COLLECTOR,
                        help="Existing SQLite stock history or sanitized research snapshot")
    parser.add_argument("--json",action="store_true")
    parser.add_argument("--historical-replay-days",type=int,default=None)
    parser.add_argument("--limit-items",type=int,default=24)
    parser.add_argument("--compare-recent",action="store_true",
                        help="Research only: score recent 8/16/32 cycle variants versus unchanged V163 baseline")
    args=parser.parse_args()
    if not 1<=args.hours<=8:
        parser.error("horizon must be 1-8 hours")
    if args.historical_replay_days is not None:
        def progress(item,done,total):
            print(f"V163 replay processed {done}/{total} items: {item}",
                  file=sys.stderr,flush=True)
        result=replay_events(source=args.source,days=args.historical_replay_days,
                             limit_items=args.limit_items,progress=progress,
                             cycle_windows=(8,16,32) if args.compare_recent else ())
        print(json.dumps(result,sort_keys=True) if args.json else
              format_replay(result))
    else:
        result=forecast_all(source=args.source,horizon=args.hours*3600)
        print(json.dumps(result,sort_keys=True) if args.json else format_report(result))


if __name__=="__main__":
    main()
