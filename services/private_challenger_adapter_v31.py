"""Private only: run a frozen GENERIC challenger in a subprocess.

Environment:
- TORN_FREN_CHAMPION_SHADOW_ENABLED=1 plus private token (V29 route)
- TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED=1 (separate, default OFF)
- TORN_FREN_CHAMPION_SHADOW_DB_PATH=/path/to/collector.db
- TORN_FREN_CHAMPION_V19_MASTER_PATH, V20_MASTER_PATH, V21_MASTER_PATH

Research only, no scoring probability or public route change.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from pathlib import Path

NATIVE_FLAG="TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED"
DB_PATH_FLAG="TORN_FREN_CHAMPION_SHADOW_DB_PATH"
MASTER_ENV={
    "v19":"TORN_FREN_CHAMPION_V19_MASTER_PATH",
    "v20":"TORN_FREN_CHAMPION_V20_MASTER_PATH",
    "v21":"TORN_FREN_CHAMPION_V21_MASTER_PATH",
}


def research_candidate(
    country:str,item:str,selected:dict,category:str,
    environ:dict|None=None, now:int|None=None, *, run_worker=None
) -> dict:
    env=os.environ if environ is None else environ
    if env.get(NATIVE_FLAG,"").strip().lower() not in ("1","true","yes"):
        return {"status":"DISABLED","champion_executed":False}
    version=selected.get("model_family")
    if version not in MASTER_ENV:
        return {"status":"SPECIALIST_OR_BASELINE_UNSUPPORTED",
                "champion_executed":False}
    master=env.get(MASTER_ENV[version],"")
    db=env.get(DB_PATH_FLAG,"")
    if not master or not db:
        return {"status":"MISSING_PRIVATE_SOURCE_PATHS","champion_executed":False}
    # Validate before launching; paths and credentials are never sent to HTTP client.
    if not Path(master).is_file() or not Path(db).is_file():
        return {"status":"PRIVATE_SOURCES_UNAVAILABLE","champion_executed":False}
    timestamp=int(time.time()) if now is None else int(now)
    args=[sys.executable,"-m","services.frozen_candidate_worker_v31",
          "--db",db,"--master",master,"--version",version,
          "--country",country,"--item",item,"--now",str(timestamp)]
    # Normalize flower/plushie research to the 8h planning rule rather than
    # silently pretending the old 12h native setting was directly comparable.
    if category in ("flower","plushie") and version in ("v20","v21"):
        args+=["--max-wait-seconds","28800"]
    try:
        invocation=run_worker or subprocess.run
        p=invocation(args,capture_output=True,text=True,timeout=35,
                     check=False)
        if p.returncode!=0 or len(p.stdout)>8192:
            return {"status":"PRIVATE_WORKER_FAILED","champion_executed":False}
        result=json.loads(p.stdout)
        if not isinstance(result,dict):
            raise ValueError("invalid worker response")
        status=result.get("status")
        if status!="RESEARCH_PROPOSAL_ONLY":
            return {"status":str(status or "NO_RESULT"),
                    "champion_executed":False}
        if (result.get("key")!=f"{country}:{item}" or
            result.get("model_generation")!=version or
            result.get("model_config")!=selected.get("config_name") or
            result.get("probability_calibrated") is not False):
            return {"status":"FROZEN_CONFIG_IDENTITY_MISMATCH",
                    "champion_executed":False}
        depart=result.get("recommended_departure_timestamp")
        arrive=result.get("recommended_arrival_timestamp")
        if (not isinstance(depart,int) or not isinstance(arrive,int) or
            depart<timestamp or arrive<=depart or
            depart-timestamp>12*3600):
            return {"status":"INVALID_DEPARTURE","champion_executed":False}
        return {
            "status":"RESEARCH_PROPOSAL_ONLY","champion_executed":True,
            "mode":"PRIVATE_DIAGNOSTIC_NOT_LIVE",
            "model_generation":version,
            "model_config":result["model_config"],
            "recommended_departure_timestamp":depart,
            "recommended_arrival_timestamp":arrive,
            "quantity_threshold":30,"grace_seconds":10,
            "replanning_seconds":result.get("replan_step_seconds"),
            "horizon_seconds":result.get("research_horizon_seconds"),
            "chance_calibrated":False,
            "source":"original_versioned_generic_engine_single_tick",
        }
    except (OSError,ValueError,json.JSONDecodeError,subprocess.TimeoutExpired):
        return {"status":"PRIVATE_WORKER_FAILED","champion_executed":False}
