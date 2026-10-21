"""V126: read-only diagnostic for V125 UNKNOWN phase onset.

An upstream provider switch or gap may start a source-continuous HIGH or
LOW segment without observing its actual opening threshold transition.
Do NOT set onset equal to last item observation or source change: that
would invent a restock date.

Retain the V125 decision as ABSTAIN. To quantify the blind spot, derive
the minimum *observed* uninterrupted current-state duration (the first
same-provider stock-change observation in the present uninterrupted
segment). Construct a separate EXPLORATORY unknown-onset score curve:
completed empirical phase durations sampled under a declared stationary
observation-time assumption with weights max(D-L,0), where L is verified
continuous current state observation duration. In each scenario, the
unobserved age at the segment's first observation is sampled uniformly
0..D-L; the remaining current phase duration is D-L-age.

This conditional-on-survival model has severe provider selection biases
and is NOT a calibrated stock availability probability, certified source
freshness, actual restock timing, or an actionable flight recommendation.
It is displayed only as a PROVISIONAL research candidate; V125 remains
unchanged. Do not auto-travel or write source/sidecar/website. Default
single-run preview only. Later use as-issued true phase change data to
validate and potentially replace this fallback.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from contextlib import closing

from research.plushie_champions.common import TRAVEL_SECONDS,MAX_WAIT,STEP,GRACE
from research.v107_explicit_restock_cycle_baseline import completed_phases
from research.v109_raw_restock_transition_event_audit import TARGETS,read_collector_item
from research.v123_empirical_phase_survival_challenger import MIN_PHASES,SCENARIOS
from research import v125_earliest_credible_shadow as base

SEED=711239
MAX_COUNTRY_ITEM_ROWS=50000
SENSITIVITY_MODEL="v126_stationary_source_segment_residual_life"
POLICY="V125 unchanged - V126 hypothetical only"


def gap_crosses(gaps,a,b):
    return any(lo<=b and (hi is None or hi>=a) for lo,hi in gaps)


def source_segment_duration(observations,gaps,*,asof):
    """Return current state uninterrupted observation LOWER bound, not onset."""
    if not observations or observations[-1].epoch>asof:
        return {"status":"NO_CONTIGUOUS_EVIDENCE"}
    terminal=observations[-1]
    flag=terminal.quantity>=30
    source=terminal.source
    beginning=terminal.epoch
    count=1
    for prev,next_obs in zip(reversed(observations[:-1]),
                             reversed(observations[1:])):
        if (prev.epoch>=next_obs.epoch
            or prev.source!=source
            or (prev.quantity>=30)!=flag
            or gap_crosses(gaps,prev.epoch,next_obs.epoch)):
            break
        beginning=prev.epoch
        count+=1
    return {
        "status":"SOURCE_SEGMENT_LOWER_BOUND",
        "item_source":source,"observed_state":"HIGH" if flag else "LOW",
        "first_uninterrupted_observation_epoch":beginning,
        "last_observation_epoch":terminal.epoch,
        "asof_epoch":asof,
        "known_uninterrupted_observed_age_lower_bound_seconds":asof-beginning,
        "observed_item_change_rows_in_segment":count,
        "true_phase_start_unknown":True,
    }


def hypothetical_unknown_onset_curve(observations,item_key,*,asof,gaps=(),
                                    scenarios=SCENARIOS,seed=SEED):
    if (type(asof) is not int or asof<=0
        or item_key not in ("uni:Nessie Plushie","uni:Red Fox Plushie")
        or type(scenarios) is not int or not 1<=scenarios<=1024
        or len(observations)>MAX_COUNTRY_ITEM_ROWS
        or any(o.epoch>asof for o in observations)):
        raise ValueError("invalid hypothetical source history or asof")
    h=completed_phases(observations,asof=asof,collection_gaps=gaps)
    meta={
        "status":"ABSTAIN","item_key":item_key,
        "historical_phase":h["phase"],
        "observed_phase_onset":h["phase_onset"],
        "source_country_freshness_verified":False,
        "phase_start_imputed":False,
        "model_is_exploratory_not_calibrated":True,
        "scenario_count":scenarios,
        "future_stock_consulted":False,
    }
    if h["phase"] not in ("LOW","HIGH") or h["phase_onset"] is not None:
        return dict(meta,status="NOT_AN_UNKNOWN_ONSET")
    bounds=source_segment_duration(observations,gaps,asof=asof)
    if bounds["status"]!="SOURCE_SEGMENT_LOWER_BOUND":
        return dict(meta,status="NO_VERIFIABLE_SEGMENT")
    last=h["last_observation"]
    if last is None or not 0<=asof-last.epoch<=base.MAX_LAST_CHANGE_AGE_SECONDS:
        return dict(meta,status="STOCK_LAST_CHANGE_TOO_OLD",bounds=bounds)
    history={
        "HIGH":[int(x) for x in h["stocked_durations"] if x>=STEP],
        "LOW":[int(x) for x in h["depleted_durations"] if x>=STEP],
    }
    if min(map(len,history.values()))<MIN_PHASES:
        return dict(meta,status="INSUFFICIENT_COMPLETED_PHASES",bounds=bounds)
    phase=h["phase"]
    L=bounds["known_uninterrupted_observed_age_lower_bound_seconds"]
    weighted=[(D,D-L) for D in history[phase] if D>L]
    if len(weighted)<MIN_PHASES:
        return dict(meta,status="INSUFFICIENT_AGE_SURVIVORS",bounds=bounds)
    total=sum(w for _,w in weighted)
    if total<=0:
        return dict(meta,status="NO_RESIDUAL_LIFE_EVIDENCE",bounds=bounds)
    rng=random.Random(seed+asof%100003)
    offsets=[TRAVEL_SECONDS["uni"]+d for d in range(0,MAX_WAIT+1,STEP)]
    horizon=offsets[-1]+GRACE
    counts=[0]*len(offsets)
    durations=[x for x,_ in weighted]
    weights=[w for _,w in weighted]
    for _ in range(scenarios):
        duration=rng.choices(durations,weights=weights,k=1)[0]
        prior_age=rng.uniform(0,duration-L)
        residual=float(duration-L-prior_age)
        state=phase
        position=residual
        stocked_intervals=[(0.,position)] if phase=="HIGH" else []
        loops=0
        while position<=horizon:
            loops+=1
            if loops>1000:raise RuntimeError("unbounded scenario paths")
            state="LOW" if state=="HIGH" else "HIGH"
            length=rng.choice(history[state])
            if state=="HIGH":
                stocked_intervals.append((position,position+length))
            position+=length
        for i,offset in enumerate(offsets):
            if any(start-GRACE<=offset<end for start,end in stocked_intervals):
                counts[i]+=1
    scores=[round(count/scenarios,8) for count in counts]
    return dict(
        meta,status="UNCERTAIN_ORIGIN_EXPLORATORY_CURVE",
        asof_epoch=asof,
        bounds=bounds,
        scenario_hypothesis="stationary phase observation conditional on seen high/low duration",
        still_unverified_source_country_age=True,
        historical_current_type_duration_count=len(history[phase]),
        surviving_phase_durations_used=len(weighted),
        delay_seconds=list(range(0,MAX_WAIT+1,STEP)),
        scores=scores,
        projected_leave_now_arrival_score=scores[0],
        score_distinct_count=len(set(scores)),
    )


def read_only_preview(*,source=base.SOURCE,sidecar=base.SIDECAR,
                      now=None,enforce=True):
    issued=int(time.time() if now is None else now)
    source,_=base.canonical_paths(
        source=source,sidecar=sidecar,enforce=enforce)
    original=base.observe(
        source=source,sidecar=sidecar,now=issued,
        record=False,enforce=enforce)
    extra={}
    if original["global_heartbeat_age_seconds"] is None or not (
        0<=original["global_heartbeat_age_seconds"]<=base.GLOBAL_HEARTBEAT_AGE_LIMIT
    ):
        return {"status":"V126_STALE_GLOBAL_HEARTBEAT",
                "read_only":True,"original_v125":original,
                "unknown_phase_diagnostics":{}}
    with closing(base.source_readonly(source)) as db:
        for country,item in (TARGETS["redfox"],TARGETS["nessie"]):
            key=f"{country}:{item}"
            issued_rec=original["as_issued_model_recommendations"][key]
            if issued_rec["status"]!="CURRENT_PHASE_ONSET_UNKNOWN":
                extra[key]={
                    "status":"V125_ONSET_KNOWN_OR_OTHER_ABSTENTION",
                    "original_v125_status":issued_rec["status"],
                    "provisional_departure":None,
                }
                continue
            series,gaps=read_collector_item(db,country,item)
            curve=hypothetical_unknown_onset_curve(
                series,key,asof=issued,gaps=gaps)
            candidate=None
            if curve["status"]=="UNCERTAIN_ORIGIN_EXPLORATORY_CURVE":
                analog={
                    "status":"ISSUED_TWO_PHASE_SCENARIO_CURVE",
                    "asof_epoch":issued,
                    "delay_seconds":curve["delay_seconds"],
                    "scores":curve["scores"],
                }
                candidate=base.earliest_credible(analog)
            extra[key]={
                "status":curve["status"],
                "true_phase_onset_unknown":True,
                "replaces_v125_recommendation":False,
                "is_actionable_departure":False,
                "provisional_departure":(
                    None if candidate is None else candidate["departure"]),
                "provisional_wait_minutes":(
                    None if candidate is None
                    or candidate["departure"] is None
                    else round((candidate["departure"]-issued)/60,2)),
                "provisional_arrival_score":(
                    None if candidate is None else candidate["score"]),
                "hypothetical_now_score":curve.get(
                    "projected_leave_now_arrival_score"),
                "score_model_hypothesis":curve.get("scenario_hypothesis"),
                "continuous_stock_evidence":curve.get("bounds"),
                "historical_surviving_phase_examples":curve.get(
                    "surviving_phase_durations_used"),
                "country_stock_source_freshness_verified":False,
            }
    return {
        "status":"V126_UNKNOWN_ORIGIN_READ_ONLY_SENSITIVITY_PREVIEW",
        "read_only":True,"research_only":True,
        "written_databases":0,
        "production_modified":False,
        "original_v125":original,
        "unknown_phase_diagnostics":extra,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preview",action="store_true")
    args=p.parse_args()
    print(json.dumps(read_only_preview(),sort_keys=True))


if __name__=="__main__":
    main()
