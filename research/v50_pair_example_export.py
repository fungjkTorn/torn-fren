"""V50 OFFLINE source-derived resolved examples for Lion and Panda.

Historical data only. Build causal AnalogPlanner normalizations with cutoff
at each historical decision, then replay two expert outcomes until resolved.
This is NOT a reproduction of the champion's noncausal early split
normalization. Compare results with the original replay before any promotion.

Run on development PC, not the production VM. Each sample can be expensive.
Never publish example records or commit collector SQLite.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from research.plushie_champions.common import (
    ResearchContext, AnalogPlanner, valid_starts, selector_feature_dict,
    MAX_WAIT, GRACE, TRAVEL_SECONDS, DAY,
)
from research.v45_online_template_probe import simulate_one
from research.v49_lion_panda_pair_probe import TARGETS,original_features
from research.v50_pair_selector_artifact import FEATURES


def resolved_example(ctx,target,s,cutoff):
    cfg=TARGETS[target]
    country,item=cfg["key"].split(":",1)
    # Per-decision cutoff prevents training representations fitting future
    # feature statistics, unlike the original fixed-validation cutoff.
    ka,wa=cfg["expert_a"]
    kb,wb=cfg["expert_b"]
    pa=AnalogPlanner(ctx,country,item,ka,wa,cutoff=s)
    pb=AnalogPlanner(ctx,country,item,kb,wb,cutoff=s)
    a=pa.plan(float(s))
    b=pb.plan(float(s))
    d=original_features(ctx,country,item,float(s),a,b,target)
    if list(d)!=list(FEATURES[target]):
        raise ValueError("source feature ordering changed")
    timeline=ctx.timelines[(country,item)]
    travel=TRAVEL_SECONDS[country]
    oa=simulate_one(pa.plan,timeline,s,travel)
    ob=simulate_one(pb.plan,timeline,s,travel)
    # Explicit absent expert schedule is NOT an observed failure.
    if oa["status"]!="RESOLVED_EXPERT_DECISION":
        return None
    if ob["status"]!="RESOLVED_EXPERT_DECISION":
        return None
    resolved=max(oa["resolved_at"],ob["resolved_at"])
    if resolved>cutoff:
        return None
    fields={k:(float(v) if math.isfinite(float(v)) else None)
            for k,v in d.items()}
    return {
        "key":cfg["key"],
        "decision_ts":int(s),
        "feature_as_of":int(s),
        "resolved_at":int(resolved),
        "features":fields,
        "a_success":oa["success"],
        "b_success":ob["success"],
        "source":"SOURCE_PINNED_CAUSAL_ANALOG_EXPERTS",
        "normalization":"per_decision_cutoff",
        "research_only":True,
    }


def export(db,target,cutoff,output,*,max_starts=20):
    if target not in TARGETS:
        raise ValueError("unsupported target")
    if not 1<=max_starts<=10000:
        raise ValueError("invalid count")
    cutoff=int(cutoff)
    cfg=TARGETS[target]
    country,item=cfg["key"].split(":",1)
    ctx=ResearchContext.build(db,asof=cutoff,readonly=True)
    try:
        # valid_starts excludes unresolved maximum future paths.
        starts=[int(s) for s in valid_starts(ctx,country,item)
                if s+MAX_WAIT+TRAVEL_SECONDS[country]+GRACE<=cutoff]
        starts=starts[-max_starts:]
        if not starts:
            raise ValueError("no fully resolved historical anchors")
        path=Path(output)
        path.parent.mkdir(parents=True,exist_ok=True)
        count=0;disagreements=0
        # Checkpoint safely after every resolved outcome; interrupted
        # offline research is never silently treated as a complete dataset.
        with path.open("w",encoding="utf-8") as file:
            for s in starts:
                record=resolved_example(ctx,target,s,cutoff)
                if record is None:
                    continue
                count+=1
                disagreements+=int(record["a_success"]!=record["b_success"])
                file.write(json.dumps(record,allow_nan=False,sort_keys=True)+"\n")
                file.flush()
        return {"status":"OFFLINE_RESEARCH_EXAMPLES_EXPORTED",
                "item_key":cfg["key"],"attempted_starts":len(starts),
                "resolved_examples":count,"disagreements":disagreements,
                "output":str(path),"normalization":"per_decision_cutoff",
                "not_live_approved":True}
    finally:
        ctx.con.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--target",required=True,choices=tuple(TARGETS))
    p.add_argument("--train-asof",required=True,type=int)
    p.add_argument("--output",required=True)
    p.add_argument("--max-starts",type=int,default=20)
    a=p.parse_args()
    print(json.dumps(export(a.db,a.target,a.train_asof,
                            a.output,max_starts=a.max_starts),
                     sort_keys=True))

if __name__=="__main__":
    main()
