"""Research-only Red Fox original k18/global-regime-.5 analog single tick.

Uses all ten original plushie timelines, just like the frozen tournament.
This expensive cold-build is NOT added to the default VM scheduler until
representative source-validity, causal parity and memory/runtime checks pass.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from services.frozen_candidate_worker_v31 import inspect_live_source
from research.plushie_champions.common import (
    ResearchContext, AnalogPlanner, STEP, MAX_WAIT, MIN_QTY, GRACE,
    TRAVEL_SECONDS,
)

KEY="uni:Red Fox Plushie"
K=18
GLOBAL_WEIGHT=0.5


def predict(db: str|Path,country: str,item: str,now: int):
    country=country.strip().lower();item=item.strip();now=int(now)
    if f"{country}:{item}"!=KEY:
        return {"status":"NOT_APPROVED_RED_FOX_ANALOG"}
    source=inspect_live_source(db,now)
    if source["status"]!="FRESH":
        return {"status":source["status"]}
    ctx=ResearchContext.build(db)
    try:
        q=(now//STEP)*STEP
        if len(ctx.grid)==0 or q>ctx.grid[-1]:
            return {"status":"CROSS_ITEM_CONTEXT_LAGGING"}
        if now-ctx.grid[-1]>STEP+180:
            return {"status":"CROSS_ITEM_CONTEXT_STALE"}
        # Historical reference candidates must have their entire simulated
        # 8h departure/travel/grace path resolved before the as-of query.
        planner=AnalogPlanner(ctx,country,item,k=K,
                              global_weight=GLOBAL_WEIGHT,cutoff=q)
        recommendation=planner.plan(float(q))
    finally:
        ctx.con.close()
    if recommendation is None:
        return {"status":"NO_RECOMMENDATION","model_generation":"global_regime_analog"}
    dep=int(recommendation[0])
    if dep<now or dep>now+MAX_WAIT:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    return {
        "status":"RESEARCH_PROPOSAL_ONLY",
        "model_generation":"global_regime_analog",
        "model_config":"red_fox_k18_global_regime_0.5",
        "key":KEY,
        "query_timestamp":now,
        "recommended_departure_timestamp":dep,
        "recommended_arrival_timestamp":dep+TRAVEL_SECONDS[country],
        "replan_step_seconds":STEP,
        "research_horizon_seconds":MAX_WAIT,
        "quantity_threshold":MIN_QTY,
        "grace_seconds":GRACE,
        "probability_calibrated":False,
        "gameplay_automated":False,
        "source":"SOURCE_PINNED_RED_FOX_ANALOG_RESEARCH_ONLY",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--country",required=True)
    p.add_argument("--item",required=True)
    p.add_argument("--now",required=True,type=int)
    a=p.parse_args()
    try: output=predict(a.db,a.country,a.item,a.now)
    except Exception as e:
        output={"status":"V38_RED_FOX_ERROR","error_type":type(e).__name__}
    print(json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
