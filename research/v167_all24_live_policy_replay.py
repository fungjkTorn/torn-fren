"""V167 all-24 event-driven live-policy replay and V2 telemetry.

This is a research replay of the intended beta operating contract:
- exact 24-item roster
- current best-known per-item route
- decisions recomputed every five minutes
- NO product 8-hour lookahead rule
- forecast forward by RESTOCK EVENTS until the first reachable event is found
- preserve V2 lifecycle telemetry at every issue
- score sealed future truth only after the causal decision is made

Some recovered legacy specialist wrappers contain an 8h MAX_WAIT. V167 treats
that as a local/direct specialist advice horizon only, not the system's future
event horizon. A causal event projector carries the item's observed cycle
process farther forward; whenever direct specialist advice exists it is kept
as the item's local model advice and compared/aligned to the selected event.

Defensive bounds (MAX_EVENTS / MAX_LOOKAHEAD_DAYS) prevent runaway compute;
they are not product recommendation horizons.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.japan_xanax.renewal_shadow import History, rate_plan, source_data
from research.plushie_champions.common import TRAVEL_SECONDS, STEP, GRACE
from research.quantity_rate_cycles import QuantityRateCycles
from deploy.scripts.v163_readonly_event_first_preview import OBS
from research.v164_evidence_routed_earliest_restock import (
    ROUTES as V164_ROUTES, _truth_rows, _clean_windows, _earliest_reachable_window,
)
from research.v166_seven_specialist_earliest_replay import (
    CausalMirror, specialist_plan as seven_specialist_plan,
    SEVEN, MODEL_FREEZE_EPOCH,
)
from research.matched_champion_audit import native_plan
from research.v145_provider_continuous_phases import provider_continuous_phases

MAX_EVENTS=512
MIN_QTY=30

# This is the current beta route we actually intend to test.
# Japan Xanax is deliberately included with its best current challenger instead
# of disappearing from the replay; it remains flagged weak until it proves out.
ROUTES={k:dict(v) for k,v in V164_ROUTES.items()}
ROUTES["jap:Xanax"]={
    "primary":"rate_current_quarter",
    "challenger":None,
    "rationale":"best current available challenger; deployment readiness unproven",
}


def _ro(path):
    p=Path(path).expanduser().resolve(strict=True)
    db=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=30)
    db.execute("PRAGMA query_only=ON")
    return db


# sqlite3 imported lazily in several helpers to keep module import cheap.
import sqlite3


def _crosses(gaps,a,b):
    for start,end in gaps:
        if start>b: break
        if start<=b and (end is None or end>=a):
            return True
    return False


def _cycles(rows,gaps,asof):
    """Clean >=30 lifecycle cycles available causally at asof."""
    rows=[r for r in rows if r[0]<=asof]
    cycles=[]
    prev=None
    restock=None
    peak=None
    excluded=0
    last_restock=None
    for t,q,provider in rows:
        if prev is not None:
            pt,pq,pp=prev
            broken=(provider!=pp or _crosses(gaps,pt,t))
            if broken:
                if restock is not None: excluded+=1
                restock=peak=None
            elif pq<MIN_QTY<=q:
                restock=t;peak=q
            elif restock is not None and q>=MIN_QTY:
                peak=max(peak or q,q)
            elif pq>=MIN_QTY>q and restock is not None:
                cycles.append({
                    "restock":restock,"depletion":t,
                    "stocked_lifetime":t-restock,
                    "batch_size":peak,
                    "restock_interval":(
                        restock-last_restock if last_restock is not None else None),
                })
                last_restock=restock
                restock=peak=None
        prev=(t,q,provider)
    return cycles,excluded


def _mean(xs):
    return sum(xs)/len(xs) if xs else None


def lifecycle_telemetry(rows,gaps,asof):
    """V2-compatible lifecycle statistics from evidence <= asof only."""
    cycles,excluded=_cycles(rows,gaps,asof)
    times=[r[0] for r in rows]
    i=bisect.bisect_right(times,asof)-1
    last=rows[i] if i>=0 else None
    lifetimes=[c["stocked_lifetime"] for c in cycles if c["stocked_lifetime"]>0]
    intervals=[c["restock_interval"] for c in cycles if c["restock_interval"]]
    batches=[c["batch_size"] for c in cycles if c["batch_size"] is not None]

    # V2 zero->restock wait: find clean >=30 losses followed by next >=30 restock.
    waits=[]
    last_depletion=None
    last_restock=None
    prev=None
    zero_anchor=None
    for t,q,p in rows:
        if t>asof: break
        if prev is not None:
            pt,pq,pp=prev
            if p!=pp or _crosses(gaps,pt,t):
                zero_anchor=None
            elif pq>=MIN_QTY>q:
                last_depletion=t
                zero_anchor=t
            elif pq<MIN_QTY<=q:
                last_restock=t
                if zero_anchor is not None and t>zero_anchor:
                    waits.append(t-zero_anchor)
                zero_anchor=None
        prev=(t,q,p)

    phase=None;phase_start=None
    if last is not None:
        high=last[1]>=MIN_QTY
        phase="STOCKED" if high else "DEPLETED"
        # walk backwards to the last threshold change in this same clean segment
        j=i
        phase_start=rows[j][0]
        while j>0:
            a,b=rows[j-1],rows[j]
            if b[2]!=a[2] or _crosses(gaps,a[0],b[0]):
                break
            if (a[1]>=MIN_QTY)!=(b[1]>=MIN_QTY):
                phase_start=b[0]
                break
            phase_start=a[0];j-=1

    return {
        "asof_epoch":asof,
        "current_quantity":last[1] if last else None,
        "current_phase":phase,
        "current_phase_started_epoch":phase_start,
        "current_phase_age_seconds":asof-phase_start if phase_start else None,
        "last_observation_epoch":last[0] if last else None,
        "last_restock_epoch":last_restock,
        "last_depletion_epoch":last_depletion,
        "avg_stocked_lifetime_seconds":_mean(lifetimes),
        "median_stocked_lifetime_seconds":statistics.median(lifetimes) if lifetimes else None,
        "avg_zero_to_restock_seconds":_mean(waits),
        "median_zero_to_restock_seconds":statistics.median(waits) if waits else None,
        "avg_restock_interval_seconds":_mean(intervals),
        "median_restock_interval_seconds":statistics.median(intervals) if intervals else None,
        "avg_batch_size":_mean(batches),
        "median_batch_size":statistics.median(batches) if batches else None,
        "valid_cycles":len(cycles),
        "excluded_cycles":excluded,
    }


def _q(values,p):
    if not values:return None
    values=sorted(int(v) for v in values if v>0)
    if not values:return None
    return values[max(0,min(len(values)-1,math.ceil(len(values)*p)-1))]


def project_events(item,phases,asof,*,max_events=MAX_EVENTS):
    """Event-driven causal cycle projection with no product time horizon.

    max_events is only a runaway-compute guard. It is not a time horizon and
    does not suppress a reachable event merely because it is days away.
    """
    high=list(phases.get("stocked_durations") or [])
    low=list(phases.get("depleted_durations") or [])
    phase=phases.get("phase")
    onset=phases.get("phase_onset")
    if phase not in ("HIGH","LOW") or not isinstance(onset,int):
        return []
    if min(len(high),len(low))<3:
        return []

    high_med=int(statistics.median(high));low_med=int(statistics.median(low))
    high_early=_q(high,.25) or high_med
    high_late=_q(high,.75) or high_med
    low_early=_q(low,.25) or low_med
    low_late=_q(low,.75) or low_med
    age=max(0,asof-onset)
    active=high if phase=="HIGH" else low
    survivors=[x-age for x in active if x>age]
    if not survivors:return []
    residual=int(statistics.median(survivors))

    if phase=="LOW":
        first=asof+residual
    else:
        first=asof+residual+low_med

    flight=TRAVEL_SECONDS[item.split(":",1)[0]]
    events=[]
    restock=first
    for idx in range(max_events):
        stocked_end=restock+high_med
        earliest_depart=max(asof,restock-flight-GRACE)
        arrival=earliest_depart+flight+GRACE
        reachable=(arrival>=restock and arrival<stocked_end)
        events.append({
            "event_index":idx+1,
            "predicted_restock_epoch":restock,
            "predicted_depletion_epoch":stocked_end,
            "predicted_restock_early_epoch":restock-(low_med-low_early),
            "predicted_restock_late_epoch":restock+(low_late-low_med),
            "predicted_stocked_lifetime_seconds":high_med,
            "earliest_departure_epoch":earliest_depart if reachable else None,
            "predicted_arrival_epoch":arrival if reachable else None,
            "reachable":reachable,
        })
        restock+=high_med+low_med
    return events


def first_reachable(events):
    return next((e for e in events if e["reachable"]),None)


def generic_plan(source,key,issued,mode):
    rows,polls,crosses,_,cutoff=source_data(source,now=issued,item_key=key)
    h=History(crosses);rate=QuantityRateCycles(crosses)
    for row in rows:
        h.add(row);rate.add(OBS(*row))
    i=bisect.bisect_right(polls,issued)-1
    age=issued-polls[i] if i>=0 else None
    flight=TRAVEL_SECONDS[key.split(":",1)[0]]
    selected=h.plans(issued,poll_age=age,flight_seconds=flight)
    selected["rate_current_quarter"]=rate_plan(rate,key,issued,age)
    p=selected.get(mode)
    return {
        "status":p.get("status") if p else "MODE_UNAVAILABLE",
        "departure":p.get("departure") if p else None,
        "source_cutoff":cutoff,
    }


def routed_local_plan(causal_db,source,key,issued):
    mode=ROUTES[key]["primary"]
    if mode=="specialist_control":
        if key in SEVEN:
            r=seven_specialist_plan(causal_db,key,issued)
            return dict(model=mode,status=r.get("status"),departure=r.get("departure"))
        r=native_plan(causal_db,key,issued,timeout=30)
        return dict(model=mode,status=r.get("status"),departure=r.get("departure"))
    r=generic_plan(source,key,issued,mode)
    return dict(model=mode,status=r.get("status"),departure=r.get("departure"))


def score_decision(source,key,issued,departure,truth_cutoff):
    flight=TRAVEL_SECONDS[key.split(":",1)[0]]
    rows,gaps=_truth_rows(source,key,truth_cutoff)
    target=_earliest_reachable_window(rows,gaps,issued,flight,truth_cutoff)
    result={"actual_target_status":target["status"]}
    if departure is None:return result
    arrival=departure+flight
    evidence=source_data(source,now=truth_cutoff,item_key=key)[3]
    state=evidence.score(arrival)[0]
    result.update(arrival_epoch=arrival,arrival_state=state)
    if target["status"]=="EARLIEST_REACHABLE_FOUND":
        result.update(
            actual_target_restock_epoch=target["restock"],
            actual_target_depletion_epoch=target["depletion"],
            oracle_earliest_departure_epoch=target["oracle_earliest_departure"],
            departure_minus_oracle_seconds=departure-target["oracle_earliest_departure"],
            arrival_minus_actual_restock_seconds=arrival-target["restock"],
        )
    return result


def replay_item(*,source,key,start,end,workdir):
    if key not in ROUTES:raise ValueError("not in all24 route")
    truth_cutoff=source_data(source,item_key=key)[4]
    max_flight=max(TRAVEL_SECONDS.values())
    if end+max_flight+GRACE>truth_cutoff:
        raise ValueError("immature replay end")

    scratch=Path(workdir)/(key.replace(":","__").replace(" ","_")+".sqlite")
    mirror=CausalMirror(source,scratch,start)
    truth_rows,truth_gaps=_truth_rows(source,key,truth_cutoff)
    issue_rows,_,_,_,_=source_data(source,now=end,item_key=key)
    # use truth gap boundaries but only phases built from <=issue rows later
    records=[]
    previous_target=None
    try:
        for issued in range(start,end+1,STEP):
            mirror.advance(issued)
            causal_rows=[r for r in issue_rows if r[0]<=issued]
            # Build causal phase model from only visible rows.
            with closing(sqlite3.connect(scratch.as_uri()+"?mode=ro",uri=True)) as db:
                db.execute("PRAGMA query_only=ON")
                gaps=db.execute("SELECT start_timestamp,end_timestamp FROM collection_gaps ORDER BY start_timestamp").fetchall()
            from research.v128_full24_earliest_shadow import _gap_index
            phases=provider_continuous_phases(
                [OBS(*r) for r in causal_rows],asof=issued,
                gaps=gaps)
            events=project_events(key,phases,issued)
            target=first_reachable(events)
            local=routed_local_plan(scratch,source,key,issued)

            # Live policy target: first reachable projected event. Local model
            # advice is retained as a refinement when it points into that event.
            dep=target["earliest_departure_epoch"] if target else None
            local_dep=local.get("departure")
            aligned=False
            if target and local_dep is not None:
                local_arr=local_dep+TRAVEL_SECONDS[key.split(":",1)[0]]+GRACE
                if target["predicted_restock_epoch"]<=local_arr<target["predicted_depletion_epoch"]:
                    dep=local_dep
                    aligned=True

            telemetry=lifecycle_telemetry(causal_rows,gaps,issued)
            scored=score_decision(source,key,issued,dep,truth_cutoff)
            target_id=(target["event_index"],target["predicted_restock_epoch"]) if target else None
            stable=(previous_target is not None and target_id==previous_target)
            records.append({
                "item_key":key,"issued_epoch":issued,
                "route_model":ROUTES[key]["primary"],
                "route_status":local.get("status"),
                "local_model_departure_epoch":local_dep,
                "local_model_aligned_to_selected_event":aligned,
                "selected_event":target,
                "recommended_departure_epoch":dep,
                "target_stable_from_previous_replan":stable,
                "event_count_projected":len(events),
                "lifecycle":telemetry,
                **scored,
            })
            previous_target=target_id
    finally:
        try:scratch.unlink()
        except OSError:pass

    c=Counter()
    dep_errors=[];restock_errors=[]
    for r in records:
        c["issues"]+=1
        if r["recommended_departure_epoch"] is None:
            c["abstain"]+=1;continue
        c["proposals"]+=1
        if r.get("arrival_state") in ("SUCCESS","FAILURE"):
            c["arrival_known"]+=1
            c["arrival_success"]+=int(r["arrival_state"]=="SUCCESS")
        if r.get("actual_target_restock_epoch") is not None:
            c["earliest_target_scored"]+=1
            arr=r["arrival_epoch"]+GRACE
            ok=(arr>=r["actual_target_restock_epoch"] and
                (r["actual_target_depletion_epoch"] is None or arr<r["actual_target_depletion_epoch"]))
            c["earliest_target_hit"]+=int(ok)
            dep_errors.append(r["departure_minus_oracle_seconds"])
            restock_errors.append(r["selected_event"]["predicted_restock_epoch"]-r["actual_target_restock_epoch"])
        c["stable_replans"]+=int(r["target_stable_from_previous_replan"])
        c["local_aligned"]+=int(r["local_model_aligned_to_selected_event"])

    return {
        "item_key":key,"route":ROUTES[key],"start":start,"end":end,
        "counts":dict(c),
        "arrival_success_fraction":c["arrival_success"]/c["arrival_known"] if c["arrival_known"] else None,
        "earliest_target_hit_fraction":c["earliest_target_hit"]/c["earliest_target_scored"] if c["earliest_target_scored"] else None,
        "proposal_coverage":c["proposals"]/c["issues"] if c["issues"] else None,
        "mean_departure_minus_oracle_seconds":_mean(dep_errors),
        "median_departure_minus_oracle_seconds":statistics.median(dep_errors) if dep_errors else None,
        "mean_predicted_minus_actual_restock_seconds":_mean(restock_errors),
        "median_predicted_minus_actual_restock_seconds":statistics.median(restock_errors) if restock_errors else None,
        "records":records,
        "product_horizon_type":"EVENT_DRIVEN_FIRST_REACHABLE",
        "product_time_horizon_seconds":None,
        "defensive_max_events":MAX_EVENTS,
        "defensive_time_horizon_seconds":None,
        "production_modified":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--item-key",required=True,choices=tuple(sorted(ROUTES)))
    p.add_argument("--start-epoch",required=True,type=int)
    p.add_argument("--end-epoch",required=True,type=int)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    if a.start_epoch<MODEL_FREEZE_EPOCH:
        raise SystemExit("V167 refuses pre-freeze evaluation")
    out=Path(a.output).expanduser().resolve();out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v167-") as td:
        result=replay_item(source=a.source,key=a.item_key,start=a.start_epoch,
                           end=a.end_epoch,workdir=td)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
        "item_key","arrival_success_fraction","earliest_target_hit_fraction",
        "proposal_coverage","mean_departure_minus_oracle_seconds",
        "mean_predicted_minus_actual_restock_seconds")},sort_keys=True))


if __name__=="__main__":
    main()
