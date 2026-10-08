"""V30 exact-source *native* departure parity diagnostic (research-only).

Never promote from cross-snapshot matches. V19/20 source masters do not
necessarily contain a DB SHA, so their provenance is UNKNOWN unless explicitly
supplied through --source-db-sha256 and verified outside this program.

Examples:
  python -m research.v30_native_parity_probe \
    --db 'data/torn-fren-stock-history-latest.db' \
    --v19 'data/all_item_v19/master.json' \
    --v20 'data/weak_item_v20/master.json' \
    --v21 'data/all_item_v21/full_master.json' \
    --only 'arg:Monkey Plushie' --only 'chi:Peony' \
    --max-rows 3 --output 'data/v30_native_parity.json'

Do NOT use --force-cross-snapshot-diagnostic to claim parity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import statistics
from pathlib import Path

from services.frozen_champion_shadow_v24 import (
    _install_frozen_readonly_history,
    OLD_NATIVE,
    EXPECTED_RESULT_SCHEMAS,
)

MASTERS=("v19","v20","v21")
ENGINE_NAMES={"v19":"services.plushie_flower_dynamic_planner_v18",
              "v20":"services.plushie_flower_dynamic_planner_v19",
              "v21":"services.plushie_flower_dynamic_planner_v19"}


def sha256(path: str | Path) -> str:
    hashobj=hashlib.sha256()
    with open(path,"rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):
            hashobj.update(block)
    return hashobj.hexdigest()


def source_provenance(master: dict, db_sha256: str,
                      declared_source_sha256: str | None = None) -> dict:
    embedded=(master.get("settings") or {}).get("db_sha256")
    original=(embedded or declared_source_sha256 or "").strip().lower()
    if not original:
        return {"status":"UNKNOWN_SOURCE_DB_HASH",
                "same_snapshot_proven":False,
                "source_sha256":None,
                "tested_db_sha256":db_sha256}
    if len(original)!=64 or any(x not in "0123456789abcdef" for x in original):
        raise ValueError("Invalid claimed source DB hash")
    return {"status":"SAME_DB_VERIFIED" if original==db_sha256 else "CROSS_SNAPSHOT",
            "same_snapshot_proven":original==db_sha256,
            "source_sha256":original,
            "tested_db_sha256":db_sha256}


def sample_rows(rows:list[dict], max_rows:int) -> list[dict]:
    if not rows or max_rows==0: return rows
    # Freeze deterministic evenly spaced sample; never select by success.
    n=min(max_rows,len(rows))
    if n==1: return [rows[len(rows)//2]]
    indices=[round(i*(len(rows)-1)/(n-1)) for i in range(n)]
    if len(set(indices))!=len(indices):
        raise AssertionError("Duplicate sampled start indices")
    return [rows[i] for i in indices]


def compare_exact(recorded:list[dict],replayed:list[dict]) -> dict:
    if len(recorded)!=len(replayed):
        raise ValueError("Missing replay sessions; do not silently exclude failures")
    details=[];matches=0
    for expected,actual in zip(recorded,replayed):
        if int(expected["start"])!=int(actual["start"]):
            raise ValueError("Unequal session start times")
        predicted=actual.get("departure")
        truth=expected.get("departure")
        same=(predicted is not None and truth is not None
              and abs(float(predicted)-float(truth))<0.001)
        matches+=same
        details.append({
          "start":int(expected["start"]),
          "recorded_departure":truth,
          "replayed_departure":predicted,
          "departure_error_seconds":None if predicted is None or truth is None
                  else int(round(float(predicted)-float(truth))),
          "exact_match":bool(same),
          "saved_success":expected.get("success"),
          "replay_success":actual.get("success"),
        })
    return {"matches":matches,"n":len(details),
            "match_rate":matches/len(details) if details else None,
            "rows":details}


def _native_candidate(db,version,item,master,selected,max_rows):
    """Run original planner code, not the earlier research reimplementation."""
    from services import history_service
    from services import plushie_flower_dynamic_planner_v18 as v18
    from services import plushie_flower_dynamic_planner_v19 as v19
    _install_frozen_readonly_history(history_service,db)
    planner=v18 if version=="v19" else v19
    policy=OLD_NATIVE[version].copy()
    if version=="v20":
        policy["replan_step"]=int((master.get("settings") or {}).get("replan_seconds",900))
    if version=="v21":
        options=(master.get("settings") or {}).get("options") or {}
        for field in ("max_wait","departure_grid","replan_step"):
            if field in options:
                if int(options[field])!=policy[field]:
                    raise ValueError(f"Stored v21 policy mismatch for {field}")
    name,product=item.split(":",1)
    from services.remaining_item_v21 import observed_arrival_success
    gaps=v19.normalize_gaps(history_service.get_collection_gaps())
    if version=="v19":
        cleaned,cycles,bounces=planner.load_item(name,product,30)
        timeline=planner.Timeline(cleaned,cycles,30)
        dep_times,features=planner.completed_cycle_features(cycles)
    else:
        cleaned,cycles,bounces,_=planner.load_item(name,product,30)
        timeline=planner.Timeline(cleaned,cycles,30,gaps=gaps)
        dep_times,features=planner.completed_cycle_features(cycles,gaps=gaps)
    points=planner.build_points(timeline,dep_times,features,600)
    point_times=[p.t for p in points]
    cfg=planner.Config(**selected["selected_on_training"]["config"])
    travel=int(v19.TRAVEL_SECONDS[name])
    delays=list(range(0,policy["max_wait"]+1,policy["departure_grid"]))
    rows=sample_rows(selected.get("holdout_rows") or [],max_rows)
    # Use exact historical native scorer semantics, NOT V24's corrected
    # arrival scorer; this is a provenance-aware parity test of *decisions*.
    plans={}
    def p(t):
        k=int(t)
        if k not in plans:
            plans[k]=planner.plan(
               t,points,point_times,timeline,dep_times,features,
               cfg,delays,travel,10
            )
        return plans[k]
    replay=[]
    for row in rows:
        s=float(row["start"])
        result=planner.simulate_session(s,p,timeline,travel,10,
                                        policy["replan_step"],policy["max_wait"])
        replay.append({"start":int(s),
                       "departure":result["departure"] if result else None,
                       "success":bool(result["success"]) if result else False})
    result=compare_exact(rows,replay)
    result.update({
        "item_key":item,
        "version":version,
        "model_config":cfg.name,
        "engine_family":ENGINE_NAMES[version],
        "selected_original_schema":selected.get("schema"),
        "points_rebuilt":len(points),
        "points_recorded":selected.get("historical_points"),
        "cycles_rebuilt":len(cycles),
        "cycles_recorded":selected.get("cycles"),
        "provider_bounces_rebuilt":len(bounces),
        "provider_bounces_recorded":selected.get("provider_bounces_suppressed"),
    })
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    for family in MASTERS:p.add_argument("--"+family,required=True)
    p.add_argument("--only",action="append",default=[])
    p.add_argument("--max-rows",type=int,default=3)
    p.add_argument("--force-cross-snapshot-diagnostic",action="store_true",
                   help="Only diagnostic comparison; NEVER counted as verified native parity")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    if a.max_rows<0:p.error("negative max rows")
    db=Path(a.db).resolve(strict=True)
    digest=sha256(db)
    masters={v:json.loads(Path(getattr(a,v)).read_text(encoding="utf-8"))
             for v in MASTERS}
    output=Path(a.output)
    if output.exists():raise SystemExit("Output exists: refusing to clobber prior evidence")
    report={"schema":"torn-fren-v30-native-source-parity-v1",
            "tested_db_sha256":digest,
            "diagnostic_only":True,
            "read_only":True,
            "results":{},
            "provenance":{},
            "warning":("Cross-snapshot decision matches are NOT same-input parity. "
                       "Master files may not embed DB source digests.")}

    for version,master in masters.items():
        source=source_provenance(master,digest)
        report["provenance"][version]=source
        keys=a.only or sorted(master.get("results",{}))
        report["results"][version]={}
        for key in keys:
            selected=(master.get("results") or {}).get(key) or {}
            if selected.get("status")!="complete" or not selected.get("holdout_rows"):
                report["results"][version][key]={"status":"NO_FROZEN_HOLDOUT"}
                continue
            if selected.get("schema")!=EXPECTED_RESULT_SCHEMAS[version]:
                report["results"][version][key]={"status":"SCHEMA_MISMATCH"}
                continue
            if not source["same_snapshot_proven"] and not a.force_cross_snapshot_diagnostic:
                report["results"][version][key]={"status":source["status"],
                    "verifiable_native_parity":False}
                continue
            try:
                comparison=_native_candidate(str(db),version,key,master,selected,a.max_rows)
                comparison["status"]="NATIVE_SAME_SNAPSHOT" if source["same_snapshot_proven"] else "CROSS_SNAPSHOT_DIAGNOSTIC"
                comparison["verifiable_native_parity"]=source["same_snapshot_proven"]
                report["results"][version][key]=comparison
            except Exception as exc:
                report["results"][version][key]={"status":"ERROR",
                    "error_type":type(exc).__name__,
                    "detail":str(exc)[:240],"verifiable_native_parity":False}
            print(version,key,report["results"][version][key]["status"],flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    tmp=output.with_suffix(output.suffix+".tmp")
    tmp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,output)
    print("SAVED",output,flush=True)


if __name__=="__main__":
    main()
