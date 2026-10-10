"""V49 read-only, source-pinned Lion/Panda two-expert cost/feature probe.

Evaluates EXACT original analog expert pair and selector feature dictionary on
one causally valid live query. Does not train a classifier or claim champion
status: the frozen LogisticRegression/ExtraTrees weights are NOT in the repo.

Never publishes a recommendation; never touches current 19 private models,
production collector, bot, website, or the V47/V48 caches.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

from services.frozen_candidate_worker_v31 import inspect_live_source
from research.plushie_champions.common import (
    ResearchContext, AnalogPlanner, selector_feature_dict, STEP,
    TRAVEL_SECONDS, MIN_QTY, GRACE, MAX_WAIT,
)

TARGETS = {
    "lion": {
        "key": "sou:Lion Plushie",
        "expert_a": (14, 0.35),
        "expert_b": (18, 0.50),
        "selector": "logistic class_weight=balanced max_iter=2000",
    },
    "panda": {
        "key": "chi:Panda Plushie",
        "expert_a": (16, 0.15),
        "expert_b": (18, 0.75),
        "selector": "ExtraTrees n_estimators=300 depth=3 min_samples_leaf=3 class_weight=balanced random_state=2",
    },
}


def original_features(ctx,country,item,q,pa,pb,target):
    """Mirror each source-pinned champion's exact selector feature ordering."""
    d=selector_feature_dict(ctx,country,item,q,pa,pb)
    if target=="panda":
        d["g2_g6"]=d["g2"]/d["g6"] if d["g6"] else 1.0
        d["g6_g18raw"]=d["g6"]/d["g18"] if d["g18"] else 1.0
        d["rL_g18raw"]=d["rL"]/d["g18"] if d["g18"] else 1.0
        d["prob_gap"]=d["B_prob"]-d["A_prob"]
        d["rob_gap"]=d["B_rob"]-d["A_rob"]
    return d


def infer(db,target,now,*,source_checker=inspect_live_source,
          context_builder=ResearchContext.build,
          planner_class=AnalogPlanner):
    if target not in TARGETS:
        raise ValueError("not approved Lion/Panda expert target")
    now=int(now)
    config=TARGETS[target]
    country,item=config["key"].split(":",1)
    source=source_checker(db,now)
    if source.get("status")!="FRESH":
        return {"status":source.get("status","COLLECTOR_UNVERIFIED"),
                "key":config["key"]}
    q=int((now//STEP)*STEP)
    start=time.monotonic()
    ctx=context_builder(db,asof=now,readonly=True)
    try:
        if not len(ctx.grid) or q>ctx.grid[-1]:
            return {"status":"CONTEXT_UNAVAILABLE","key":config["key"]}
        results={}
        choices={}
        for name in ("a","b"):
            k,gw=config["expert_"+name]
            t0=time.monotonic()
            model=planner_class(ctx,country,item,k=k,global_weight=gw,
                                cutoff=q)
            choice=model.plan(float(q))
            choices[name]=choice
            elapsed=round(time.monotonic()-t0,3)
            if choice is None:
                results[name]={"status":"NO_RECOMMENDATION",
                               "k":k,"global_regime_weight":gw,
                               "elapsed_seconds":elapsed}
            else:
                dep=int(choice[0])
                results[name]={
                    "status":"EXPERT_PROPOSAL_ONLY" if now<=dep<=now+MAX_WAIT
                             else "EXPERT_OUT_OF_BOUNDS",
                    "k":k,"global_regime_weight":gw,
                    "departure_timestamp":dep,
                    "arrival_timestamp":dep+TRAVEL_SECONDS[country],
                    "uncalibrated_analog_probability":float(choice[1]),
                    "uncalibrated_robust_score":float(choice[2]),
                    "elapsed_seconds":elapsed,
                }
        t0=time.monotonic()
        features=original_features(ctx,country,item,float(q),
                                   choices["a"],choices["b"],target)
        arr=np.array(list(features.values()),dtype=float)
        feature_seconds=round(time.monotonic()-t0,3)
        if not np.all(np.isfinite(arr)):
            return {"status":"NONFINITE_FEATURES_REJECTED",
                    "key":config["key"],
                    "feature_keys":list(features),
                    "source":"ORIGINAL_SELECTOR_FEATURES"}
    finally:
        ctx.con.close()
    return {
        "status":"SELECTOR_WEIGHTS_MISSING_NOT_PUBLISHED",
        "key":config["key"],"model_generation":"two_expert_ml_selector",
        "original_selector":config["selector"],
        "experts":results,
        "feature_names":list(features),
        "feature_count":len(features),
        "feature_seconds":feature_seconds,
        "total_elapsed_seconds":round(time.monotonic()-start,3),
        "replan_step_seconds":STEP,"research_horizon_seconds":MAX_WAIT,
        "quantity_threshold":MIN_QTY,"grace_seconds":GRACE,
        "probability_calibrated":False,
        "gameplay_automated":False,"research_only":True,
        "published_to_website":False,
        "source":"SOURCE_PINNED_LION_PANDA_TWO_EXPERT_DIAGNOSTIC",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--target",choices=tuple(TARGETS),required=True)
    p.add_argument("--now",type=int,required=True)
    a=p.parse_args()
    try:
        result=infer(a.db,a.target,a.now)
    except Exception as e:
        result={"status":"V49_DIAGNOSTIC_ERROR",
                "error_type":type(e).__name__}
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
