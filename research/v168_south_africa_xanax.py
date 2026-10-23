"""V168 South Africa Xanax focused champion validation.

Purpose:
- validate the existing V19 dyn1 incumbent for sou:Xanax
- compare legitimate challengers on matched causal issue clocks
- score arrival >=30 and earliest-reachable-restock behavior using South Africa's
  real 11820-second flight
- preserve 5-minute replanning semantics
- no production changes

This is intentionally item-specific. It does not retrain on validation truth.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import statistics
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

from deploy.scripts.v163_readonly_event_first_preview import OBS, predict_events, _gap_index
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v164_evidence_routed_earliest_restock import (
    _truth_rows, _earliest_reachable_window,
)
from research.continuous_departure_replay import ArrivalEvidence
from research.quantity_rate_cycles import QuantityRateCycles
from research.true_zero_cycles import ZeroCycles
from research.plushie_champions.common import TRAVEL_SECONDS, STEP, GRACE
from research.v166_seven_specialist_earliest_replay import CausalMirror
from services.travel_decision_contract_v166 import build_item_travel_decision
from services.travel_window_policy import project_policy
from services.frozen_candidate_worker_v31 import _install_frozen_readonly_history

KEY="sou:Xanax"
COUNTRY="sou"
ITEM="Xanax"
FLIGHT=TRAVEL_SECONDS[COUNTRY]
MODEL_FREEZE_EPOCH=1791504000

# Existing registry incumbent plus serious alternatives.
V19_NAMES=tuple(f"dyn{i}" for i in range(1,14))
V20_NAMES=tuple(f"traj{i}" for i in range(1,15))
GENERIC_NAMES=("true_zero_expected","true_zero_bounded",
               "quantity_rate_expected","quantity_rate_bounded",
               "quantity_rate_quarter")
CANDIDATES=tuple("v19:"+x for x in V19_NAMES)+tuple(
    "v20:"+x for x in V20_NAMES)+GENERIC_NAMES


def _polls_gaps(source,cutoff):
    p=Path(source).resolve(strict=True)
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        polls=[int(r[0]) for r in db.execute(
            """SELECT timestamp FROM poll_heartbeats
               WHERE mode='poll-cycle' AND success=1 AND timestamp<=?
               ORDER BY timestamp""",(cutoff,)).fetchall()]
        gaps=db.execute(
            """SELECT start_timestamp,end_timestamp FROM collection_gaps
               WHERE start_timestamp<=? ORDER BY start_timestamp""",(cutoff,)).fetchall()
    return polls,gaps


def _event_candidates(rows,gaps,issued):
    phases=provider_continuous_phases(
        [OBS(*r) for r in rows if r[0]<=issued],asof=issued,gaps=gaps)
    f=predict_events(KEY,phases,asof=issued,horizon=None,max_events=64)
    out=[]
    current=f.get("current_stock_window")
    if isinstance(current,dict) and isinstance(current.get("expected_departure_epoch"),int):
        out.append((current["expected_departure_epoch"]-issued,0))
    for e in f.get("restock_events") or []:
        dep=e.get("expected_departure_epoch")
        if isinstance(dep,int) and dep>=issued:
            out.append((dep-issued,int(e.get("event_index") or 0)))
    return f,sorted(set(out))


def _dynamic_family(causal_db,issued,events,generation,names):
    """Score all frozen configs in one engine/context load for this issue."""
    if not events:return {name:None for name in names}
    from services import history_service
    _install_frozen_readonly_history(history_service,causal_db)
    if generation=="v19":
        from services import plushie_flower_dynamic_planner_v19 as engine
        cleaned,cycles,_bounces,gaps=engine.load_item(COUNTRY,ITEM,30)
        normalized=engine.normalize_gaps(history_service.get_collection_gaps())
        timeline=engine.Timeline(cleaned,cycles,30,gaps=normalized)
        deps,features=engine.completed_cycle_features(cycles,gaps=normalized)
    else:
        from services import plushie_flower_dynamic_planner_v20 as engine
        cleaned,cycles,_bounces,gaps=engine.load_item(COUNTRY,ITEM,30)
        normalized=engine.normalize_gaps(history_service.get_collection_gaps())
        timeline=engine.Timeline(cleaned,cycles,30,gaps=normalized)
        deps,features=engine.completed_cycle_features(cycles,gaps=normalized)
    cfgs={x.name:x for x in engine.configs()}
    points=engine.build_points(timeline,deps,features,600)
    if len(points)<60:return {name:None for name in names}
    times=[x.t for x in points]
    delays=[d for d,_ in events]
    result={}
    for name in names:
        cfg=cfgs.get(name)
        if cfg is None:
            result[name]=None;continue
        p=engine.plan(float(issued),points,times,timeline,deps,features,
                      cfg,delays,FLIGHT,GRACE)
        result[name]=int(p["departure_time"]) if p is not None else None
    return result
def _cycle_forecast(rows,gaps,issued,kind):
    crosses=_gap_index(gaps,issued)
    tracker=QuantityRateCycles(crosses) if kind.startswith("quantity_rate") else ZeroCycles(crosses)
    for r in rows:
        if r[0]>issued:break
        tracker.add(OBS(*r))
    forecast=tracker.forecast(KEY,asof=issued)
    if kind.endswith("bounded"):
        d=build_item_travel_decision(
            forecast,now=issued,poll_age_seconds=0,arrival_policy="bounded")
    elif kind.endswith("quarter"):
        d=project_policy(forecast,now=issued,poll_age_seconds=0,kind="current_quarter")
    else:
        d=build_item_travel_decision(
            forecast,now=issued,poll_age_seconds=0,arrival_policy="expected")
    return d.get("estimated_departure_epoch")


def issue_plans(causal_db,rows,gaps,issued,candidate_subset=None):
    forecast,events=_event_candidates(rows,gaps,issued)
    subset=set(CANDIDATES if candidate_subset is None else candidate_subset)
    out={}
    need_v19=[x.split(":",1)[1] for x in subset if x.startswith("v19:")]
    need_v20=[x.split(":",1)[1] for x in subset if x.startswith("v20:")]
    if need_v19:
        values=_dynamic_family(causal_db,issued,events,"v19",need_v19)
        out.update({"v19:"+k:v for k,v in values.items()})
    if need_v20:
        values=_dynamic_family(causal_db,issued,events,"v20",need_v20)
        out.update({"v20:"+k:v for k,v in values.items()})
    for name in subset:
        if name in GENERIC_NAMES:
            out[name]=_cycle_forecast(rows,gaps,issued,name)
    return out,forecast
def _score(dep,issued,truth_rows,truth_gaps,evidence,truth_cutoff):
    c=Counter()
    c["issues"]=1
    if dep is None:
        c["abstain"]=1
        return c,None,None
    c["proposals"]=1
    state=evidence.score(dep+FLIGHT)[0]
    c["arrival_"+state.lower()]+=1
    target=_earliest_reachable_window(
        truth_rows,truth_gaps,issued,FLIGHT,truth_cutoff)
    if target["status"]=="EARLIEST_REACHABLE_FOUND":
        c["earliest_scored"]+=1
        arr=dep+FLIGHT+GRACE
        hit=(arr>=target["restock"] and
             (target["depletion"] is None or arr<target["depletion"]))
        c["earliest_hit"]+=int(hit)
        return c,dep-target["oracle_earliest_departure"],dep+FLIGHT-target["restock"]
    return c,None,None


def _rank_summary(summary):
    return (
        summary["arrival_success_fraction"]
        if summary["arrival_success_fraction"] is not None else -1,
        summary["earliest_hit_fraction"]
        if summary["earliest_hit_fraction"] is not None else -1,
        summary["proposal_coverage"]
        if summary["proposal_coverage"] is not None else -1,
        summary["arrival_known"],
    )


def replay(*,source,start,end,output,screen_step=3600,finalists=4):
    source=Path(source).resolve(strict=True)
    if start<MODEL_FREEZE_EPOCH or end<=start:
        raise ValueError("invalid post-freeze window")
    with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        truth_cutoff=db.execute(
            """SELECT MAX(timestamp) FROM poll_heartbeats
               WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
    if truth_cutoff is None or end+FLIGHT+GRACE+180>truth_cutoff:
        raise ValueError("immature validation end")

    truth_rows,truth_gaps=_truth_rows(source,KEY,truth_cutoff)
    polls,_=_polls_gaps(source,truth_cutoff)
    evidence=ArrivalEvidence(
        [OBS(*r) for r in truth_rows],polls,truth_gaps,truth_cutoff)
    issue_rows=[r for r in truth_rows if r[0]<=end]

    # Stage A: broad frozen-config screen on hourly matched issue clocks.
    screen_issues=list(range(
        ((start+screen_step-1)//screen_step)*screen_step,end+1,screen_step))
    split=max(1,int(len(screen_issues)*.60))
    dev_issues=screen_issues[:split]
    val_hourly=screen_issues[split:]
    stats={name:Counter() for name in CANDIDATES}
    dep_errors={name:[] for name in CANDIDATES}
    arr_errors={name:[] for name in CANDIDATES}

    with tempfile.TemporaryDirectory(prefix="v168-sou-xanax-") as td:
        scratch=Path(td)/"causal.sqlite"
        mirror=CausalMirror(source,scratch,dev_issues[0])
        for n,issued in enumerate(dev_issues,1):
            mirror.advance(issued)
            visible=[r for r in issue_rows if r[0]<=issued]
            with closing(sqlite3.connect(scratch.as_uri()+"?mode=ro",uri=True)) as db:
                cgaps=db.execute(
                    "SELECT start_timestamp,end_timestamp FROM collection_gaps ORDER BY start_timestamp"
                ).fetchall()
            plans,_=issue_plans(scratch,visible,cgaps,issued)
            for name in CANDIDATES:
                sc,de,ae=_score(plans.get(name),issued,truth_rows,truth_gaps,evidence,truth_cutoff)
                stats[name].update(sc)
                if de is not None:dep_errors[name].append(de)
                if ae is not None:arr_errors[name].append(ae)
            if n%12==0:
                print(json.dumps({"status":"V168_SCREEN_PROGRESS",
                                  "issues_done":n,"issues_total":len(dev_issues)}),flush=True)

        def summary(name,c,dep,arr):
            known=c["arrival_success"]+c["arrival_failure"]
            return {
                "issues":c["issues"],"proposals":c["proposals"],
                "proposal_coverage":c["proposals"]/c["issues"] if c["issues"] else None,
                "arrival_known":known,
                "arrival_success_fraction":c["arrival_success"]/known if known else None,
                "earliest_scored":c["earliest_scored"],
                "earliest_hit_fraction":c["earliest_hit"]/c["earliest_scored"] if c["earliest_scored"] else None,
                "median_departure_minus_oracle_seconds":statistics.median(dep) if dep else None,
                "median_arrival_minus_actual_restock_seconds":statistics.median(arr) if arr else None,
                "counts":dict(c),
            }

        dev_rows=[]
        for name in CANDIDATES:
            dev_rows.append({"candidate":name,"development":summary(
                name,stats[name],dep_errors[name],arr_errors[name])})
        ranked=sorted(dev_rows,key=lambda x:_rank_summary(x["development"]),reverse=True)
        chosen=[x["candidate"] for x in ranked[:finalists]]
        if "v19:dyn1" not in chosen:
            chosen[-1]="v19:dyn1"
        chosen=tuple(dict.fromkeys(chosen))

        # Stage B: untouched later 40%, every five minutes, finalists only.
        if not val_hourly:
            raise ValueError("validation split empty")
        val_start=val_hourly[0]
        validation_issues=list(range(val_start,end+1,STEP))
        vst={name:Counter() for name in chosen}
        vdep={name:[] for name in chosen}
        varr={name:[] for name in chosen}
        mirror.advance(val_start)
        for n,issued in enumerate(validation_issues,1):
            mirror.advance(issued)
            visible=[r for r in issue_rows if r[0]<=issued]
            with closing(sqlite3.connect(scratch.as_uri()+"?mode=ro",uri=True)) as db:
                cgaps=db.execute(
                    "SELECT start_timestamp,end_timestamp FROM collection_gaps ORDER BY start_timestamp"
                ).fetchall()
            plans,_=issue_plans(scratch,visible,cgaps,issued,candidate_subset=chosen)
            for name in chosen:
                sc,de,ae=_score(plans.get(name),issued,truth_rows,truth_gaps,evidence,truth_cutoff)
                vst[name].update(sc)
                if de is not None:vdep[name].append(de)
                if ae is not None:varr[name].append(ae)
            if n%48==0:
                print(json.dumps({"status":"V168_VALIDATION_PROGRESS",
                                  "issues_done":n,"issues_total":len(validation_issues),
                                  "finalists":chosen}),flush=True)

    validation=[]
    for name in chosen:
        validation.append({"candidate":name,"validation":summary(
            name,vst[name],vdep[name],varr[name])})
    winner=max(validation,key=lambda x:_rank_summary(x["validation"]))
    result={
        "status":"V168_SOUTH_AFRICA_XANAX_TWO_STAGE_CAUSAL_VALIDATION",
        "item_key":KEY,"flight_seconds":FLIGHT,
        "start":start,"end":end,"truth_cutoff":truth_cutoff,
        "screen_issue_step_seconds":screen_step,
        "validation_issue_step_seconds":STEP,
        "selection_rule":"broad screen first60pct; finalist validation last40pct every5m",
        "historical_incumbent":{
            "candidate":"v19:dyn1",
            "old_development_success_fraction":143/152,
            "old_hits":143,"old_starts":152,
        },
        "screen_ranking":ranked,
        "finalists":list(chosen),
        "validation":validation,
        "winner_on_untouched_validation":winner["candidate"],
        "winner_validation":winner["validation"],
        "actual_player_flights":False,
        "production_modified":False,
        "validation_not_used_for_screen_selection":True,
    }
    Path(output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "winner":result["winner_on_untouched_validation"],
        "validation":result["winner_validation"],
        "finalists":result["finalists"],
        "output":str(Path(output).resolve()),
    },sort_keys=True))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--start-epoch",type=int)
    p.add_argument("--end-epoch",type=int)
    p.add_argument("--days",type=int,default=7)
    p.add_argument("--screen-step",type=int,default=3600)
    p.add_argument("--finalists",type=int,default=4)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    source=Path(a.source).resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as db:
        cutoff=db.execute(
            """SELECT MAX(timestamp) FROM poll_heartbeats
               WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
    end=a.end_epoch if a.end_epoch is not None else int(cutoff)-FLIGHT-GRACE-180
    start=a.start_epoch if a.start_epoch is not None else max(MODEL_FREEZE_EPOCH,end-a.days*86400)
    if a.screen_step not in (1800,3600,7200):
        raise SystemExit("screen-step must be 1800, 3600 or 7200")
    if not 2<=a.finalists<=6:
        raise SystemExit("finalists must be 2..6")
    replay(source=source,start=start,end=end,output=a.output,
           screen_step=a.screen_step,finalists=a.finalists)


if __name__=="__main__":
    main()
