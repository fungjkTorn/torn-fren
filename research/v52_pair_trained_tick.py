"""V52 isolated Lion/Panda trained-selector research tick; NEVER publishes.

Requires an exact SHA256 pin for a reviewed local JSON artifact created by
v50_pair_selector_artifact. No pickle. Historical training and VM admission
are separate manual gates. The old 19-model scheduler is not modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from services.frozen_candidate_worker_v31 import inspect_live_source
from research.plushie_champions.common import (
    ResearchContext, AnalogPlanner, STEP, MAX_WAIT, MIN_QTY,
    GRACE, TRAVEL_SECONDS,
)
from research.v49_lion_panda_pair_probe import TARGETS,original_features
from research.v50_pair_selector_artifact import (
    SCHEMA,FEATURES,choose_from_features,
)

MAX_ARTIFACT_BYTES=2097152


def load_pinned_artifact(path,expected_digest,target):
    if target not in TARGETS:
        raise ValueError("unsupported target")
    if not re.fullmatch("[0-9a-f]{64}",str(expected_digest)):
        raise ValueError("required reviewed SHA256 pin absent")
    p=Path(path).resolve(strict=True)
    if p.suffix!=".json" or p.stat().st_size>MAX_ARTIFACT_BYTES:
        raise ValueError("not a small JSON selector artifact")
    blob=p.read_bytes()
    digest=hashlib.sha256(blob.rstrip(b"\r\n")).hexdigest()
    if digest!=expected_digest:
        raise ValueError("ARTIFACT_HASH_MISMATCH")
    data=json.loads(blob)
    config=TARGETS[target]
    if (data.get("schema")!=SCHEMA or
        data.get("research_only") is not True or
        data.get("approved_for_live") is not False or
        data.get("key")!=config["key"] or
        data.get("target")!=target or
        data.get("feature_names")!=list(FEATURES[target]) or
        data.get("expert_a")!=list(config["expert_a"]) or
        data.get("expert_b")!=list(config["expert_b"]) or
        data.get("winning_selector")!=config["selector"]):
        raise ValueError("ARTIFACT_CONTRACT_MISMATCH")
    return data


def predict(db,target,now,artifact,digest,*,source_checker=inspect_live_source,
            context_builder=ResearchContext.build,
            planner_class=AnalogPlanner):
    if target not in TARGETS:
        raise ValueError("unsupported target")
    # Artifact hash validation is first: a stale or foreign artifact cannot
    # cause expensive stock history inspection or output candidate timings.
    model=load_pinned_artifact(artifact,digest,target)
    now=int(now)
    state=source_checker(db,now)
    if state.get("status")!="FRESH":
        return {"status":state.get("status","NO_COLLECTOR_HEARTBEAT"),
                "key":TARGETS[target]["key"]}
    config=TARGETS[target]
    country,item=config["key"].split(":",1)
    q=(now//STEP)*STEP
    ctx=context_builder(db,asof=now,readonly=True)
    try:
        if not len(ctx.grid) or q>ctx.grid[-1]:
            return {"status":"CONTEXT_UNAVAILABLE","key":config["key"]}
        choices={}
        for name in ("a","b"):
            k,weight=config["expert_"+name]
            planner=planner_class(ctx,country,item,k=k,
                                  global_weight=weight,cutoff=q)
            choices[name]=planner.plan(float(q))
        features=original_features(ctx,country,item,float(q),
                                   choices["a"],choices["b"],target)
        if list(features)!=list(FEATURES[target]):
            raise ValueError("SOURCE_FEATURE_ORDER_MISMATCH")
        choice_label=choose_from_features(model,features)
    finally:
        ctx.con.close()
    choice_name="b" if choice_label else "a"
    selected=choices[choice_name]
    base={
        "key":config["key"],
        "status":"RESEARCH_NOT_ADMITTED_CANDIDATE",
        "target":target,
        "selected_expert":choice_name,
        "selected_expert_config":config["expert_"+choice_name],
        "selector_artifact_sha256":digest,
        "training_asof":model["train_asof"],
        "replan_step_seconds":STEP,
        "quantity_threshold":MIN_QTY,
        "grace_seconds":GRACE,
        "research_horizon_seconds":MAX_WAIT,
        "probability_calibrated":False,
        "gameplay_automated":False,
        "published_to_website":False,
        "research_only":True,
        "source":"SOURCE_PINNED_ARTIFACT_SELECTOR_PENDING_VALIDATION",
    }
    if selected is None:
        return {**base,"candidate_status":"SELECTED_EXPERT_ABSTAINED"}
    dep=int(selected[0])
    if not now<=dep<=now+MAX_WAIT:
        return {**base,"candidate_status":"DEPARTURE_OUT_OF_BOUNDS"}
    return {**base,"candidate_status":"BOUNDED_EXPERIMENTAL_TIMING",
            "computed_at":now,
            "research_departure_timestamp":dep,
            "research_arrival_timestamp":dep+TRAVEL_SECONDS[country]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--target",choices=tuple(TARGETS),required=True)
    p.add_argument("--now",required=True,type=int)
    p.add_argument("--artifact",required=True)
    p.add_argument("--artifact-sha256",required=True)
    a=p.parse_args()
    try:
        result=predict(a.db,a.target,a.now,a.artifact,a.artifact_sha256)
    except Exception as exc:
        result={"status":"V52_ARTIFACT_RESEARCH_ERROR",
                "error_type":type(exc).__name__,
                "published_to_website":False}
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
