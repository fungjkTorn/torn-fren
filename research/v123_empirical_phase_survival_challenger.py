"""V123: empirical multi-cycle survival forecast from distinct depletion anchors.

V122 proved Nessie's one-reference template produces exclusively binary 0/1
availability scores and yielded no matched win against flying immediately.
This RESEARCH challenger uses V107's causal completed phase durations, but
predicts a probability-like fraction of deterministic Monte-Carlo scenarios
in which >=30 stock is available at each possible UK arrival time.

No model tuning from observed test outcomes: predeclared configuration
128 seeded scenarios, p>=0.60, improvement >=0.15 vs fly-now if delayed,
two adjacent five-minute points, 8h max planning horizon, UK flight 6360s.
Scores are not calibrated probabilities. Uncertainty comes from empirical
finished low/high phase duration samples within uninterrupted source epochs,
not YATA provider-corrected game-world restocks.

At observed distinct DEPLETED (<30) phase-transition timestamps:
- use ONLY stock-change rows at or before issue to build phase durations;
- optionally select earliest projected flight meeting prespecified risk gate;
- separately retain depart-now as the unconditional baseline;
- only AFTER choices inspect V88 poll-heartbeat stocks at future landings.
- no action != miss; proxy unknown != miss; matched bound not statistical CI.
This previously investigated holdout is exploratory, NOT new validation.
No API, files, database writes, gameplay actions, collectors, model/website
changes, or service modifications. Provider country-update age unavailable.
"""
from __future__ import annotations

import argparse
import bisect
import json
import random
import sqlite3
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import (
    TRAVEL_SECONDS,MAX_WAIT,STEP,GRACE
)
from research.v107_explicit_restock_cycle_baseline import completed_phases
from research.v109_raw_restock_transition_event_audit import (
    SOURCE,TARGETS,read_collector_item,transition_episodes
)
from research.v110_multicycle_restock_horizon_audit import choose_anchor_events
from research.v88_poll_state_forward_report import observation as poll_observation
from research.v60_private_snapshot_probe import approved_collector_source

SCENARIOS=128
MIN_PHASES=5
MIN_SCORE=0.60
MIN_LIFT=0.15
MIN_CONSECUTIVE=2
MAX_ANCHORS=35
MAX_COMPLETED_HISTORY=50000
MAX_SCORING_HOURS=24
REQUIRED_TRAVEL_SECONDS=6360
SEED=711_237


def empirical_survival_curve(observations,item_key,*,asof,gaps=(),
                             scenarios=SCENARIOS,seed=SEED):
    """Simulate past-only empirical durations; never read asof-future rows."""
    if (type(asof) is not int or asof<=0
        or type(seed) is not int
        or type(scenarios) is not int or not 1<=scenarios<=1024
        or item_key not in ("uni:Red Fox Plushie","uni:Nessie Plushie")):
        raise ValueError("invalid research model options")
    if len(observations)>MAX_COMPLETED_HISTORY:
        raise ValueError("too many source rows; abort rather than truncate")
    # Fail rather than silently letting a caller send a future observation.
    if any(o.epoch>asof for o in observations):
        raise ValueError("future observation in model history")
    history=completed_phases(
        observations,asof=asof,collection_gaps=gaps)
    meta={
        "status":"ABSTAIN",
        "item_key":item_key,"asof":asof,"source_country_age_verified":False,
        "past_completed_depleted_phases":len(history["depleted_durations"]),
        "past_completed_stocked_phases":len(history["stocked_durations"]),
        "scenario_count":scenarios,
        "availability_scores_not_calibrated":True,
    }
    if history["phase"]!="LOW" or history["phase_onset"] is None:
        return dict(meta,status="NOT_KNOWN_DEPLETED")
    last=history["last_observation"]
    if last is None or last.epoch!=asof:
        # Historical events provide fresh *collector-observed changes*, but
        # not necessarily fresh upstream UK provider update timestamps.
        return dict(meta,status="NO_FRESH_COLLECTOR_TRANSITION")
    age=asof-int(history["phase_onset"])
    lows=[int(x) for x in history["depleted_durations"] if int(x)>=STEP]
    highs=[int(x) for x in history["stocked_durations"] if int(x)>=STEP]
    if min(len(lows),len(highs))<MIN_PHASES:
        return dict(meta,status="INSUFFICIENT_COMPLETED_CYCLES")
    survive=[x for x in lows if x>age]
    if len(survive)<MIN_PHASES:
        return dict(meta,status="NO_LOW_PHASE_SURVIVORS")
    flight=TRAVEL_SECONDS["uni"]
    offsets=[flight+d for d in range(0,MAX_WAIT+1,STEP)]
    if len(offsets)!=97:
        raise AssertionError("wrong 8h grid")
    duration_horizon=offsets[-1]+GRACE
    counts=[0]*len(offsets)
    rng=random.Random(seed+asof%100003)
    # Completed historical phase durations exclusively drive future paths.
    for _ in range(scenarios):
        depleted_remaining=rng.choice(survive)-age
        pos=float(depleted_remaining)
        intervals=[]
        guard=0
        while pos<=duration_horizon:
            guard+=1
            if guard>1000:
                raise RuntimeError("implausibly high number of empirical cycles")
            high_length=rng.choice(highs)
            intervals.append((pos,pos+high_length))
            pos+=high_length+rng.choice(lows)
        for j,t in enumerate(offsets):
            if any(begin-GRACE<=t<end for begin,end in intervals):
                counts[j]+=1
    scores=[c/scenarios for c in counts]
    return dict(
        meta,status="EMPIRICAL_STOCK_SURVIVAL_CURVE",
        start_phase_age_seconds=age,
        delay_seconds=list(range(0,MAX_WAIT+1,STEP)),
        arrivals=[asof+delta for delta in offsets],
        scores=scores,
        immediate_arrival_score=scores[0],
        unique_values=len(set(scores)),
        min_score=min(scores),max_score=max(scores)
    )


def choose_departure(curve,*,asof,score_floor=MIN_SCORE,
                     required_lift=MIN_LIFT,
                     consecutive=MIN_CONSECUTIVE):
    """Prespecified gate: earlier risk-supported flight, or abstain.

    Score at arrival NOW is first option. A delayed proposal requires
    at least 0.15 higher model score than NOW to justify waiting.
    """
    if (not 0<=score_floor<=1 or not 0<=required_lift<=1
        or type(consecutive) is not int or not 1<=consecutive<=12):
        raise ValueError("invalid selection thresholds")
    if curve["status"]!="EMPIRICAL_STOCK_SURVIVAL_CURVE":
        return {
            "departure":None,"score":None,
            "status":"MODEL_ABSTAIN_"+curve["status"]}
    arr=curve["scores"]
    ds=curve["delay_seconds"]
    if len(ds)!=len(arr) or not arr:
        raise AssertionError("inconsistent curve")
    now_score=arr[0]
    if now_score>=score_floor:
        return {
            "departure":asof,"score":now_score,
            "status":"DEPART_NOW_SUPPORTED"}
    cutoff=max(score_floor,now_score+required_lift)
    for j in range(len(ds)-consecutive+1):
        if all(arr[j+k]>=cutoff and
               ds[j+k]-ds[j]==k*STEP
               for k in range(consecutive)):
            return {
                "departure":asof+ds[j],
                "score":arr[j],
                "status":"DELAYED_ABOVE_IMMEDIATE_SCORE"}
    return {
        "departure":None,"score":None,
        "status":"NO_CONFIDENT_ARRIVAL_WINDOW"}


def _pair(records):
    c=Counter()
    deltas=[]
    for r in records:
        a,b=r["model_hit"],r["immediate_hit"]
        dep=r["model_departure"]
        c["depletion_starts"]+=1
        if dep is None:
            c["model_no_departure"]+=1
            continue
        c["model_departed"]+=1
        deltas.append((dep-r["issue"])/60)
        if dep==r["issue"]:
            c["identical_departures"]+=1
            if a!=b:
                raise AssertionError("identical flight gave different evidence")
        if a is None or b is None:
            c["unknown_pair"]+=1
            continue
        c["scorable_pairs"]+=1
        if a and b:c["both_hit"]+=1
        elif a:c["model_only_hit"]+=1
        elif b:c["immediate_only_hit"]+=1
        else:c["both_miss"]+=1
    n=c["depletion_starts"]
    return {
        **{key:c[key] for key in (
            "depletion_starts","model_departed","model_no_departure",
            "identical_departures","unknown_pair","scorable_pairs",
            "both_hit","model_only_hit","immediate_only_hit","both_miss")},
        "net_known_model_only_minus_now_only":
            c["model_only_hit"]-c["immediate_only_hit"],
        "mean_model_wait_minutes":
            round(statistics.mean(deltas),2) if deltas else None,
        "observed_model_hit_lower_bound_per_start":round(
            sum(r["model_hit"] is True for r in records)/n,4) if n else None,
        "observed_now_hit_lower_bound_per_start":round(
            sum(r["immediate_hit"] is True for r in records)/n,4) if n else None,
        "proxy_unknowns_not_counted_as_failed":True,
    }


def audit_item(obs,gaps,collector,*,item_key,asof,max_anchors=25,
               model=empirical_survival_curve,
               scorer=poll_observation):
    if not 1<=max_anchors<=MAX_ANCHORS:
        raise ValueError("invalid anchor cap")
    country,item=item_key.split(":",1)
    flight=TRAVEL_SECONDS[country]
    episodes,rejected=transition_episodes(obs,gaps)
    anchors=choose_anchor_events(obs,episodes,max_events=max_anchors)
    timeline=[x.epoch for x in obs]
    evaluated=[]
    example=[]
    reasons=Counter()
    for index in anchors:
        anchor=episodes[index]
        if anchor["phase"]!="DEPLETED":
            raise AssertionError("not an initial-depletion event")
        issue=int(anchor["issue"])
        if issue+MAX_WAIT+flight+200>asof:
            reasons["IMMATURE_FULL_HORIZON"]+=1
            continue
        historical=obs[:bisect.bisect_right(timeline,issue)]
        if not historical or historical[-1].epoch!=issue:
            raise AssertionError("depleted event not observed at asof")
        curve=model(historical,item_key,asof=issue,gaps=gaps)
        selection=choose_departure(curve,asof=issue)
        dep=selection["departure"]
        if dep is not None and not issue<=dep<=issue+MAX_WAIT:
            raise AssertionError("model flight outside allowed horizon")
        # Critically: no score of any future arrival occurs before choices.
        if dep is not None:
            st_m,hit_m,_=scorer(
                collector,country,item,dep+flight,asof)
        else:
            st_m,hit_m="NO_ACTION",None
        st_n,hit_n,_=scorer(
            collector,country,item,issue+flight,asof)
        if dep==issue and hit_m!=hit_n:
            raise AssertionError("same flight should have identical evidence")
        reasons["model_"+selection["status"]]+=1
        reasons["model_arrival_"+st_m]+=1
        reasons["now_arrival_"+st_n]+=1
        evaluated.append({
            "issue":issue,
            "model_departure":dep,
            "model_hit":hit_m,"immediate_hit":hit_n,
            "predicted_now_score":curve.get("immediate_arrival_score"),
            "predicted_chosen_score":selection.get("score"),
            "decision_status":selection["status"],
        })
        if len(example)<5:
            example.append({
                "issue":issue,
                "model_status":selection["status"],
                "now_score":curve.get("immediate_arrival_score"),
                "recommended_score":selection.get("score"),
                "recommended_departure":dep,
                "now_evidence":st_n,"model_evidence":st_m,
                "score_is_calibrated_probability":False,
            })
    summary=_pair(evaluated)
    summary.update({
        "item_key":item_key,
        "completed_phases":len(episodes),
        "eligible_distinct_depleted_anchor_count":len(anchors),
        "matured_depletion_anchors_evaluated":len(evaluated),
        "unmatured_anchors_censored":reasons["IMMATURE_FULL_HORIZON"],
        "transition_rejections":dict(rejected),
        "decision_and_proxy_reasons":dict(sorted(reasons.items())),
        "examples":example,
        "historical_window_previously_inspected":True,
        "independent_restock_epochs_not_player_flights":True,
        "provider_country_update_age_verified":False,
        "causal_prior_completed_phase_model_only":True,
    })
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=("redfox","nessie","both"),
                   default="both")
    p.add_argument("--events",type=int,default=25)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not 1<=args.events<=MAX_ANCHORS:
        p.error("invalid event cap")
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved collector source")
    t0=time.monotonic()
    selected=TARGETS if args.target=="both" else {
        args.target:TARGETS[args.target]}
    with closing(sqlite3.connect(
        Path(SOURCE).resolve(strict=True).as_uri()+"?mode=ro",
        uri=True,timeout=15)) as collector:
        collector.execute("PRAGMA query_only=ON")
        items={}
        for key,(country,item) in selected.items():
            observations,gaps=read_collector_item(
                collector,country,item)
            items[key]=audit_item(
                observations,gaps,collector,
                item_key=f"{country}:{item}",
                asof=int(time.time()),max_anchors=args.events)
    report={
        "status":"V123_CAUSAL_EMPIRICAL_PHASE_SURVIVAL_RESTOCK_CHALLENGER",
        "read_only":True,
        "item_results":items,
        "raw_probability_scores_calibrated":False,
        "new_prospective_validation":False,
        "country_specific_provider_age_available":False,
        "actual_player_flights_recorded":False,
        "scenario_count":SCENARIOS,
        "required_win_margin_above_now":MIN_LIFT,
        "required_minimum_model_score":MIN_SCORE,
        "required_consecutive_5m_points":MIN_CONSECUTIVE,
        "forecast_only_past_completed_phase_history":True,
        "elapsed_seconds":round(time.monotonic()-t0,2),
    }
    if args.json:
        print(json.dumps(report,sort_keys=True))
    else:
        print("===== V123 DEPLETION-FIRST EMPIRICAL RESTOCK PROBABILITY =====")
        print("Read-only historical exploratory model; not live-certified.")
        for key,item in items.items():
            print(key,json.dumps(item,sort_keys=True))
        print("Model Monte Carlo scenario count",SCENARIOS,
              "risk gate",MIN_SCORE,"lift",MIN_LIFT,
              "max wait 8h, UK flight 106m")
        print("Elapsed",report["elapsed_seconds"],
              "country-provider freshness and gameplay NOT certified.")


if __name__=="__main__":
    main()
