"""V125: first credible UK departure, including both HIGH and LOW stock phases.

V123/V124 required a recent LOW transition and treated leave-now as a
preferred fallback. That is NOT the user's objective. The first departure
whose modeled ARRIVAL stock >=30 is sufficiently credible may be now,
+20 minutes or later. Historical completed HIGH/LOW durations are sampled
to create 128 empirical paths conditioned on survival to CURRENT issue time.
Check a 106-minute outbound flight and up to 8h departure wait.

Prespecified experimental rule: earliest TWO adjacent 5-minute departure
bins with empirical scenario availability >=0.60. There is NO special
bonus for leaving immediately and NO arbitrary 0.15 improvement hurdle.
Score is not calibrated probability or verified upstream stock.
The selected future WATCH is provisional, not executable under today's
5m snapshot; record it and re-evaluate prospectively each issue.

Opt-in sidecar records EVERY genuine as-issued research snapshot, with
UNIQUE(item_key,issued_epoch,policy_id), including abstentions. Default
preview performs zero writes. The collector is always read-only, and the
separate sidecar stays under /var/lib/torn-fren-v38. No service installation,
automated travel, website publication, provider calls or production edits.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS,MAX_WAIT,STEP,GRACE
from research.v107_explicit_restock_cycle_baseline import completed_phases
from research.v109_raw_restock_transition_event_audit import SOURCE,TARGETS,read_collector_item
from research.v60_private_snapshot_probe import approved_collector_source,read_heartbeat
from research.v123_empirical_phase_survival_challenger import SCENARIOS,MIN_PHASES

ROOT=Path("/var/lib/torn-fren-v38")
SIDECAR=ROOT/"v125_earliest_credible_shadow.db"
POLICY_ID="v125_first_credible_two_bins_060_empirical_128_v1"
GLOBAL_HEARTBEAT_AGE_LIMIT=180
MAX_LAST_CHANGE_AGE_SECONDS=6*3600
MAX_ITEM_SOURCE_ROWS=50000
SCORE_FLOOR=0.60
MIN_CONSECUTIVE=2
SEED=711238


def phase_survival_curve(observations,item_key,*,asof,gaps=(),
                         scenarios=SCENARIOS,seed=SEED):
    """Pure, causal two-phase empirical Monte Carlo model.

    The observed HIGH or LOW phase remains active as of the issue. Condition
    its remaining duration on prior completed same-type phases exceeding
    the observed elapsed age; then sample alternating completed durations.
    The resulting fraction of stocked scenarios is NOT a true probability.
    """
    if (type(asof) is not int or asof<=0
        or type(scenarios) is not int or not 1<=scenarios<=1024
        or type(seed) is not int
        or item_key not in ("uni:Red Fox Plushie","uni:Nessie Plushie")):
        raise ValueError("invalid V125 research model input")
    if len(observations)>MAX_ITEM_SOURCE_ROWS:
        return {"status":"ROW_CAP","item_key":item_key}
    if any(o.epoch>asof for o in observations):
        raise ValueError("asof future stock history prohibited")
    h=completed_phases(observations,asof=asof,collection_gaps=gaps)
    last=h["last_observation"]
    common={
        "status":"ABSTAIN","item_key":item_key,"asof_epoch":asof,
        "observed_current_phase":h["phase"],
        "observed_phase_onset":h["phase_onset"],
        "last_stock_change_epoch":None if last is None else last.epoch,
        "last_observed_quantity":None if last is None else last.quantity,
        "provider_source":None if last is None else last.source,
        "last_item_change_age_seconds":(
            None if last is None else asof-last.epoch),
        "completed_stocked_phase_count":len(h["stocked_durations"]),
        "completed_depleted_phase_count":len(h["depleted_durations"]),
        "scenario_count":scenarios,
        "country_specific_source_update_verified":False,
        "scores_are_calibrated_probabilities":False,
    }
    if last is None or h["phase"] not in ("HIGH","LOW"):
        return dict(common,status="UNKNOWN_OBSERVED_STATE")
    if h["phase_onset"] is None:
        return dict(common,status="CURRENT_PHASE_ONSET_UNKNOWN")
    if (asof-last.epoch>MAX_LAST_CHANGE_AGE_SECONDS
        or asof-last.epoch<0):
        return dict(common,status="ITEM_CHANGE_OBSERVATION_TOO_OLD")
    phase_age=asof-int(h["phase_onset"])
    if phase_age<0:
        raise AssertionError("phase age must not be negative")
    durations={
        "HIGH":[int(x) for x in h["stocked_durations"] if int(x)>=STEP],
        "LOW":[int(x) for x in h["depleted_durations"] if int(x)>=STEP],
    }
    if any(len(v)<MIN_PHASES for v in durations.values()):
        return dict(common,status="INSUFFICIENT_COMPLETED_PHASES")
    phase=h["phase"]
    survivors=[v-phase_age for v in durations[phase] if v>phase_age]
    if len(survivors)<MIN_PHASES:
        return dict(common,status="INSUFFICIENT_SURVIVING_PHASE_ANALOGS")
    flight=TRAVEL_SECONDS["uni"]
    offsets=[flight+d for d in range(0,MAX_WAIT+1,STEP)]
    horizon=offsets[-1]+GRACE
    rng=random.Random(seed+asof%100003)
    counts=[0]*len(offsets)
    for _ in range(scenarios):
        position=float(rng.choice(survivors))
        state=phase
        stocked_intervals=[]
        if state=="HIGH":
            stocked_intervals.append((0.,position))
        loops=0
        while position<=horizon:
            loops+=1
            if loops>1000:
                raise RuntimeError("unbounded empirical cycle simulation")
            state="LOW" if state=="HIGH" else "HIGH"
            length=rng.choice(durations[state])
            if state=="HIGH":
                stocked_intervals.append((position,position+length))
            position+=length
        for j,offset in enumerate(offsets):
            if any(begin-GRACE<=offset<end
                   for begin,end in stocked_intervals):
                counts[j]+=1
    scores=[round(x/scenarios,8) for x in counts]
    return dict(
        common,status="ISSUED_TWO_PHASE_SCENARIO_CURVE",
        observed_phase_age_seconds=phase_age,
        remaining_phase_analogs=len(survivors),
        delay_seconds=list(range(0,MAX_WAIT+1,STEP)),
        arrival_epochs=[asof+x for x in offsets],
        scores=scores,
        score_at_immediate_departure=scores[0],
        score_min=min(scores),score_max=max(scores),
        score_distinct_count=len(set(scores))
    )


def earliest_credible(curve,*,score_floor=SCORE_FLOOR,
                      min_consecutive=MIN_CONSECUTIVE):
    """Earliest qualifying departure, whether now or later; no special bias."""
    if (not 0<=score_floor<=1
        or type(min_consecutive) is not int
        or not 1<=min_consecutive<=12):
        raise ValueError("invalid predeclared confidence gate")
    if curve["status"]!="ISSUED_TWO_PHASE_SCENARIO_CURVE":
        return {"status":"ABSTAIN_"+curve["status"],
                "departure":None,"arrival":None,"score":None}
    ds=curve["delay_seconds"]
    xs=curve["scores"]
    if len(ds)!=len(xs) or not xs or ds[0]!=0:
        raise AssertionError("invalid score grid")
    for i in range(len(xs)-min_consecutive+1):
        if all(xs[i+k]>=score_floor and
               ds[i+k]==ds[i]+k*STEP
               for k in range(min_consecutive)):
            departure=curve["asof_epoch"]+ds[i]
            return {
                "status":(
                    "EARLIEST_NOW" if ds[i]==0
                    else "EARLIEST_WAIT_SUPPORTED"),
                "departure":departure,
                "arrival":departure+TRAVEL_SECONDS["uni"],
                "wait_seconds":ds[i],
                "score":xs[i],
            }
    return {
        "status":"NO_QUALIFYING_DEPARTURE_IN_EIGHT_HOURS",
        "departure":None,"arrival":None,"score":None}


def issued_research_record(item_key,observations,gaps,*,issued,
                           forecaster=phase_survival_curve,
                           choose=earliest_credible):
    curve=forecaster(observations,item_key,asof=issued,gaps=gaps)
    chosen=choose(curve)
    departure=chosen["departure"]
    if departure is not None and not issued<=departure<=issued+MAX_WAIT:
        raise AssertionError("invalid departure bound")
    return {
        "item_key":item_key,"issued_epoch":issued,"policy_id":POLICY_ID,
        "status":curve["status"],
        "phase":curve.get("observed_current_phase"),
        "phase_onset":curve.get("observed_phase_onset"),
        "provider_source":curve.get("provider_source"),
        "last_item_change_age_seconds":curve.get(
            "last_item_change_age_seconds"),
        "last_observed_quantity":curve.get("last_observed_quantity"),
        "baseline_leave_now_departure":issued,
        "baseline_leave_now_arrival":issued+TRAVEL_SECONDS["uni"],
        "projected_arrival_score_leave_now":curve.get(
            "score_at_immediate_departure"),
        "earliest_departure":departure,
        "earliest_arrival":chosen["arrival"],
        "wait_minutes":(
            round((departure-issued)/60,2)
            if departure is not None else None),
        "projected_arrival_score_earliest":chosen["score"],
        "decision_status":chosen["status"],
        "research_departure_state":(
            "ABSTAIN" if departure is None else
            "RESEARCH_NOW" if departure==issued else
            "RESEARCH_READY_WITHIN_5M" if departure-issued<=STEP else
            "RESEARCH_FUTURE_WATCH_NOT_EXECUTABLE"),
        "score_floor":SCORE_FLOOR,
        "two_adjacent_5m_bins_required":True,
        "score_distinct_count":curve.get("score_distinct_count"),
        "history_completed_low_count":curve.get(
            "completed_depleted_phase_count"),
        "history_completed_high_count":curve.get(
            "completed_stocked_phase_count"),
        "country_provider_freshness_verified":False,
        "no_arrival_truth_access_before_issue":True,
        "recommendation_not_published":True,
        "actual_gameplay_departure_verified":False,
    }


def canonical_paths(*,source=SOURCE,sidecar=SIDECAR,enforce=True):
    src=Path(source).resolve(strict=True)
    dst=Path(sidecar)
    root=ROOT if enforce else dst.parent
    if not root.is_dir():
        raise ValueError("approved research storage directory missing")
    private=root.resolve(strict=True)
    if (src==dst.resolve(strict=False) or dst.is_symlink()
        or dst.resolve(strict=False).parent!=private
        or (enforce and (src!=Path(SOURCE).resolve(strict=True)
                        or dst.resolve(strict=False)!=SIDECAR))):
        raise ValueError("invalid collector or isolated research sidecar")
    if enforce and not approved_collector_source(src):
        raise ValueError("unapproved collector")
    if dst.exists() and not dst.is_file():
        raise ValueError("sidecar is not a regular file")
    return src,dst


def source_readonly(path):
    p=Path(path).resolve(strict=True)
    con=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=15)
    con.execute("PRAGMA query_only=ON")
    return con


def write_private_sidecar(path,rows):
    if Path(path).is_symlink():
        raise ValueError("symlink sidecar prohibited")
    con=sqlite3.connect(str(path),timeout=15)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS v125_issued(
            id INTEGER PRIMARY KEY,
            item_key TEXT NOT NULL,
            issued_epoch INTEGER NOT NULL,
            policy_id TEXT NOT NULL,
            phase TEXT,
            phase_onset INTEGER,
            decision_status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(item_key,issued_epoch,policy_id)
        )""")
        for item in sorted(rows):
            r=rows[item]
            con.execute("""INSERT OR IGNORE INTO v125_issued(
                item_key,issued_epoch,policy_id,phase,
                phase_onset,decision_status,payload_json
            ) VALUES (?,?,?,?,?,?,?)""",
                (item,int(r["issued_epoch"]),POLICY_ID,
                 r["phase"],r["phase_onset"],
                 r["decision_status"],json.dumps(r,sort_keys=True)))
        con.commit()
        os.chmod(path,0o600)
    finally:
        con.close()


def observe(*,source=SOURCE,sidecar=SIDECAR,now=None,
            record=False,enforce=True):
    now=int(time.time() if now is None else now)
    src,dst=canonical_paths(source=source,sidecar=sidecar,enforce=enforce)
    with closing(source_readonly(src)) as collector:
        hb=read_heartbeat(collector)
        hb_age=None if hb is None else now-hb
        ok=hb_age is not None and 0<=hb_age<=GLOBAL_HEARTBEAT_AGE_LIMIT
        rows={}
        for country,item in (TARGETS["redfox"],TARGETS["nessie"]):
            item_key=f"{country}:{item}"
            if not ok:
                rows[item_key]={
                    "item_key":item_key,"issued_epoch":now,
                    "policy_id":POLICY_ID,"phase":None,
                    "phase_onset":None,
                    "decision_status":"GLOBAL_HEARTBEAT_STALE",
                    "status":"GLOBAL_HEARTBEAT_STALE",
                    "country_provider_freshness_verified":False,
                    "baseline_leave_now_departure":now,
                    "baseline_leave_now_arrival":
                        now+TRAVEL_SECONDS["uni"],
                    "earliest_departure":None,"earliest_arrival":None,
                    "wait_minutes":None}
                continue
            obs,gaps=read_collector_item(collector,country,item)
            rows[item_key]=issued_research_record(
                item_key,obs,gaps,issued=now)
    if record:
        write_private_sidecar(dst,rows)
    return {
        "status":"V125_PRIVATE_RESEARCH_RECORDED" if record
                 else "V125_PREVIEW_NO_WRITES",
        "global_heartbeat_age_seconds":hb_age,
        "country_provider_freshness_verified":False,
        "collector_written":False,
        "website_changed":False,
        "research_only":True,
        "as_issued_model_recommendations":rows,
        "sidecar_path":str(dst) if record else None,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument("--preview",action="store_true")
    mode.add_argument("--record",action="store_true")
    a=p.parse_args()
    print(json.dumps(observe(record=a.record),sort_keys=True))


if __name__=="__main__":
    main()
