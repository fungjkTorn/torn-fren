"""Research-only original V19 live inference for three frozen flower champions.

The V19 historical engine is run unchanged with bounded read-only history.
V20 traj12 and the seven bespoke plushie engines are NOT substituted with V19.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.frozen_candidate_worker_v31 import (
    inspect_live_source, _install_frozen_readonly_history,
)

V19_APPROVED = {
    "jap:Cherry Blossom": "dyn2",
    "sou:African Violet": "dyn7",
    "swi:Edelweiss": "dyn9",
}
MAX_WAIT = 28800
REPLAN_STEP = 300
DEPARTURE_GRID = 300
MIN_QUANTITY = 30
GRACE = 10


def predict(db: str | Path, country: str, item: str, now: int) -> dict:
    country=country.strip().lower()
    item=item.strip()
    now=int(now)
    key=f"{country}:{item}"
    expected=V19_APPROVED.get(key)
    if not expected:
        return {"status": "NOT_APPROVED_FROZEN_V19_V38"}
    source=inspect_live_source(db,now)
    if source["status"]!="FRESH":
        return {"status":source["status"]}
    from services import history_service
    from services import plushie_flower_dynamic_planner_v19 as engine
    _install_frozen_readonly_history(history_service,db)
    cfg=next((x for x in engine.configs() if x.name==expected),None)
    if cfg is None:
        return {"status":"FROZEN_V19_CONFIG_UNAVAILABLE"}
    cleaned,cycles,_bounces,gaps=engine.load_item(country,item,MIN_QUANTITY)
    normalized_gaps=engine.normalize_gaps(history_service.get_collection_gaps())
    timeline=engine.Timeline(cleaned,cycles,MIN_QUANTITY,gaps=normalized_gaps)
    deps,features=engine.completed_cycle_features(cycles,gaps=normalized_gaps)
    points=engine.build_points(timeline,deps,features,600)
    if len(points)<60:
        return {"status":"INSUFFICIENT_HISTORICAL_FEATURES"}
    travel=int(engine.TRAVEL_SECONDS[country])
    proposal=engine.plan(
        float(now),points,[p.t for p in points],timeline,
        deps,features,cfg,list(range(0,MAX_WAIT+1,DEPARTURE_GRID)),
        travel,GRACE,
    )
    if proposal is None:
        return {"status":"NO_RECOMMENDATION","model_generation":"V19",
                "model_config":cfg.name}
    dep=int(proposal["departure_time"])
    if dep<now or dep>now+MAX_WAIT:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    return {
        "status":"RESEARCH_PROPOSAL_ONLY",
        "model_generation":"V19",
        "model_config":cfg.name,
        "key":key,
        "query_timestamp":now,
        "recommended_departure_timestamp":dep,
        "recommended_arrival_timestamp":dep+travel,
        "replan_step_seconds":REPLAN_STEP,
        "research_horizon_seconds":MAX_WAIT,
        "quantity_threshold":MIN_QUANTITY,
        "grace_seconds":GRACE,
        "probability_calibrated":False,
        "gameplay_automated":False,
        "source":"FROZEN_V19_ORIGINAL_ENGINE_SINGLE_TICK",
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--country",required=True)
    p.add_argument("--item",required=True)
    p.add_argument("--now",required=True,type=int)
    args=p.parse_args()
    try:
        result=predict(args.db,args.country,args.item,args.now)
    except Exception as exc:
        result={"status":"V38_NATIVE_ERROR","error_type":type(exc).__name__}
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
