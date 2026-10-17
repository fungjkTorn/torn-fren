"""Research-only original V20 traj12 China Peony live single tick.

Uses the actual V20 trajectory engine restored from the frozen research branch,
NOT the older V19 approximation. Causal stock source and immutable read-only DB.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.frozen_candidate_worker_v31 import (
    inspect_live_source,_install_frozen_readonly_history,
)

KEY="chi:Peony"
CONFIG="traj12"
MAX_WAIT=28800
STEP=300
GRACE=10
MIN_QTY=30


def predict(db: str|Path,country:str,item:str,now:int)->dict:
    country=country.strip().lower();item=item.strip();now=int(now)
    if f"{country}:{item}"!=KEY:
        return {"status":"NOT_APPROVED_PEONY_V20"}
    source=inspect_live_source(db,now)
    if source["status"]!="FRESH":
        return {"status":source["status"]}
    from services import history_service
    from services import plushie_flower_dynamic_planner_v20 as engine
    _install_frozen_readonly_history(history_service,db)
    cfg=next((x for x in engine.configs() if x.name==CONFIG),None)
    if cfg is None:
        return {"status":"FROZEN_TRAJ12_CONFIG_UNAVAILABLE"}
    cleaned,cycles,_bounces,gaps=engine.load_item(country,item,MIN_QTY)
    gap_ranges=engine.normalize_gaps(history_service.get_collection_gaps())
    timeline=engine.Timeline(cleaned,cycles,MIN_QTY,gaps=gap_ranges)
    deps,features=engine.completed_cycle_features(cycles,gaps=gap_ranges)
    points=engine.build_points(timeline,deps,features,600)
    if len(points)<60:
        return {"status":"INSUFFICIENT_HISTORICAL_FEATURES"}
    travel=int(engine.TRAVEL_SECONDS[country])
    proposal=engine.plan(float(now),points,[p.t for p in points],timeline,
                         deps,features,cfg,list(range(0,MAX_WAIT+1,STEP)),
                         travel,GRACE)
    if proposal is None:
        return {"status":"NO_RECOMMENDATION","model_generation":"V20",
                "model_config":CONFIG}
    dep=int(proposal["departure_time"])
    if dep<now or dep>now+MAX_WAIT:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    return {
        "status":"RESEARCH_PROPOSAL_ONLY",
        "model_generation":"V20",
        "model_config":CONFIG,
        "key":KEY,
        "query_timestamp":now,
        "recommended_departure_timestamp":dep,
        "recommended_arrival_timestamp":dep+travel,
        "replan_step_seconds":STEP,
        "research_horizon_seconds":MAX_WAIT,
        "quantity_threshold":MIN_QTY,
        "grace_seconds":GRACE,
        "probability_calibrated":False,
        "gameplay_automated":False,
        "source":"FROZEN_V20_ORIGINAL_TRAJECTORY_ENGINE_SINGLE_TICK",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--country",required=True)
    p.add_argument("--item",required=True)
    p.add_argument("--now",required=True,type=int)
    a=p.parse_args()
    try:
        result=predict(a.db,a.country,a.item,a.now)
    except Exception as exc:
        result={"status":"V38_PEONY_ERROR","error_type":type(exc).__name__}
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":main()
