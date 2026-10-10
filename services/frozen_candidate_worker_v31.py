"""Isolated, read-only, *single-tick* frozen GENERIC model inference for V31.

No public routing; no gameplay/automatic travel. This worker is launched
in its own subprocess by a separately gated private research endpoint.

Safety contracts:
- Only V19/V20/V21 and a pinned complete master candidate.
- Refuse historical --now backtests on a DB containing later observations.
- Require current poll-heartbeat evidence and no known collection gap.
- Inspect stock history only after validating data has no future rows.
- Never echo API keys or claim model probabilities are calibrated.
- Never mutate the collector DB.
- Outputs a model proposal for human-facing *private shadow* comparison ONLY.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
from research.v38_readonly_retry import read_with_retry

# Standalone canary helper: do not import research-only V24 replay from main.
# The existing V24 replay module is not part of the public V2 website path.
OLD_NATIVE = {
    "v19": {"max_wait":21600,"departure_grid":300,"replan_step":300},
    "v20": {"max_wait":43200,"departure_grid":300,"replan_step":300},
    "v21": {"max_wait":43200,"departure_grid":900,"replan_step":900},
}


def _install_frozen_readonly_history(history_service, db):
    """Replace legacy history access only inside the isolated child process."""
    path=Path(db).resolve(strict=True)
    def read_only_connect():
        connection=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=30)
        connection.execute("PRAGMA query_only=ON")
        return connection
    history_service.DB_PATH=path
    history_service._connect=read_only_connect
    history_service.init_db=lambda:None
    history_service._DB_READY=True
    return path
from services.remaining_item_v21 import observed_arrival_success

LIVE_FRESHNESS_SECONDS=180
VALID_COUNTRIES={"mex","cay","can","haw","uni","arg","swi","jap","chi","uae","sou"}


def inspect_live_source(db: str | Path, now: int, freshness=LIVE_FRESHNESS_SECONDS) -> dict:
    db=Path(db).resolve(strict=True)
    def read_source_once():
        with sqlite3.connect(db.as_uri()+"?mode=ro",uri=True) as con:
            # Source is a living collector DB, not an offline lookback onto the future.
            maximum=con.execute("SELECT MAX(timestamp) FROM stock_history").fetchone()[0]
            if maximum is None:
                return {"status":"NO_OBSERVATIONS"}
            if int(maximum)>now:
                return {"status":"FUTURE_RECORDS_PRESENT","latest_observation":int(maximum)}
            hb=con.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
                               WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
            if hb is None or hb>now or now-hb>freshness:
                return {"status":"COLLECTOR_STALE_OR_NO_HEARTBEAT",
                        "last_successful_heartbeat":int(hb) if hb is not None else None}
            # Inclusive boundaries: recovery timestamp itself is not a valid cycle label.
            gaps=con.execute("""SELECT start_timestamp,end_timestamp FROM collection_gaps
                                WHERE start_timestamp <= ? AND
                                COALESCE(end_timestamp,9223372036854775807)>=? LIMIT 1""",
                             (int(now),int(hb))).fetchone()
            if gaps is not None:
                return {"status":"COLLECTION_GAP_CROSSES_RECENT_POLL"}
        return {"status":"FRESH","last_successful_heartbeat":int(hb),
                "latest_observation":int(maximum)}
    return read_with_retry(read_source_once)


def frozen_single_tick(
    db:str|Path,master:str|Path,version:str,country:str,item:str,now:int,
    *,
    freeze_max_wait_seconds:int|None=None,
) -> dict:
    if version not in OLD_NATIVE:
        return {"status":"UNSUPPORTED_MODEL_GENERATION"}
    country=country.strip().lower();item=item.strip()
    if country not in VALID_COUNTRIES or not item or len(item)>120:
        return {"status":"INVALID_ITEM"}
    source=inspect_live_source(db,now)
    if source["status"]!="FRESH":
        return {"status":source["status"],"source":source}
    master_data=json.loads(Path(master).read_text(encoding="utf-8"))
    key=f"{country}:{item}"
    candidate=(master_data.get("results") or {}).get(key) or {}
    if candidate.get("status")!="complete":
        return {"status":"NO_FROZEN_CANDIDATE"}
    config=(candidate.get("selected_on_training") or {}).get("config")
    if not config:
        return {"status":"MISSING_FROZEN_CONFIG"}

    from services import history_service
    from services import plushie_flower_dynamic_planner_v18 as v18
    from services import plushie_flower_dynamic_planner_v19 as v19
    _install_frozen_readonly_history(history_service,db)
    planner=v18 if version=="v19" else v19
    country_gaps=v19.normalize_gaps(history_service.get_collection_gaps())
    if version=="v19":
        cleaned,cycles,bounces=planner.load_item(country,item,30)
        timeline=planner.Timeline(cleaned,cycles,30)
        dep_times,features=planner.completed_cycle_features(cycles)
    else:
        cleaned,cycles,bounces,gaps=planner.load_item(country,item,30)
        if version=="v21":
            class QuantityTruthTimeline(planner.Timeline):
                def success(self,arrival,grace):
                    ok=observed_arrival_success(
                        self.ts,self.qty,self.gaps,arrival,self.min_qty,grace)
                    return bool(ok) if ok is not None else False
            timeline=QuantityTruthTimeline(cleaned,cycles,30,gaps=country_gaps)
        else:
            timeline=planner.Timeline(cleaned,cycles,30,gaps=country_gaps)
        dep_times,features=planner.completed_cycle_features(cycles,gaps=country_gaps)
    points=planner.build_points(timeline,dep_times,features,600)
    if len(points)<60:
        return {"status":"INSUFFICIENT_HISTORICAL_FEATURES"}
    cfg=planner.Config(**config)
    options=OLD_NATIVE[version].copy()
    if version=="v21":
        frozen=(master_data.get("settings") or {}).get("options") or {}
        for k in ("max_wait","departure_grid","replan_step"):
            if k in frozen:
                if int(frozen[k])!=int(options[k]):
                    return {"status":"FROZEN_POLICY_OPTIONS_MISMATCH"}
    if version=="v20":
        frozen=(master_data.get("settings") or {}).get("departure_grid_seconds")
        if frozen is not None and int(frozen)!=int(options["departure_grid"]):
            return {"status":"FROZEN_POLICY_OPTIONS_MISMATCH"}
    native_horizon=options["max_wait"]
    if freeze_max_wait_seconds is not None:
        if freeze_max_wait_seconds<300 or freeze_max_wait_seconds>native_horizon:
            return {"status":"INVALID_RESEARCH_HORIZON"}
        options["max_wait"]=int(freeze_max_wait_seconds)
    cfg_options=list(range(0,options["max_wait"]+1,options["departure_grid"]))
    travel=int(v19.TRAVEL_SECONDS[country])
    proposal=planner.plan(float(now),points,[p.t for p in points],timeline,
                          dep_times,features,cfg,cfg_options,travel,10)
    if proposal is None:
        return {"status":"NO_RECOMMENDATION","model_generation":version,
                "model_config":cfg.name}
    departure=int(proposal["departure_time"]);arrival=departure+travel
    if departure<now or departure>now+options["max_wait"]:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    return {
       "status":"RESEARCH_PROPOSAL_ONLY",
       "model_generation":version,
       "model_config":cfg.name,
       "source":"ORIGINAL_VERSIONED_ENGINE_SINGLE_TICK",
       "key":key,
       "query_timestamp":int(now),
       "recommended_departure_timestamp":departure,
       "recommended_arrival_timestamp":arrival,
       "seconds_until_departure":departure-now,
       "research_horizon_seconds":options["max_wait"],
       "replan_step_seconds":options["replan_step"],
       "freshness_seconds":now-source["last_successful_heartbeat"],
       "quantity_threshold":30,
       "grace_seconds":10,
       "probability_calibrated":False,
       "gameplay_automated":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--master",required=True)
    p.add_argument("--version",choices=list(OLD_NATIVE),required=True)
    p.add_argument("--country",required=True)
    p.add_argument("--item",required=True)
    p.add_argument("--now",type=int,required=True)
    p.add_argument("--max-wait-seconds",type=int)
    a=p.parse_args()
    try:
        answer=frozen_single_tick(a.db,a.master,a.version,a.country,a.item,
                                  a.now,freeze_max_wait_seconds=a.max_wait_seconds)
    except Exception as exc:
        # Do not expose model internals or file paths to an HTTP caller.
        answer={"status":"CHALLENGER_ERROR","error_type":type(exc).__name__}
    print(json.dumps(answer,sort_keys=True))


if __name__=="__main__":
    main()
