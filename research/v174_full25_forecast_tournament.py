"""V174: ACTUAL causal 25-item forecasting-model tournament.

Unlike V173, this rebuilds V18/V19/V20 engine contexts and scores their
historical neighbors and event-derived departures at each issue clock.
CausalMirror contains no observations later than each issuance. Time-based
recency challengers restrict model training points to preceding 2 or 5 days.
Completed-cycle zero/rate forecasters test last 6, 10 and 20 cycles.
The V169 as-issued champion remains the matched, untouched control.

Screen: earliest 60% at 1-hour cadence across frozen engine configurations.
Validation: final 40%, full 300-second cadence, selected finalists and
V169 incumbent, with real simulated executable departures and no promotion
based on five-minute proposal success alone. The screen choice is frozen
before the independent validation period.

This can take hours on a PC. A separate JSON checkpoint is saved for each
completed item. Read-only sanitized data; NO VM, site, collector, or model
publisher writes.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3
from statistics import median
import tempfile

from deploy.scripts.v163_readonly_event_first_preview import OBS, _gap_index
from research.continuous_departure_replay import ArrivalEvidence
from research.japan_xanax.renewal_shadow import source_data
from research.plushie_champions.common import TRAVEL_SECONDS, GRACE, STEP
from research.quantity_rate_cycles import QuantityRateCycles
from research.true_zero_cycles import ZeroCycles, model as stock_model
from research.v166_seven_specialist_earliest_replay import CausalMirror
from research.v167_all24_live_policy_replay import ROUTES, event_timeline_for_issue
from research.v167_event_candidate_scoring import earliest_event_candidates
from research.v173_adaptive_flight_policy import (
    SPECIAL_WINDOWS, find_original_report, historical_openings, wait_window_grade,
    START, END,
)
from services.frozen_candidate_worker_v31 import _install_frozen_readonly_history
from services.travel_decision_contract_v166 import build_item_travel_decision

ENGINE_NAMES={
    "v18":("dyn1","dyn2","dyn3","dyn4","dyn5","dyn6","dyn7","dyn8"),
    "v19":tuple("dyn"+str(i) for i in range(1,14)),
    "v20":tuple("traj"+str(i) for i in range(1,15)),
}
# Evaluate every frozen full-history configuration, plus shorter-history
# versions of 2 representative configurations for each generation.
RECENT_NAMES={
    "v18":("dyn1","dyn3"),"v19":("dyn1","dyn8"),
    "v20":("traj1","traj12"),
}
RECENT_HOURS=(48,120)
CYCLE_WINDOWS=(6,10,20)
MIN_SCREEN_ISSUES=16


def candidates():
    names=["V169_INCUMBENT"]
    for family,configs in ENGINE_NAMES.items():
        names.extend(f"{family}:{cfg}" for cfg in configs)
        for hours in RECENT_HOURS:
            names.extend(f"{family}:{cfg}@{hours}h" for cfg in RECENT_NAMES[family])
    for family in ("zero","rate"):
        names.extend(f"{family}:recent{n}" for n in CYCLE_WINDOWS)
    return tuple(names)


ALL_CANDIDATES=candidates()


class AdaptiveZero(ZeroCycles):
    def __init__(self,crosses,window):
        super().__init__(crosses)
        self.window=window

    def _physical_state(self,asof):
        state=dict(super()._physical_state(asof))
        for field in ("stocked_durations","depleted_durations",
                      "future_stocked_durations"):
            if state.get(field):
                state[field]=list(state[field])[-self.window:]
        return state

    def _available_history(self):
        return self.available_durations[-self.window:]

    def forecast(self,key,*,asof):
        full=self.restock_quantities
        try:
            self.restock_quantities=full[-self.window:]
            return super().forecast(key,asof=asof)
        finally:
            self.restock_quantities=full


class AdaptiveRate(QuantityRateCycles):
    def __init__(self,crosses,window):
        super().__init__(crosses)
        self.window=window

    def _physical_state(self,asof):
        state=dict(super()._physical_state(asof))
        for field in ("stocked_durations","depleted_durations",
                      "future_stocked_durations"):
            if state.get(field):state[field]=list(state[field])[-self.window:]
        return state

    def _available_history(self):
        return super()._available_history()[-self.window:]

    def forecast(self,key,*,asof):
        from collections import deque
        full_rates=self.rates
        full_quantities=self.restock_quantities
        try:
            self.rates=deque(list(full_rates)[-self.window:],maxlen=64)
            self.restock_quantities=full_quantities[-self.window:]
            return super().forecast(key,asof=asof)
        finally:
            self.rates=full_rates
            self.restock_quantities=full_quantities


def advance_trackers(trackers,rows,pos,issued):
    while pos<len(rows) and rows[pos][0]<=issued:
        obs=OBS(*rows[pos])
        for tr in trackers.values():tr.add(obs)
        pos+=1
    return pos


def event_departures(events,issued,flight):
    """Try current stock and next reachable restocks, without a time horizon."""
    out=[]
    reachable=[e for e in events if e.get("reachable")]
    for e in reachable[:3]:
        departures=earliest_event_candidates([e],issued)
        for point in departures:
            dep=point.get("candidate_departure_epoch",
                          point.get("earliest_departure_epoch"))
            if isinstance(dep,int) and dep>=issued:
                out.append((dep-issued,point))
    out.sort(key=lambda x:x[0])
    # Strict point-count guard; not a maximum restock calendar lookahead.
    return out[:96]


def engine_issue_plans(db,key,issued,candidate_events,wanted):
    """Reconstruct historical engine features from the causal SQLite mirror."""
    dyn={name:None for name in wanted if name.startswith(("v18:","v19:","v20:"))}
    if not dyn or not candidate_events:return dyn
    from services import history_service
    _install_frozen_readonly_history(history_service,db)
    country,item=key.split(":",1)
    flight=TRAVEL_SECONDS[country]
    raw_delays=[x[0] for x in candidate_events]
    cfg_requests={}
    for name in dyn:
        family,remainder=name.split(":",1)
        cfg_name,*window=remainder.split("@",1)
        hours=int(window[0][:-1]) if window else None
        cfg_requests.setdefault(family,[]).append((name,cfg_name,hours))
    for family,requests in cfg_requests.items():
        if family=="v18":
            from services import plushie_flower_dynamic_planner_v18 as engine
            cleaned,cycles,_=engine.load_item(country,item,30)
            timeline=engine.Timeline(cleaned,cycles,30)
            deps,features=engine.completed_cycle_features(cycles)
        elif family=="v19":
            from services import plushie_flower_dynamic_planner_v19 as engine
            cleaned,cycles,_,_=engine.load_item(country,item,30)
            gaps=engine.normalize_gaps(history_service.get_collection_gaps())
            timeline=engine.Timeline(cleaned,cycles,30,gaps=gaps)
            deps,features=engine.completed_cycle_features(cycles,gaps=gaps)
        else:
            from services import plushie_flower_dynamic_planner_v20 as engine
            cleaned,cycles,_,_=engine.load_item(country,item,30)
            gaps=engine.normalize_gaps(history_service.get_collection_gaps())
            timeline=engine.Timeline(cleaned,cycles,30,gaps=gaps)
            deps,features=engine.completed_cycle_features(cycles,gaps=gaps)
        cfgs={c.name:c for c in engine.configs()}
        points=engine.build_points(timeline,deps,features,600)
        times=[p.t for p in points]
        for fullname,cfgname,hours in requests:
            if cfgname not in cfgs:raise ValueError("missing frozen config: "+fullname)
            if hours is not None:
                lower=issued-hours*3600
                lo=bisect.bisect_left(times,lower)
                selected=points[lo:]
                selected_times=times[lo:]
            else:
                selected=points
                selected_times=times
            if len(selected)<60:continue
            plan=engine.plan(float(issued),selected,selected_times,
                             timeline,deps,features,cfgs[cfgname],
                             raw_delays,flight,GRACE)
            if plan is None:continue
            depart=int(plan["departure_time"])
            if depart<issued:continue
            point=min(candidate_events,key=lambda p:abs(issued+p[0]-depart))[1]
            dyn[fullname]={
                "departure":depart,
                "target":point.get("predicted_restock_epoch"),
                "event_index":point.get("event_index"),
                "score":plan.get("probability"),
                "forecaster":fullname,
            }
    return dyn


def forecast_issue(db,key,issued,causal_rows,gaps,trackers,
                   wanted,baseline_record):
    flight=TRAVEL_SECONDS[key.split(":",1)[0]]
    forecast,events=event_timeline_for_issue(key,causal_rows,gaps,issued)
    cand=event_departures(events,issued,flight)
    plan={}
    if "V169_INCUMBENT" in wanted:
        event=baseline_record.get("selected_event") or {}
        plan["V169_INCUMBENT"]={
            "departure":baseline_record.get("recommended_departure_epoch"),
            "target":event.get("predicted_restock_epoch"),
            "event_index":event.get("event_index"),
            "forecaster":"V169_AS_ISSUED",
        }
    dyn={n for n in wanted if n.startswith(("v18:","v19:","v20:"))}
    if dyn:plan.update(engine_issue_plans(db,key,issued,cand,dyn))
    for name in wanted:
        if name not in trackers:continue
        f=trackers[name].forecast(key,asof=issued)
        d=build_item_travel_decision(f,now=issued,poll_age_seconds=0,
                                    arrival_policy="expected")
        departure=d.get("estimated_departure_epoch")
        selected=d.get("selected_restock_event_index")
        events2=f.get("restock_events") or []
        match=next((e for e in events2
                    if e.get("event_index")==selected),None)
        target=(match or {}).get("predicted_restock_epoch")
        if selected==0:target=issued
        plan[name]={"departure":departure,"target":target,
                    "event_index":selected,"forecaster":f.get("model_name")}
    return plan


def grade_candidates(plans,issued,flight,evidence,openings,waits,stats,
                     last=None,required_reconfirm=False):
    for name,decision in plans.items():
        c=stats[name];c["issues"]+=1
        dep=(decision or {}).get("departure")
        if type(dep) is not int or dep<issued:continue
        c["proposals"]+=1
        score=evidence.score(dep+flight)[0]
        if score in ("SUCCESS","FAILURE"):
            c["proposal_"+score.lower()]+=1
        else:c["proposal_unknown"]+=1
        if not required_reconfirm:continue
        previous=last.get(name)
        target=decision.get("target")
        aligned=(type(target) is int and previous is not None and
                 type(previous.get("target")) is int and
                 abs(target-previous["target"])<=900 and
                 previous["issued"]==issued-STEP)
        current=decision.get("event_index")==0
        # Preserve the V169 incumbent's original reconfirmation flag if given.
        if name=="V169_INCUMBENT":
            aligned=bool(decision.get("baseline_stable",aligned))
        if last is not None:last[name]={"issued":issued,"target":target}
        if not issued<=dep<issued+STEP or not (aligned or current):continue
        c["executions"]+=1
        if score in ("SUCCESS","FAILURE"):c["arrival_"+score.lower()]+=1
        else:c["arrival_unknown"]+=1
        if waits:
            detail=wait_window_grade(dep+flight,score,waits,openings,evidence)
            for minutes in waits:
                if detail[str(minutes)]=="POST_ARRIVAL_RESTOCK_WITHIN_WINDOW":
                    c[f"wait_{minutes}_success"]+=1
                elif detail[str(minutes)] in ("UNKNOWN_ARRIVAL",
                                               "UNCONFIRMED_RESTOCK_EVIDENCE"):
                    c[f"wait_{minutes}_unknown"]+=1


def brief(c,windows):
    issues=c["issues"]
    n=c["arrival_success"]+c["arrival_failure"]
    known_proposals=c["proposal_success"]+c["proposal_failure"]
    s={"issue_clocks":issues,"proposals":c["proposals"],
       "proposal_success":c["proposal_success"],
       "proposal_known":known_proposals,
       "proposal_coverage":c["proposals"]/issues if issues else 0,
       "proposal_arrival_success_fraction":(
           c["proposal_success"]/known_proposals if known_proposals else None),
       "actionable_departures":c["executions"],
       "actionable_known_arrivals":n,"actionable_successes":c["arrival_success"],
       "actionable_failures":c["arrival_failure"],
       "actionable_unknowns":c["arrival_unknown"],
       "actionable_arrival_success_fraction":(
           c["arrival_success"]/n if n else None),
       "actionable_success_per_issue":c["arrival_success"]/issues if issues else 0}
    for w in windows:
        extra=c[f"wait_{w}_success"]
        s[f"extra_wait_{w}_seconds_successes"]=extra
        s[f"landing_or_wait_{w}_seconds_success_per_issue"]=(
            (c["arrival_success"]+extra)/issues if issues else 0)
        s[f"wait_{w}_seconds_unknown"]=c[f"wait_{w}_unknown"]
    return s


def screen_rank(s,windows):
    if not s["issue_clocks"]:return (-1,0,0,0)
    known=s["proposal_known"]
    eligible=(known>=MIN_SCREEN_ISSUES
              and s["proposal_coverage"]>=.35)
    # Hourly issue scores reflect availability of useful advice, not
    # simulated executable departures (the hourly grid cannot identify 5m
    # commitments). Final grade requires five-minute action confirmation.
    return (int(eligible),
            s["proposal_success"]/s["issue_clocks"],
            s["proposal_arrival_success_fraction"] or 0,
            s["proposal_coverage"])


def release_recommendation(candidate,screen_winner,validation,windows):
    """Research decision only: promote candidate after actionable holdout gain.

    Every candidate was frozen on the development screen. No new thresholds,
    policies, or timing offsets are chosen from validation outcomes.
    """
    default={"selected_policy":"V169_INCUMBENT",
             "automatic_production_deploy":False}
    if candidate=="V169_INCUMBENT":
        return {**default,"reason":"ORIGINAL_CHAMPION_WON_DEVELOPMENT_SCREEN"}
    baseline=validation.get("V169_INCUMBENT")
    challenger=validation.get(candidate)
    if not baseline or not challenger:
        return {**default,"reason":"UNSCORED_FINALIST"}
    if (min(baseline["actionable_known_arrivals"],
            challenger["actionable_known_arrivals"])<30
        or min(baseline["actionable_departures"],
               challenger["actionable_departures"])<30):
        return {**default,"reason":"INSUFFICIENT_MATCHED_HOLDOUT_EXECUTIONS"}
    if (challenger["proposal_coverage"]<
        baseline["proposal_coverage"]*.75):
        return {**default,"reason":"PROPOSAL_COVERAGE_REGRESSION"}
    old=baseline["actionable_arrival_success_fraction"]
    new=challenger["actionable_arrival_success_fraction"]
    if old is None or new is None or new<old-.03:
        return {**default,"reason":"STOCK_ON_LANDING_REGRESSION"}
    if windows:
        w=max(windows)
        # Candidate and baseline have the same validation clock denominator.
        target=f"landing_or_wait_{w}_seconds_success_per_issue"
        baseline_value=baseline.get(target)
        candidate_value=challenger.get(target)
    else:
        target="actionable_success_per_issue"
        baseline_value=baseline.get(target)
        candidate_value=challenger.get(target)
    if baseline_value is None or candidate_value is None:
        return {**default,"reason":"MISSING_HOLDOUT_METRIC"}
    gain=candidate_value-baseline_value
    if gain<.005:
        return {**default,"reason":"INSUFFICIENT_ACTIONABLE_HOLDOUT_GAIN",
                "gain_per_issue":round(gain,6)}
    return {
        "selected_policy":candidate,
        "reason":"OFFLINE_PROMOTION_CANDIDATE_NEEDS_LIVE_IMPLEMENTATION",
        "gain_per_issue":round(gain,6),"comparison_metric":target,
        "automatic_production_deploy":False,
    }


def fixed_roster(source,reports,source_south,start,end):
    if not len(ROUTES)==25:raise ValueError("25-item roster contract changed")
    with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+
                                 "?mode=ro",uri=True,timeout=30)) as db:
        db.execute("PRAGMA query_only=ON")
        have={r[0] for r in db.execute(
            "SELECT DISTINCT country||':'||item_name FROM stock_history")}
        md=dict(db.execute("SELECT key,value FROM research_metadata"))
    missing={k for k in ROUTES if k not in have}
    if missing:raise ValueError("25-item data missing: "+repr(sorted(missing)))
    if md.get("sanitized_stock_only")!="true" or md.get("roster_size")!="25":
        raise ValueError("source must be the separate sanitized 25-item archive")
    original={}
    for key in sorted(ROUTES):
        original[key]=find_original_report(
            reports,key,start,end,south_report=source_south)
        if not original[key].get("records"):
            raise ValueError("missing V169 as-issued records: "+key)
    return original


def run_item(source,key,baseline,start,end,screen_step=3600,finalists=4):
    from research.v164_evidence_routed_earliest_restock import _truth_rows
    country=key.split(":",1)[0];flight=TRAVEL_SECONDS[country]
    rows,polls,crosses,evidence,cutoff=source_data(source,item_key=key)
    if end+flight+GRACE+180>cutoff:
        raise ValueError("immature validation arrival truth: "+key)
    starts=[r["issued_epoch"] for r in baseline["records"]]
    expected_last=start+((end-start)//STEP)*STEP
    if starts[0]!=start or starts[-1]!=expected_last or any(
            b-a!=STEP for a,b in zip(starts,starts[1:])):
        raise ValueError("V169 issue-tape identity mismatch: "+key)
    split=start+int((end-start)*.60)
    screen_epochs=[
        t for t in starts if t<split and t%screen_step==0
    ]
    validation_epochs=[t for t in starts if t>=split]
    if not screen_epochs or not validation_epochs:
        raise ValueError("no chronological split")
    by_issue={r["issued_epoch"]:r for r in baseline["records"]}
    opening_evidence=historical_openings(rows,crosses)
    wait_windows=SPECIAL_WINDOWS.get(key,())
    records_by_time=[r[0] for r in rows]
    available=tuple(ALL_CANDIDATES)
    screen_stats={name:Counter() for name in available}
    val_stats=None
    scratch=None
    with tempfile.TemporaryDirectory(prefix="v174-forecasts-") as td:
        scratch=Path(td)/(key.replace(":","__").replace(" ","_")+".sqlite")
        mirror=CausalMirror(source,scratch,screen_epochs[0])
        def trackers(names):
            return {n:(AdaptiveRate(crosses,int(n.split("recent")[1])) if n.startswith("rate:")
                       else AdaptiveZero(crosses,int(n.split("recent")[1])))
                    for n in names if n.startswith(("rate:","zero:"))}
        current=trackers(available)
        position=advance_trackers(current,rows,0,screen_epochs[0])
        for i,issued in enumerate(screen_epochs,1):
            mirror.advance(issued)
            position=advance_trackers(current,rows,position,issued)
            causal=rows[:bisect.bisect_right(records_by_time,issued)]
            # All source gaps used for training end no later than issuance.
            with closing(sqlite3.connect(scratch.as_uri()+"?mode=ro",uri=True)) as db:
                db.execute("PRAGMA query_only=ON")
                gaps=db.execute("SELECT start_timestamp,end_timestamp FROM collection_gaps ORDER BY start_timestamp").fetchall()
            names=set(available)
            plans=forecast_issue(scratch,key,issued,causal,gaps,current,
                                 names,by_issue[issued])
            grade_candidates(plans,issued,flight,evidence,opening_evidence,
                             wait_windows,screen_stats)
            if i%8==0:
                print(json.dumps({"stage":"SCREEN","item":key,
                                  "issues_complete":i,
                                  "issues_total":len(screen_epochs),
                                  "configs":len(available)}),flush=True)
        screen_briefs={n:brief(c,wait_windows) for n,c in screen_stats.items()}
        ranked=sorted(available,key=lambda n:screen_rank(screen_briefs[n],wait_windows),
                      reverse=True)
        selected=list(ranked[:finalists])
        if "V169_INCUMBENT" not in selected:
            selected[-1]="V169_INCUMBENT"
        selected=tuple(dict.fromkeys(selected))
        val_stats={n:Counter() for n in selected}
        # Validation is independent: fresh trackers advance causally from
        # initial history, but only finalist configs run inference.
        current=trackers(selected)
        position=0
        last={}
        for i,issued in enumerate(validation_epochs,1):
            mirror.advance(issued)
            position=advance_trackers(current,rows,position,issued)
            causal=rows[:bisect.bisect_right(records_by_time,issued)]
            with closing(sqlite3.connect(scratch.as_uri()+"?mode=ro",uri=True)) as db:
                db.execute("PRAGMA query_only=ON")
                gaps=db.execute("SELECT start_timestamp,end_timestamp FROM collection_gaps ORDER BY start_timestamp").fetchall()
            rec=by_issue[issued]
            plans=forecast_issue(scratch,key,issued,causal,gaps,current,
                                 set(selected),rec)
            if "V169_INCUMBENT" in plans:
                plans["V169_INCUMBENT"]["baseline_stable"]=(
                    rec.get("target_stable_from_previous_replan"))
            grade_candidates(plans,issued,flight,evidence,opening_evidence,
                             wait_windows,val_stats,
                             last=last,required_reconfirm=True)
            if i%48==0:
                print(json.dumps({"stage":"VALIDATION","item":key,
                                  "issues_complete":i,
                                  "issues_total":len(validation_epochs),
                                  "finalists":list(selected)}),flush=True)
    val_briefs={n:brief(c,wait_windows) for n,c in val_stats.items()}
    selection=next((name for name in ranked if name in selected),"V169_INCUMBENT")
    gate=release_recommendation(selection,ranked[0],val_briefs,wait_windows)
    return {
        "item_key":key,"status":"V174_ALL25_FULL_MODEL_REFORECAST_COMPLETED",
        "model_recomputed_per_issue":True,"screen_configurations":len(available),
        "screen_issue_clocks":len(screen_epochs),
        "validation_issue_clocks":len(validation_epochs),
        "screen_step_seconds":screen_step,"validation_step_seconds":STEP,
        "data_window_start_epoch":start,"data_window_end_epoch":end,
        "screen_ranking":[{"candidate":n,"screen":screen_briefs[n]} for n in ranked],
        "finalists":list(selected),
        "development_selected_candidate":selection,
        "research_release_recommendation":gate,
        "validation_results":val_briefs,
        "original_champion_validation":val_briefs.get("V169_INCUMBENT"),
        "special_wait_windows_seconds":list(wait_windows),
        "actual_player_flights":False,"production_modified":False,
        "release_automatic":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True)
    parser.add_argument("--v169-root",required=True)
    parser.add_argument("--south-africa-report",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--screen-step",type=int,default=3600,
                        choices=(1800,3600,7200))
    parser.add_argument("--finalists",type=int,default=4)
    parser.add_argument("--start-epoch",type=int,default=START)
    parser.add_argument("--end-epoch",type=int,default=END)
    args=parser.parse_args()
    if not 3<=args.finalists<=6:parser.error("finalists must be 3..6")
    source=Path(args.source).resolve(strict=True)
    out=Path(args.output).resolve()
    if out.exists():raise FileExistsError("original output protected; choose another")
    out.parent.mkdir(parents=True,exist_ok=True)
    reports=fixed_roster(source,args.v169_root,args.south_africa_report,
                         args.start_epoch,args.end_epoch)
    fingerprint=hashlib.sha256(
        (Path(__file__).read_bytes()+
         str(source.stat().st_size).encode()+
         str(source.stat().st_mtime_ns).encode())).hexdigest()[:16]
    partdir=out.parent/(out.stem+"_verified_parts_"+fingerprint)
    partdir.mkdir(parents=True,exist_ok=True)
    results={}
    for idx,key in enumerate(sorted(ROUTES),1):
        p=partdir/(key.replace(":","__").replace(" ","_")+".json")
        raw=hashlib.sha256(json.dumps(reports[key],sort_keys=True).encode()).hexdigest()
        identity={"key":key,"baseline_sha256":raw,
                  "start":args.start_epoch,"end":args.end_epoch,
                  "step":args.screen_step,"finalists":args.finalists}
        if p.exists():
            saved=json.loads(p.read_text(encoding="utf-8"))
            if saved.get("identity")!=identity:
                raise ValueError("checkpoint mismatch: "+str(p))
            results[key]=saved["result"];resumed=True
        else:
            results[key]=run_item(source,key,reports[key],
                                  args.start_epoch,args.end_epoch,
                                  args.screen_step,args.finalists)
            with p.open("x",encoding="utf-8") as dest:
                json.dump({"identity":identity,"result":results[key]},
                          dest,indent=2,sort_keys=True)
                dest.write("\n")
            resumed=False
        print(json.dumps({"progress":f"{idx}/25","item_key":key,
                          "status":"COMPLETED","resumed":resumed,
                          "selected":results[key]["development_selected_candidate"],
                          "release_policy":results[key]["research_release_recommendation"]["selected_policy"],
                          "finalists":results[key]["finalists"]}),flush=True)
    output={
        "status":"V174_COMPLETED_TRUE_ALL25_CAUSAL_FORECAST_TOURNAMENT",
        "scope":"ALL_25_ITEMS_ACTUAL_MODEL_REFORECASTS",
        "model_families":"V18_V19_V20_FULL_AND_RECENT_PLUS_RECENT_ZERO_RATE",
        "screen_first_60pct":"PER_ITEM_ACTUAL_MODEL_INFERENCE_HOURLY",
        "validation_last_40pct":"FULL_FIVE_MINUTE_ACTIONABLE_FROZEN_FINALISTS",
        "legacy_V169_incumbent_included_for_every_item":True,
        "recommendation":"Review before real website publisher promotion",
        "source_is_read_only":True,
        "production_modified":False,
        "items_completed":len(results),
        "per_item_results":results,
    }
    out.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":output["status"],"items_completed":len(results),
                      "output":str(out)}),flush=True)


if __name__=="__main__":
    main()
