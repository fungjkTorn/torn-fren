"""Research-only replay of *frozen* V19/V20/V21 travel champions on a newer DB.

This DOES NOT reselect configs, train a challenger, change the website, or
use future outcome labels for decisions. The V19 planner and corrected-truth
scorer are imported from existing, versioned services.

Each session is a dynamic policy simulation: after the start, the recommendation
may be revised at its pre-existing replan cadence as observations become known.
Report this separately from first-recommendation confidence or restock MAE.

Example:
python -u -m services.frozen_champion_shadow_v24 \
 --db data/torn-fren-stock-history-latest.db \
 --registry data/torn_fren_matched_provisional_registry.json \
 --v19 data/all_item_v19/master.json \
 --v20 data/weak_item_v20/master.json \
 --v21 data/all_item_v21/full_master.json \
 --cutoff 1791241486 --only 'arg:Tear Gas' --only 'can:Fire Hydrant' \
 --workers 2 --max-starts 12 --resume
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from services.remaining_item_v21 import observed_arrival_success

SCHEMA="frozen-champion-v24-new-data-shadow-v2"
DEFAULT_OUTPUT="data/frozen_champion_v24/new_vm_master.json"
OLD_NATIVE={
    "v19": {"max_wait":21600,"departure_grid":300,"replan_step":300},
    "v20": {"max_wait":43200,"departure_grid":300,"replan_step":900},
    "v21": {"max_wait":43200,"departure_grid":900,"replan_step":900},
}


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _save(path,payload):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_name(target.name+".writing")
    tmp.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    os.replace(tmp,target)


def _champion_entries(reg):
    rows=reg.get("entries") or []
    if not isinstance(rows,list):
        raise ValueError("registry entries must be a list")
    return {r["key"]:r for r in rows}


def _resolve_config(entry, masters):
    version=entry.get("provisional_model")
    if version not in ("v19","v20","v21"):
        return None
    item=(masters[version].get("results") or {}).get(entry["key"])
    if not item or item.get("status")!="complete":
        return None
    cfg=(item.get("selected_on_training") or {}).get("config")
    if not cfg:
        return None
    return version,cfg,item



def _install_frozen_readonly_history(history_service, db):
    """Force ALL legacy history reads to use a read-only SQLite connection.

    history_service.init_db normally runs CREATE TABLE and PRAGMA journal_mode,
    even during reads. The shadow replay must never initialize or migrate a
    frozen snapshot or change a live collector DB.
    """
    path=Path(db).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    def read_only_connect():
        conn=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=30)
        conn.execute("PRAGMA query_only=ON")
        return conn
    history_service.DB_PATH=path
    history_service._connect=read_only_connect
    history_service.init_db=lambda: None
    history_service._DB_READY=True
    return path


def _digest_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def _worker(payload):
    from services import history_service
    from services import plushie_flower_dynamic_planner_v19 as planner

    key=payload["key"]
    country,item_name=key.split(":",1)
    _install_frozen_readonly_history(history_service,payload["db"])

    # Worker processes may handle several items; don't stack a new subclass
    # of the previously monkey-patched Timeline on every iteration.
    base_timeline=getattr(planner,"_frozen_v24_timeline_base",planner.Timeline)
    planner._frozen_v24_timeline_base=base_timeline
    class TruthTimeline(base_timeline):
        def success(self,arrival,grace):
            val=observed_arrival_success(
                self.ts,self.qty,self.gaps,arrival,self.min_qty,grace
            )
            return bool(val) if val is not None else False

    planner.Timeline=TruthTimeline
    cleaned,cycles,bounces,gaps=planner.load_item(country,item_name,payload["min_qty"])
    if not cleaned:
        return key,{"status":"no_history"}
    timeline=TruthTimeline(cleaned,cycles,payload["min_qty"],gaps=gaps)
    dep_times,cycle_feats=planner.completed_cycle_features(cycles,gaps=gaps)
    points=planner.build_points(timeline,dep_times,cycle_feats,600)
    if len(points)<60:
        return key,{"status":"insufficient_points","points":len(points)}

    travel=int(planner.TRAVEL_SECONDS[country])
    max_horizon=max(c["max_wait"] for c in payload["candidates"].values())
    # All candidate models must have a full common 12h observed horizon.
    first=((payload["cutoff"]+1799)//1800)*1800
    last=int(timeline.last_ts-max_horizon-travel-payload["grace"])
    starts=[]
    for t in range(first,last+1,payload["step"]):
        if timeline.crosses_gap(t,t+max_horizon+travel+payload["grace"]):
            continue
        if planner.context_at(t,timeline,dep_times,cycle_feats) is None:
            continue
        starts.append(float(t))
    if payload["max_starts"] and len(starts)>payload["max_starts"]:
        # Spread across the new period rather than favoring the first few.
        if payload["max_starts"]==1:
            starts=[starts[len(starts)//2]]
        else:
            starts=[starts[round(i*(len(starts)-1)/(payload["max_starts"]-1))]
    if not starts:
        return key,{"status":"no_clean_new_sessions","new_end_timestamp":int(timeline.last_ts)}

    per={}
    for version,candidate in payload["candidates"].items():
        cfg=planner.Config(**candidate["config"])
        durations=list(range(0,candidate["max_wait"]+1,candidate["departure_grid"]))
        rows,_,summary=planner.eval_config(
            starts,cfg,points,[p.t for p in points],
            timeline,dep_times,cycle_feats,durations,travel,payload["grace"],
            candidate["replan_step"],candidate["max_wait"]
        )
        per[version]={
            "model":cfg.name,"summary":summary,
            "rows":[{"start":int(r["start"]),"departure":int(r["departure"]),
                     "arrival":int(r["arrival"]),"success":bool(r["success"]),
                     "session_cap":bool(r.get("session_cap",False))}
                    for r in rows],
            "original_candidate_settings": {
                k:candidate[k] for k in ("max_wait","departure_grid","replan_step")
            },
        }
    return key,{
        "status":"complete",
        "snapshot_cutoff":payload["cutoff"],
        "shared_starts":len(starts),
        "eligible_start_times":[int(t) for t in starts],
        "travel_seconds":travel,
        "provider_bounces_suppressed":len(bounces),
        "known_collection_gaps":len(gaps),
        "versions":per,
        "warning":"Dynamic policy replay on new timestamps. Not an independent next-drop confidence calibration.",
    }


def _match(item):
    """Score every eligible shared start; missing recommendations count in coverage.

    A conditional-only intersection of recommendation rows inflates performance
    when a challenger silently abstains on difficult starting sessions.
    """
    from itertools import combinations
    eligible = [int(t) for t in item.get("eligible_start_times", [])]
    if not eligible or len(set(eligible)) != len(eligible):
        raise ValueError("missing or duplicate eligible_start_times")
    if len(eligible) != item.get("shared_starts"):
        raise ValueError("eligible_start_times disagree with shared_starts")
    sessions = set(eligible)
    versions = item.get("versions") or {}
    mapped = {}
    counts = {}
    for version, data in versions.items():
        rows = data.get("rows") or []
        by = {int(row["start"]): row for row in rows}
        if len(by) != len(rows):
            raise ValueError(f"{version}: duplicate recommendation starts")
        if not set(by).issubset(sessions):
            raise ValueError(f"{version}: recommendation outside eligible starts")
        mapped[version] = by
        hits = sum(bool(r["success"]) for r in by.values())
        n_recommended = len(by)
        counts[version] = {
            "hits": hits,
            "paired_n": len(eligible),
            "all_start_success_rate": hits / len(eligible),
            "recommendations": n_recommended,
            "coverage": n_recommended / len(eligible),
            "conditional_success_rate": hits / n_recommended if n_recommended else None,
            "no_recommendation_starts": len(eligible) - n_recommended,
            "session_caps": sum(bool(r.get("session_cap")) for r in by.values()),
        }
    head_to_head = {}
    for left, right in combinations(sorted(mapped), 2):
        a, b = mapped[left], mapped[right]
        a_only = sum(bool(a.get(t, {}).get("success")) and
                     not bool(b.get(t, {}).get("success")) for t in eligible)
        b_only = sum(bool(b.get(t, {}).get("success")) and
                     not bool(a.get(t, {}).get("success")) for t in eligible)
        head_to_head[f"{left}_vs_{right}"] = {
            "shared_eligible_starts": len(eligible),
            f"{left}_only_successes": a_only,
            f"{right}_only_successes": b_only,
            "ties": len(eligible) - a_only - b_only,
        }
    return {
        "versions": counts, "common_starts": len(eligible),
        "head_to_head": head_to_head,
        "warning": ("Intention-to-treat on shared eligible starts; no-recommendation "
                    "counts as no successful trip. Native wait horizons differ by generation. "
                    "Not a calibrated next-restock forecast."),
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--db",required=True)
    ap.add_argument("--registry",help="Optional 236-entry selection registry; without it replay all master catalog keys")
    for v in ("v19","v20","v21"):
        ap.add_argument("--"+v,required=True)
    ap.add_argument("--cutoff",type=int,required=True)
    ap.add_argument("--expected-db-sha256",default="d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583",
                    help="Frozen newer VM DB digest; never point at a live collector DB")
    ap.add_argument("--only",action="append",default=[])
    ap.add_argument("--output",default=DEFAULT_OUTPUT)
    ap.add_argument("--workers",type=int,default=2)
    ap.add_argument("--max-starts",type=int,default=12)
    ap.add_argument("--step",type=int,default=1800)
    ap.add_argument("--min-qty",type=int,default=30)
    ap.add_argument("--grace-seconds",type=int,default=10)
    ap.add_argument("--v20-replan-seconds",type=int,default=900,
                    help="Historical V20 replan cadence was not stored in its master; CLI default was 900s")
    ap.add_argument("--resume",action="store_true")
    args=ap.parse_args()
    if args.workers<1 or args.max_starts<1 or args.step<60 or args.cutoff<=0 or args.v20_replan_seconds<1:
        ap.error("invalid worker, sampling or cutoff settings")
    db=Path(args.db).resolve()
    if not db.is_file():
        raise SystemExit("Missing latest snapshot; no test run started")
    db_sha=_digest_file(db)
    if args.expected_db_sha256 and db_sha.lower()!=args.expected_db_sha256.lower():
        raise SystemExit(f"STOP: frozen snapshot checksum mismatch {db_sha}; make a stable archived copy first")
    masters={v:_json(getattr(args,v)) for v in OLD_NATIVE}
    if args.registry:
        registry=_champion_entries(_json(args.registry))
    else:
        registry={
            key: {"key": key} for master in masters.values()
            for key in (master.get("results") or {}) if key != "jap:Xanax"
        }
    native_policies={v:dict(policy) for v,policy in OLD_NATIVE.items()}
    native_policies["v20"]["replan_step"]=args.v20_replan_seconds
    v20_recorded=(masters["v20"].get("settings") or {}).get("departure_grid_seconds")
    if v20_recorded is not None and int(v20_recorded)!=native_policies["v20"]["departure_grid"]:
        raise SystemExit("STOP: V20 departure grid differs from recorded master settings")
    v21_recorded=(masters["v21"].get("settings") or {}).get("options") or {}
    for opt in ("max_wait","departure_grid","replan_step"):
        if opt in v21_recorded and int(v21_recorded[opt])!=native_policies["v21"][opt]:
            raise SystemExit(f"STOP: V21 {opt} differs from recorded master settings")
    keys=args.only or [
        k for k in sorted(registry) if any(
            ((m.get("results") or {}).get(k) or {}).get("status")=="complete"
            for m in masters.values()
        )
    ]
    settings={"cutoff":args.cutoff,"db_path":str(db),"db_sha256":db_sha,
              "registry_sha256":_digest_file(args.registry) if args.registry else None,
              "native_policies":native_policies,
              "v20_replan_provenance":"CLI default 900s unless explicitly overridden; V20 master does not record replan cadence","db_size":db.stat().st_size,
              "db_mtime_ns":db.stat().st_mtime_ns,"max_starts":args.max_starts,
              "step":args.step,"min_qty":args.min_qty,"grace":args.grace_seconds,
              "master_shas":{v:hashlib.sha256(Path(getattr(args,v)).read_bytes()).hexdigest()
                             for v in OLD_NATIVE}}
    out=Path(args.output)
    if out.exists() and args.resume:
        report=_json(out)
        if report.get("schema")!=SCHEMA or report.get("settings")!=settings:
            raise SystemExit("Resume snapshot/settings differ; never mix tests")
    else:
        if out.exists():
            raise SystemExit("Result exists: supply --resume or a new --output")
        report={"schema":SCHEMA,"settings":settings,"results":{},
                "warning":"Research, no production promotion. Scored on post-cutoff actual stock."}
        _save(out,report)
    tasks=[]
    for key in keys:
        if key not in registry or (args.resume and key in report["results"]):
            continue
        candidates={}
        for v in OLD_NATIVE:
            result=(masters[v].get("results") or {}).get(key) or {}
            cfg=(result.get("selected_on_training") or {}).get("config")
            if result.get("status")=="complete" and cfg:
                candidates[v]={"config":cfg,**native_policies[v]}
        if not candidates:
            report["results"][key]={"status":"no_frozen_model"}
            continue
        tasks.append({"key":key,"db":str(db),"cutoff":args.cutoff,"step":args.step,
                      "min_qty":args.min_qty,"grace":args.grace_seconds,
                      "max_starts":args.max_starts,"candidates":candidates})
    _save(out,report)
    print(f"V24 frozen new-VM replay: {len(tasks)} items, workers={args.workers}",flush=True)
    def record(k,r):
        if r.get("status")=="complete":
            r["matched"]=_match(r)
        report["results"][k]=r
        _save(out,report)
        print("DONE",k,r.get("status"),
              r.get("matched",{}).get("versions"),flush=True)
    if args.workers==1:
        for payload in tasks:
            try:
                record(*_worker(payload))
            except Exception as exc:
                record(payload["key"],{"status":"error","error":repr(exc)})
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            pending={executor.submit(_worker,p):p["key"] for p in tasks}
            for future in as_completed(pending):
                key=pending[future]
                try:
                    record(*future.result())
                except Exception as exc:
                    record(key,{"status":"error","error":repr(exc)})
    print("WROTE",out,flush=True)

if __name__=="__main__":
    main()
