"""V35 isolated frozen V18 flower/plushie champion single-tick inference.

Only the precisely approved Heather and Wolverine V18 configurations. The
original frozen V18 planner is used unchanged; all history is bound to a
read-only SQLite child. The public V2 website and bot never import this as
a prediction source.

The Oct historical development win rates are NOT live probabilities.
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path

from services.frozen_candidate_worker_v31 import (
    inspect_live_source, _install_frozen_readonly_history,
)

# Initial two-item live prospective pilot. Fail closed for everything else.
FROZEN_V18_PILOT={
    "uni:Heather":"dyn3",
    "can:Wolverine Plushie":"dyn8",
}
MAX_WAIT=28800
REPLAN_STEP=300
DEPARTURE_GRID=300
MIN_QUANTITY=30
GRACE=10


def single_tick(db, country, item, config_name, now, *, approved_configs=None):
    """Evaluate frozen V18; optional explicit allowlist for isolated V38 research only.

    The V35 CLI retains its original two-item default and fails closed.
    """
    country=country.strip().lower()
    item=item.strip()
    key=f"{country}:{item}"
    allowed=FROZEN_V18_PILOT if approved_configs is None else approved_configs
    if allowed.get(key)!=config_name:
        return {"status":"NOT_APPROVED_FROZEN_V18_PILOT"}
    source=inspect_live_source(db,int(now))
    if source["status"]!="FRESH":
        return {"status":source["status"]}
    from services import history_service
    from services import plushie_flower_dynamic_planner_v18 as engine
    _install_frozen_readonly_history(history_service,db)
    cfg_by_name={c.name:c for c in engine.configs()}
    cfg=cfg_by_name.get(config_name)
    if cfg is None:
        return {"status":"FROZEN_CONFIG_UNAVAILABLE"}
    cleaned,cycles,_=engine.load_item(country,item,MIN_QUANTITY)
    timeline=engine.Timeline(cleaned,cycles,MIN_QUANTITY)
    deps,features=engine.completed_cycle_features(cycles)
    points=engine.build_points(timeline,deps,features,600)
    if len(points)<60:
        return {"status":"INSUFFICIENT_HISTORICAL_FEATURES"}
    travel=int(engine.TRAVEL_SECONDS[country])
    proposal=engine.plan(float(now),points,[p.t for p in points],timeline,
                         deps,features,cfg,list(range(0,MAX_WAIT+1,DEPARTURE_GRID)),
                         travel,GRACE)
    if proposal is None:
        return {"status":"NO_RECOMMENDATION",
                "model_generation":"V18","model_config":cfg.name}
    departure=int(proposal["departure_time"])
    if departure<now or departure>now+MAX_WAIT:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    # Deliberately omit uncalibrated per-trip probability from output.
    return {
        "status":"RESEARCH_PROPOSAL_ONLY",
        "model_generation":"V18",
        "model_config":cfg.name,
        "key":key,"query_timestamp":int(now),
        "recommended_departure_timestamp":departure,
        "recommended_arrival_timestamp":departure+travel,
        "replan_step_seconds":REPLAN_STEP,
        "research_horizon_seconds":MAX_WAIT,
        "quantity_threshold":MIN_QUANTITY,"grace_seconds":GRACE,
        "probability_calibrated":False,"gameplay_automated":False,
        "source":"FROZEN_V18_ORIGINAL_ENGINE_SINGLE_TICK",
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",required=True)
    parser.add_argument("--country",required=True)
    parser.add_argument("--item",required=True)
    parser.add_argument("--config",required=True)
    parser.add_argument("--now",type=int,required=True)
    args=parser.parse_args()
    try:
        result=single_tick(args.db,args.country,args.item,args.config,args.now)
    except Exception as exc:
        result={"status":"CHALLENGER_ERROR","error_type":type(exc).__name__}
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":main()
