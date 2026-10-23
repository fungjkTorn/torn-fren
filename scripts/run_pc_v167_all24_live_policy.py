"""Parallel/resumable PC runner for V169 24-beta + South Africa Xanax live-policy replay."""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from research.v167_all24_live_policy_replay import ROUTES, MODEL_FREEZE_EPOCH
from research.plushie_champions.common import TRAVEL_SECONDS

ROOT=Path(__file__).resolve().parents[1]
ITEMS=tuple(sorted(ROUTES))


def run_one(item,*,source,start,end,outdir,timeout):
    name=item.replace(":","__").replace(" ","_")
    out=outdir/(name+".json")
    if out.is_file():
        try:
            old=json.loads(out.read_text(encoding="utf-8"))
            if old.get("item_key")==item and old.get("start")==start and old.get("end")==end:
                return {"item":item,"status":"CACHED","output":str(out),
                        "arrival_success_fraction":old.get("arrival_success_fraction"),
                        "earliest_target_hit_fraction":old.get("earliest_target_hit_fraction"),
                        "proposal_coverage":old.get("proposal_coverage")}
        except Exception:
            pass
    cmd=[sys.executable,"-m","research.v167_all24_live_policy_replay",
         "--source",str(source),"--item-key",item,
         "--start-epoch",str(start),"--end-epoch",str(end),
         "--output",str(out)]
    env=os.environ.copy()
    env.update({
        "PYTHONPATH":str(ROOT),
        "TORNFREN_REPLAY_WORK":str(ROOT),
        "TORNFREN_REPLAY_PINNED_RESEARCH":str(ROOT/"research"),
        "OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1",
        "MKL_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1",
    })
    began=time.monotonic()
    try:
        p=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,
                         timeout=timeout,check=False,errors="replace")
    except subprocess.TimeoutExpired:
        return {"item":item,"status":"TIMEOUT","seconds":round(time.monotonic()-began,1)}
    log=outdir/(name+".log")
    log.write_text("COMMAND: "+" ".join(cmd)+"\nEXIT: "+str(p.returncode)+
                   "\nSTDOUT\n"+p.stdout+"\nSTDERR\n"+p.stderr,encoding="utf-8")
    if p.returncode!=0:
        return {"item":item,"status":"ERROR_EXIT_"+str(p.returncode),
                "seconds":round(time.monotonic()-began,1),"log":str(log)}
    payload=json.loads(out.read_text(encoding="utf-8"))
    return {"item":item,"status":"COMPLETED","seconds":round(time.monotonic()-began,1),
            "arrival_success_fraction":payload.get("arrival_success_fraction"),
            "earliest_target_hit_fraction":payload.get("earliest_target_hit_fraction"),
            "proposal_coverage":payload.get("proposal_coverage"),
            "execution_arrival_success_fraction":payload.get("execution_arrival_success_fraction"),
            "execution_earliest_target_hit_fraction":payload.get("execution_earliest_target_hit_fraction"),
            "mean_departure_minus_oracle_seconds":payload.get("mean_departure_minus_oracle_seconds"),
            "mean_predicted_minus_actual_restock_seconds":payload.get("mean_predicted_minus_actual_restock_seconds"),
            "output":str(out)}


def save_summary(outdir,start,end,results):
    complete=[r for r in results.values() if r["status"] in ("COMPLETED","CACHED")]
    def weighted(field,den_field):
        num=den=0.0
        for r in complete:
            try:
                payload=json.loads(Path(r["output"]).read_text(encoding="utf-8"))
                c=payload.get("counts",{})
                if field=="arrival":
                    num+=c.get("arrival_success",0);den+=c.get("arrival_known",0)
                elif field=="earliest":
                    num+=c.get("earliest_target_hit",0);den+=c.get("earliest_target_scored",0)
                elif field=="coverage":
                    num+=c.get("proposals",0);den+=c.get("issues",0)
                elif field=="execution_arrival":
                    ec=payload.get("execution_counts",{})
                    num+=ec.get("arrival_success",0);den+=ec.get("arrival_known",0)
                elif field=="execution_earliest":
                    ec=payload.get("execution_counts",{})
                    num+=ec.get("earliest_target_hit",0);den+=ec.get("earliest_target_scored",0)
            except Exception:
                continue
        return num/den if den else None
    summary={
        "status":"COMPLETE" if len(complete)==len(ITEMS) else "PARTIAL",
        "start":start,"end":end,"items_requested":len(ITEMS),
        "items_complete":len(complete),
        "portfolio_arrival_success_fraction":weighted("arrival",None),
        "portfolio_earliest_target_hit_fraction":weighted("earliest",None),
        "portfolio_proposal_coverage":weighted("coverage",None),
        "portfolio_execution_arrival_success_fraction":weighted("execution_arrival",None),
        "portfolio_execution_earliest_target_hit_fraction":weighted("execution_earliest",None),
        "results":dict(sorted(results.items())),
        "operating_contract":{
            "replan_seconds":300,
            "lookahead":"EVENT_DRIVEN_FIRST_REACHABLE",
            "fixed_time_horizon_seconds":None,
            "arrival_target_quantity":30,
            "grace_seconds":10,
            "v2_lifecycle_telemetry_retained":True,
        },
        "production_modified":False,
    }
    (outdir/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--start-epoch",type=int)
    p.add_argument("--end-epoch",type=int)
    p.add_argument("--days",type=int,default=7)
    p.add_argument("--workers",type=int,default=6)
    p.add_argument("--timeout-per-item",type=int,default=21600)
    p.add_argument("--item-key",action="append")
    p.add_argument("--smoke",action="store_true",
                   help="Run all selected items over only 30 historical minutes")
    p.add_argument("--artifact-dir",type=Path,
                   default=ROOT/"historical_pc_data"/"specialist_artifacts")
    a=p.parse_args()
    if not 1<=a.workers<=8:p.error("workers must be 1..8")
    if not 1<=a.days<=30:p.error("days must be 1..30")

    source=Path(a.source).expanduser().resolve(strict=True)
    outdir=a.output.expanduser().resolve();outdir.mkdir(parents=True,exist_ok=True)
    artifact_dir=a.artifact_dir.expanduser().resolve()
    required_artifacts=("panda_selector_artifact.json","lion_selector_artifact.json")
    missing=[name for name in required_artifacts if not (artifact_dir/name).is_file()]
    if missing:
        raise ValueError(
            "missing pinned specialist artifacts in "+str(artifact_dir)+": "+
            ", ".join(missing))
    os.environ["TORNFREN_SPECIALIST_ARTIFACTS"]=str(artifact_dir)
    with sqlite3.connect(source.as_uri()+"?mode=ro",uri=True) as db:
        cutoff=db.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
                             WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
    if cutoff is None:raise ValueError("source has no successful heartbeat")
    # Mature only by max travel + grace; no forecast lookahead subtraction.
    max_flight=max(TRAVEL_SECONDS.values())
    end=a.end_epoch if a.end_epoch is not None else int(cutoff)-max_flight-60
    start=a.start_epoch if a.start_epoch is not None else end-a.days*86400
    if a.smoke and a.start_epoch is None:
        start=end-1800
    start=max(start,MODEL_FREEZE_EPOCH)
    if end<=start:raise ValueError("no mature post-freeze replay window")

    items=tuple(a.item_key or ITEMS)
    if len(set(items))!=len(items) or not set(items)<=set(ITEMS):
        p.error("choose unique keys from V169 all25 research roster")

    manifest={
        "source":str(source),"start":start,"end":end,"items":list(items),
        "workers":a.workers,
        "artifact_dir":str(artifact_dir),
        "smoke":bool(a.smoke),
        "operating_contract":"EVENT_DRIVEN_FIRST_REACHABLE_NO_FIXED_TIME_HORIZON",
    }
    mf=outdir/"manifest.json"
    if mf.exists() and json.loads(mf.read_text(encoding="utf-8"))!=manifest:
        raise ValueError("output folder belongs to a different V167 run")
    mf.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    print("V169 ALL25 LIVE POLICY REPLAY",len(items),"START",start,"END",end,
          "STEP",300,"WORKERS",a.workers,"FIXED_HORIZON",None,
          "SMOKE",bool(a.smoke),flush=True)
    results={}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs={pool.submit(run_one,item,source=source,start=start,end=end,
                          outdir=outdir,timeout=a.timeout_per_item):item for item in items}
        for fut in as_completed(futs):
            item=futs[fut]
            try:results[item]=fut.result()
            except Exception as exc:
                results[item]={"item":item,"status":"ERROR_"+type(exc).__name__,
                               "message":str(exc)[:160]}
            print("DONE",item,json.dumps(results[item],sort_keys=True),flush=True)
            save_summary(outdir,start,end,results)

    report=save_summary(outdir,start,end,results)
    print("RESULT",report["status"],"COMPLETE",report["items_complete"],"/",report["items_requested"])
    print("SUMMARY",outdir/"summary.json")
    return 0 if report["status"]=="COMPLETE" else 2


if __name__=="__main__":
    raise SystemExit(main())
