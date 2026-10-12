"""V124 opt-in one-tick PROSPECTIVE V123 foreign-stock survival shadow.

Run this AFTER real collector writes occur, once every five minutes at most.
Default --preview performs ZERO writes. Explicit --record writes only to
/var/lib/torn-fren-v38/v124_survival_shadow.db. NO service/timer installed.

For Red Fox and Nessie separately, detect a recent actual collector-observed
>=30 to <30 threshold depletion, require uninterrupted source segment, an
up-to-date global heartbeat (NOT country-specific freshness), and at least
5 prior completed stocked/depleted phases. Predict using only item stock
observations already persisted at issue time. Convert the V123 5m predicted
arrival scores from its latest observed input epoch onto the ACTUAL wall-clock
issue grid, retaining the 106m flight and <=8h wait. Log leave-now alongside
challenger. Distinguish NOW, WATCH_GT_5M, READY_WITHIN_5M, ABSTAIN.

Recorder deduplicates one first issue per (item,observed depletion epoch);
later repeated queries only record operational attempts, not training
targets. It NEVER retrospectively backfills unissued forecasts or queries
arrival evidence while deciding. A separate read-only analysis should score
mature arrivals later, and only after country-update freshness exists should
arrival precision be claimed.

No API calls, gameplay actions, production DB write, provider intervention,
model champion substitution, or website publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS,MAX_WAIT,STEP
from research.v107_explicit_restock_cycle_baseline import completed_phases
from research.v109_raw_restock_transition_event_audit import (
    SOURCE, TARGETS, read_collector_item
)
from research.v123_empirical_phase_survival_challenger import (
    empirical_survival_curve,choose_departure,SCENARIOS,SEED,
    MIN_SCORE,MIN_LIFT,MIN_CONSECUTIVE
)
from research.v60_private_snapshot_probe import (
    approved_collector_source,read_heartbeat
)

ROOT=Path("/var/lib/torn-fren-v38")
SIDECAR=ROOT/"v124_survival_shadow.db"
RECENT_DEPLETION_LIMIT=600
RECENT_GLOBAL_HEARTBEAT_LIMIT=180
SCHEMA_VERSION=1
POLICY_ID="v124_v123_survival_128_060_015_two_point"
ITEMS=tuple(
    f"{country}:{item}"
    for country,item in (TARGETS["redfox"], TARGETS["nessie"])
)
MAX_ITEM_SOURCE_ROWS=50000


def readonly(path):
    p=Path(path).resolve(strict=True)
    db=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=10)
    db.execute("PRAGMA query_only=ON")
    return db


def parse_and_align(curve,*,issued,model_asof):
    """Map original observed-event-grid curves to actual issue-time grid.

    Linear interpolation is ONLY between previously predicted scores.
    If issue-time grid extends beyond the V123 8h source horizon,
    unscored tail is excluded; do not extrapolate hidden future scores.
    """
    if curve["status"]!="EMPIRICAL_STOCK_SURVIVAL_CURVE":
        return curve
    age=issued-model_asof
    if not 0<=age<=RECENT_DEPLETION_LIMIT:
        raise ValueError("stale/negative issue vs model prediction epoch")
    delays=curve["delay_seconds"]
    scores=curve["scores"]
    if len(delays)!=len(scores) or delays[0]!=0:
        raise AssertionError("invalid source score curve")
    target_ds=[]
    target_scores=[]
    for d in range(0,MAX_WAIT+1,STEP):
        query=d+age
        if query>delays[-1]:
            break
        j=min(int(query//STEP),len(scores)-1)
        if j==len(scores)-1:
            probability=float(scores[j])
        else:
            alpha=(query-delays[j])/STEP
            probability=(1-alpha)*scores[j]+alpha*scores[j+1]
        if not 0<=probability<=1:
            raise AssertionError("nonsensical interpolated score")
        target_ds.append(d)
        target_scores.append(round(probability,8))
    if not target_ds:
        return dict(curve,status="NO_REMAINING_ISSUED_ARRIVAL_HORIZON")
    return dict(
        curve,
        delay_seconds=target_ds,
        scores=target_scores,
        immediate_arrival_score=target_scores[0],
        issued_at_epoch=issued,
        model_last_known_stock_epoch=model_asof,
        score_alignment_age_seconds=age,
        scores_recalibrated=False,
    )


def proposal(item_key,observations,gaps,*,issued,
             forecaster=empirical_survival_curve,
             select=choose_departure):
    """Preview a source-pinned depletion proposal; no sidecar/network calls."""
    common={
        "item_key":item_key,"issued_at":int(issued),
        "policy_id":POLICY_ID,
        "source_country_age_verified":False,
        "actual_travel_or_purchase_verified":False,
        "raw_score_calibrated":False,
        "model_family":"v123_empirical_phase_survival",
        "provider_source":None,"depletion_epoch":None,
        "baseline_departure":int(issued),
        "baseline_arrival":int(issued)+TRAVEL_SECONDS["uni"],
        "recommended_departure":None,"recommended_arrival":None,
        "scheduled_status":"ABSTAIN",
        "arrival_truth_status":"NOT_YET_OBSERVED",
    }
    if len(observations)>MAX_ITEM_SOURCE_ROWS:
        return dict(common,status="TOO_MANY_STOCK_ROWS_FAIL_CLOSED")
    if not observations:
        return dict(common,status="NO_STOCK_HISTORY")
    last=observations[-1]
    if last.epoch>issued:
        return dict(common,status="FUTURE_STOCK_ROW_REJECTED")
    source=last.source
    common["provider_source"]=source
    if not source:
        return dict(common,status="UNKNOWN_SOURCE")
    history=completed_phases(observations,asof=last.epoch,
                             collection_gaps=gaps)
    anchor=history["phase_onset"]
    common["depletion_epoch"]=anchor
    if history["phase"]!="LOW" or anchor is None:
        return dict(common,status="NO_CONFIRMED_DEPLETION_EVENT")
    event_age=issued-int(anchor)
    if not 0<=event_age<=RECENT_DEPLETION_LIMIT:
        return dict(common,status="DEPLETION_TOO_OLD")
    if issued-last.epoch>RECENT_DEPLETION_LIMIT:
        return dict(common,status="ITEM_SOURCE_ROW_TOO_OLD")
    # Read-only forecasting on actual persisted change-only history.
    curve=forecaster(
        observations,item_key,asof=last.epoch,gaps=gaps)
    if curve["status"]!="EMPIRICAL_STOCK_SURVIVAL_CURVE":
        return dict(common,status=curve["status"],
                    historical_completed_lows=curve.get(
                        "past_completed_depleted_phases"),
                    historical_completed_highs=curve.get(
                        "past_completed_stocked_phases"))
    aligned=parse_and_align(curve,issued=issued,model_asof=last.epoch)
    decision=select(aligned,asof=issued)
    departure=decision["departure"]
    if departure is not None and not issued<=departure<=issued+MAX_WAIT:
        raise AssertionError("selected future action outside 8h horizon")
    status=(
        "ABSTAIN" if departure is None else
        "LEAVE_NOW" if departure==issued else
        "READY_WITHIN_5M" if departure-issued<=STEP else
        "WATCH_GT_5M_NOT_EXECUTABLE_AT_ISSUE"
    )
    return {
        **common,
        "status":"ISSUED_MODEL_FORECAST",
        "scheduled_status":status,
        "recommended_departure":departure,
        "recommended_arrival":(
            departure+TRAVEL_SECONDS["uni"] if departure is not None
            else None),
        "raw_scenario_score_now":aligned.get(
            "immediate_arrival_score"),
        "raw_scenario_score_chosen":decision.get("score"),
        "model_decision_status":decision["status"],
        "model_last_observation_epoch":last.epoch,
        "last_obs_age_seconds":issued-last.epoch,
        "observed_depletion_age_seconds":event_age,
        "completed_lows":len(history["depleted_durations"]),
        "completed_highs":len(history["stocked_durations"]),
        "scenario_count":SCENARIOS,
        "score_floor":MIN_SCORE,
        "minimum_delayed_lift":MIN_LIFT,
        "minimum_consecutive_points":MIN_CONSECUTIVE,
        "score_curve_source_grid_points":len(curve["scores"]),
        "score_curve_issued_grid_points":len(aligned["scores"]),
        "score_curve_unique_values":len(set(aligned["scores"])),
        "model_evidence_only_persisted_by_issued_at":True,
    }


def preflight(*,source=SOURCE,sidecar=SIDECAR,
              enforce_canonical=True):
    src=Path(source).resolve(strict=True)
    root=ROOT if enforce_canonical else Path(sidecar).parent
    if not root.is_dir():
        raise ValueError("approved private research directory unavailable")
    root=root.resolve(strict=True)
    dst=Path(sidecar)
    if (src==dst.resolve(strict=False)
        or dst.is_symlink()
        or dst.resolve(strict=False).parent!=root
        or (enforce_canonical and
            (src!=Path(SOURCE).resolve(strict=True) or
             dst.resolve(strict=False)!=SIDECAR))):
        raise ValueError("outside pinned isolated research storage")
    if enforce_canonical and not approved_collector_source(src):
        raise ValueError("not approved collector source")
    if dst.exists() and not dst.is_file():
        raise ValueError("output exists and is not a regular file")
    return src,dst


def observe(*,source=SOURCE,sidecar=SIDECAR,issued=None,
            record=False,enforce_canonical=True):
    issued=int(time.time() if issued is None else issued)
    src,dst=preflight(source=source,sidecar=sidecar,
                      enforce_canonical=enforce_canonical)
    results={}
    with closing(readonly(src)) as db:
        latest=read_heartbeat(db)
        age=None if latest is None else issued-int(latest)
        heartbeat_ok=age is not None and 0<=age<=RECENT_GLOBAL_HEARTBEAT_LIMIT
        for name,(country,item) in TARGETS.items():
            key=f"{country}:{item}"
            if not heartbeat_ok:
                results[key]={
                    "status":"GLOBAL_COLLECTOR_HEARTBEAT_STALE",
                    "item_key":key,"issued_at":issued,
                    "depletion_epoch":None,
                    "baseline_departure":issued,
                    "baseline_arrival":issued+TRAVEL_SECONDS["uni"],
                    "recommended_departure":None,
                    "recommended_arrival":None,
                    "source_country_age_verified":False,
                }
                continue
            obs,gaps=read_collector_item(db,country,item)
            results[key]=proposal(key,obs,gaps,issued=issued)
    if record:
        with closing(open_writer(dst)) as writer:
            for key in sorted(results):
                save_attempt(writer,results[key])
            writer.commit()
    return {
        "status":"V124_SHADOW_RECORDED" if record
                 else "V124_PREVIEW_NO_WRITES",
        "research_only":True,
        "collector_written":False,
        "website_published":False,
        "champions_changed":False,
        "provider_country_freshness_verified":False,
        "global_heartbeat_age_seconds":age,
        "local_forecast_evaluation_issued_epoch":issued,
        "sidecar":str(dst) if record else None,
        "items":results,
    }


def open_writer(path):
    # CLI calls preflight before writing. This function is testable with a
    # temp fixture but is never called on source collector DB.
    path=Path(path)
    if path.is_symlink():
        raise ValueError("refuse link sidecar")
    db=sqlite3.connect(str(path),timeout=10)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("""CREATE TABLE IF NOT EXISTS v124_issue_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_key TEXT NOT NULL,
        tick_epoch INTEGER NOT NULL,
        status TEXT NOT NULL,
        depletion_epoch INTEGER,
        UNIQUE(item_key,tick_epoch)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS v124_forecasts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_key TEXT NOT NULL,
        depletion_epoch INTEGER NOT NULL,
        issued_epoch INTEGER NOT NULL,
        policy_id TEXT NOT NULL,
        provider_source TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        UNIQUE(item_key,depletion_epoch,policy_id)
    )""")
    if not path.exists():
        raise AssertionError("SQLite sidecar not created")
    os.chmod(path,0o600)
    return db


def save_attempt(db,record):
    item=record["item_key"]
    issue=int(record["issued_at"])
    event=record.get("depletion_epoch")
    db.execute(
        """INSERT OR IGNORE INTO v124_issue_attempts(
        item_key,tick_epoch,status,depletion_epoch) VALUES (?,?,?,?)""",
        (item,issue,record["status"],event))
    if record["status"]=="ISSUED_MODEL_FORECAST":
        db.execute(
            """INSERT OR IGNORE INTO v124_forecasts(
            item_key,depletion_epoch,issued_epoch,policy_id,
            provider_source,payload_json) VALUES (?,?,?,?,?,?)""",
            (item,int(event),issue,POLICY_ID,
             record["provider_source"],json.dumps(record,sort_keys=True))
        )


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument("--preview",action="store_true",
                      help="Default, never write even to private sidecar")
    mode.add_argument("--record",action="store_true",
                      help="Opt-in private sidecar only; no services installed")
    args=p.parse_args()
    output=observe(record=args.record)
    print(json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
