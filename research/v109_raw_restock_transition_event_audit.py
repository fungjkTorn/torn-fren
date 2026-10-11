"""V109 raw-stock restock/depletion EVENT forecast evaluation (read-only).

Unlike departure-target V89-V108, evaluate a single causal prediction of each
distinct observed >=30 threshold transition against the NEXT actual threshold
transition of the same provider segment, with no collection-gap crossings.

At an observed depletion (>=30 -> below 30), predict the NEXT observed
restock-to->=30 timestamp using V107 trained ONLY on observations <= issue.
At an observed restock (below 30 -> >=30), predict the NEXT observed
depletion timestamp. Arrival times/flight decisions are downstream:
first establish meaningful predictive skill for the events themselves.

Use RAW stock_history with no full-timeline future-aware cleanup, and only
past observations for selecting event times. Future records are used only to
obtain the eventual event timestamp. Each event yields at most one score.
Events with provider switches, collection gaps, missing initial state,
missing future transition, or short (<300s) bounces are excluded/reported.

The raw collector is change-only, not exact YATA country-update truth; provider
timestamps/freshness missing. Previously researched history is not a pristine
blind lockbox. No training, API, VM/live change, or production writes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.v60_private_snapshot_probe import approved_collector_source
from research.v107_explicit_restock_cycle_baseline import (
    StockObservation,next_windows
)
from research.plushie_champions.common import TRAVEL_SECONDS

SOURCE="/opt/torn-fren/data/stock_history.db"
TARGETS={
    "redfox":("uni","Red Fox Plushie"),
    "nessie":("uni","Nessie Plushie"),
}
MAX_EPISODES=60
MIN_PHASE_DURATION=300
MIN_HISTORY_DAYS=8
HOLDOUT_FRACTION=.25


def crossed_gap(intervals,low,high):
    return any(start<=high and (end is None or end>=low)
               for start,end in intervals)


def transition_episodes(observations,gaps=()):
    """Return completed single-provider stock/depletion phases, no hindsight
    score input. Each returned phase is bounded by 2 OBSERVED changes.
    """
    transitions=[]
    last_obs=None
    last_state=None
    segment=0
    for obs in observations:
        if (last_obs is not None and
            (obs.epoch<=last_obs.epoch or obs.source!=last_obs.source
             or crossed_gap(gaps,last_obs.epoch,obs.epoch))):
            segment+=1
            last_state=None
        state=obs.quantity>=30
        if last_state is not None and last_state!=state:
            transitions.append({
                "issue":obs.epoch,"issued_quantity":obs.quantity,
                "phase":"STOCKED" if state else "DEPLETED",
                "segment":segment,"source":obs.source})
        last_state=state
        last_obs=obs

    episodes=[]
    rejected=Counter()
    for prior,next_event in zip(transitions,transitions[1:]):
        if prior["segment"]!=next_event["segment"]:
            rejected["PROVIDER_OR_COLLECTION_GAP"]+=1
            continue
        duration=next_event["issue"]-prior["issue"]
        if duration<MIN_PHASE_DURATION:
            rejected["SHORT_TRANSITION_BOUNCE"]+=1
            continue
        episodes.append({
            **prior,"actual_next_transition":next_event["issue"],
            "phase_duration_seconds":duration,
            "actual_next_phase":next_event["phase"],
        })
    return episodes,rejected


def actual_forecast_boundary(prediction,phase):
    if prediction["status"]!="FORECAST_AVAILABLE":
        return None
    windows=prediction["windows"]
    if not windows:
        return None
    if phase=="DEPLETED":
        return windows[0]["expected_stocked_start"]
    if phase=="STOCKED":
        return windows[0]["expected_drop_below_30"]
    raise ValueError("unrecognized phase")


def _quantile(xs,f):
    if not xs:return None
    vals=sorted(xs)
    index=min(len(vals)-1,max(0,round((len(vals)-1)*f)))
    return round(vals[index],2)


def evaluate_events(obs,episodes,*,item_key,gaps=(),max_episodes=MAX_EPISODES):
    """Chronological last-quarter phase forecasts. No outcome-derived tuning."""
    if not 1<=max_episodes<=MAX_EPISODES:
        raise ValueError("event safety cap invalid")
    if not obs:
        return {"state":"NO_OBSERVATIONS"}
    first=obs[0].epoch
    cutoff=first+int((obs[-1].epoch-first)*(1-HOLDOUT_FRACTION))
    candidate=[e for e in episodes if (
        e["issue"]>=cutoff and
        e["issue"]>=first+MIN_HISTORY_DAYS*86400)]
    # Event-based uniform sampling, not neighboring 30-minute starts.
    if len(candidate)>max_episodes:
        import numpy as np
        indexes=np.linspace(0,len(candidate)-1,max_episodes,dtype=int)
        candidate=[candidate[int(i)] for i in sorted(set(indexes))]
    kinds=defaultdict(Counter)
    error_series=defaultdict(list)
    examples=[]
    for ep in candidate:
        issue=ep["issue"]
        # The FORECAST is run with its own exact as-of and sees only prior
        # event history; observation timestamps after issue are not input.
        past=[r for r in obs if r.epoch<=issue]
        prediction=next_windows(
            item_key,past,asof=issue,collection_gaps=gaps)
        phase=ep["phase"]
        c=kinds[phase]
        c["observed_completed_events"]+=1
        predicted=actual_forecast_boundary(prediction,phase)
        if predicted is None:
            c["not_forecastable"]+=1
            c["abstained_"+prediction["status"]]+=1
            continue
        actual=ep["actual_next_transition"]
        error=predicted-actual
        c["forecast_issued"]+=1
        if abs(error)<=300:c["within_5m"]+=1
        if abs(error)<=900:c["within_15m"]+=1
        if abs(error)<=1800:c["within_30m"]+=1
        if error<0:c["too_early"]+=1
        if error>0:c["too_late"]+=1
        errors=error_series[phase]
        errors.append(abs(error)/60)
        if len(examples)<8:
            examples.append({
                "phase":phase,"issued_epoch":issue,
                "actual_next_epoch":actual,
                "predicted_next_epoch":predicted,
                "error_minutes":round(error/60,1),
                "first_projected_window":prediction["windows"][0]
            })

    report={}
    for phase in ("DEPLETED","STOCKED"):
        c=kinds[phase]
        n=c["observed_completed_events"]
        f=c["forecast_issued"]
        errors=error_series[phase]
        report[phase]={
            "observed_completed_events":n,
            "forecasts_issued":f,
            "abstentions":c["not_forecastable"],
            "coverage_fraction":round(f/n,4) if n else None,
            "within_5m":c["within_5m"],
            "within_15m":c["within_15m"],
            "within_30m":c["within_30m"],
            "within_15m_among_forecast":round(c["within_15m"]/f,4)
                                          if f else None,
            "median_absolute_error_minutes":_quantile(errors,.5),
            "p75_absolute_error_minutes":_quantile(errors,.75),
            "too_early":c["too_early"],"too_late":c["too_late"],
            "abstention_reasons":{
                k.removeprefix("abstained_"):v
                for k,v in c.items() if k.startswith("abstained_")},
        }
    return {
        "item_key":item_key,
        "evaluation_cutoff_epoch":cutoff,
        "distinct_observed_phase_events_sampled":len(candidate),
        "phase_predictions":report,
        "examples":examples,
        "future_stock_used_in_prediction":False,
        "verified_country_provider_update_time":False,
        "independent_game_world_restock_proven":False,
    }


def read_collector_item(conn,country,item):
    raw=conn.execute(
        """SELECT timestamp,quantity,source FROM stock_history
           WHERE country=? AND lower(item_name)=lower(?)
           ORDER BY timestamp ASC,id ASC""",(country,item)).fetchall()
    observations=[StockObservation(int(t),int(q),str(src))
                  for t,q,src in raw
                  if t is not None and q is not None and src is not None
                  and int(q)>=0]
    gaps=[(int(a),int(b) if b is not None else None)
          for a,b in conn.execute(
              "SELECT start_timestamp,end_timestamp FROM collection_gaps")]
    return observations,gaps


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=["redfox","nessie","both"],
                   default="both")
    p.add_argument("--events",type=int,default=25)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not 1<=args.events<=MAX_EPISODES:
        p.error("events outside safe bounds")
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved collector path")
    targets=TARGETS if args.target=="both" else {
        args.target:TARGETS[args.target]}
    t0=time.monotonic()
    with closing(sqlite3.connect(
        Path(SOURCE).resolve(strict=True).as_uri()+"?mode=ro",
        uri=True,timeout=15)) as conn:
        conn.execute("PRAGMA query_only=ON")
        result={}
        for target,(country,item) in targets.items():
            obs,gaps=read_collector_item(conn,country,item)
            episodes,excluded=transition_episodes(obs,gaps)
            result[target]=evaluate_events(
                obs,episodes,item_key=f"{country}:{item}",gaps=gaps,
                max_episodes=args.events)
            result[target]["raw_stock_change_rows"]=len(obs)
            result[target]["completed_provider_continuous_phases"]=len(episodes)
            result[target]["excluded_phases"]=dict(excluded)
    report={
        "status":"V109_RAW_EVENT_LEVEL_RESTOCK_DEPLETION_TIMING_AUDIT",
        "read_only":True,"production_changed":False,
        "asof_no_lookahead_evaluation":True,
        "source_raw_no_future_cleaning":True,
        "holdout_previously_seen":True,
        "total_elapsed_seconds":round(time.monotonic()-t0,2),
        "items":result,
    }
    if args.json:
        print(json.dumps(report,sort_keys=True))
        return
    print("===== V109: RESTOCK/DEPLETION EVENT TIMING, NOT DEPARTURE-TARGET HITS =====")
    for name,info in result.items():
        print("====",name,info["item_key"],"====")
        print("raw stock-change rows:",info["raw_stock_change_rows"])
        print("continuous completed phases:",info[
            "completed_provider_continuous_phases"])
        print("event samples:",info["distinct_observed_phase_events_sampled"])
        print("transition exclusions:",json.dumps(info["excluded_phases"]))
        for phase,m in info["phase_predictions"].items():
            print(f'{phase:9} observed={m["observed_completed_events"]:3} '
                  f'issued={m["forecasts_issued"]:3} '
                  f'within15m={m["within_15m"]:3} '
                  f'median_error_m={m["median_absolute_error_minutes"]} '
                  f'p75_error_m={m["p75_absolute_error_minutes"]} '
                  f'abstentions={m["abstentions"]}')
            print("  abstention reasons:",json.dumps(m["abstention_reasons"]))
        print("example:",json.dumps(info["examples"][:1]))
    print("Source raw/no lookahead, provider update epoch unavailable; observed timestamps ≠ exact stock-change instants.")
    print("Elapsed:",report["total_elapsed_seconds"],"seconds")


if __name__=="__main__":
    main()
