"""Parallel/resumable PC runner for V166 seven-specialist replay.

Runs one item per child process so each specialist gets an independent causal
scratch mirror.  The historical source SQLite is read-only.  Output JSON files
are resumable and never overwrite a completed result for a different window.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys
import time

from research.v166_seven_specialist_earliest_replay import SEVEN, MODEL_FREEZE_EPOCH

ROOT=Path(__file__).resolve().parents[1]


def run_one(item,*,source,start,end,outdir,timeout):
    name=item.replace(":","__").replace(" ","_")
    out=outdir/(name+".json")
    if out.is_file():
        try:
            old=json.loads(out.read_text(encoding="utf-8"))
            if old.get("item_key")==item and old.get("start")==start and old.get("end")==end:
                return {"item":item,"status":"CACHED","output":str(out)}
        except Exception:
            pass
    cmd=[sys.executable,"-m","research.v166_seven_specialist_earliest_replay",
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
    started=time.monotonic()
    try:
        p=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,
                         timeout=timeout,check=False,errors="replace")
    except subprocess.TimeoutExpired:
        return {"item":item,"status":"TIMEOUT","seconds":round(time.monotonic()-started,1)}
    (outdir/(name+".log")).write_text(
        "COMMAND: "+" ".join(cmd)+"\nEXIT: "+str(p.returncode)+
        "\nSTDOUT\n"+p.stdout+"\nSTDERR\n"+p.stderr,encoding="utf-8")
    if p.returncode!=0:
        return {"item":item,"status":"ERROR_EXIT_"+str(p.returncode),
                "seconds":round(time.monotonic()-started,1)}
    try:
        payload=json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        return {"item":item,"status":"INVALID_OUTPUT"}
    return {"item":item,"status":"COMPLETED","seconds":round(time.monotonic()-started,1),
            "arrival_success_fraction":payload.get("arrival_success_fraction"),
            "earliest_restock_hit_fraction":payload.get("earliest_restock_hit_fraction"),
            "proposal_coverage":payload.get("proposal_coverage"),"output":str(out)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--start-epoch",type=int)
    p.add_argument("--end-epoch",type=int)
    p.add_argument("--days",type=int,default=7)
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--timeout-per-item",type=int,default=14400)
    p.add_argument("--item-key",action="append")
    a=p.parse_args()
    if not 1<=a.workers<=7:p.error("workers must be 1..7")
    if not 1<=a.days<=14:p.error("days must be 1..14")
    source=Path(a.source).expanduser().resolve(strict=True)
    outdir=a.output.expanduser().resolve();outdir.mkdir(parents=True,exist_ok=True)

    import sqlite3
    con=sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)
    cutoff=con.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
                          WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
    con.close()
    if cutoff is None:raise ValueError("source has no successful heartbeat")
    end=a.end_epoch if a.end_epoch is not None else int(cutoff)-9*3600
    start=a.start_epoch if a.start_epoch is not None else end-a.days*86400
    start=max(start,MODEL_FREEZE_EPOCH)
    if end<=start:raise ValueError("no post-freeze mature replay window")

    items=tuple(a.item_key or SEVEN)
    if len(set(items))!=len(items) or not set(items)<=set(SEVEN):
        p.error("choose unique keys from V166 seven-specialist roster")

    manifest={"source":str(source),"start":start,"end":end,"items":list(items),
              "workers":a.workers,"post_freeze_only":True}
    mf=outdir/"manifest.json"
    if mf.exists() and json.loads(mf.read_text(encoding="utf-8"))!=manifest:
        raise ValueError("output directory belongs to a different V166 run")
    mf.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    print("V166 SEVEN SPECIALISTS",len(items),"START",start,"END",end,
          "ISSUE_STEP",300,"WORKERS",a.workers,flush=True)
    results={}
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs={pool.submit(run_one,item,source=source,start=start,end=end,
                          outdir=outdir,timeout=a.timeout_per_item):item for item in items}
        for fut in as_completed(futs):
            item=futs[fut]
            try:results[item]=fut.result()
            except Exception as exc:results[item]={"item":item,"status":"ERROR_"+type(exc).__name__}
            print("DONE",item,json.dumps(results[item],sort_keys=True),flush=True)
            (outdir/"summary.json").write_text(json.dumps({
                "status":"COMPLETE" if len(results)==len(items) and all(
                    x["status"] in ("COMPLETED","CACHED") for x in results.values())
                    else "PARTIAL",
                "start":start,"end":end,"results":dict(sorted(results.items())),
                "production_modified":False,
            },indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return 0 if all(x["status"] in ("COMPLETED","CACHED") for x in results.values()) else 2


if __name__=="__main__":
    raise SystemExit(main())
