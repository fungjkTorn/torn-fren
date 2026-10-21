"""Read-only Windows replay of seven *original* plushie specialist programs.

These are the exact original algorithms recovered under research/plushie_champions,
not the generic clock challengers. Their legacy holdout scores are NOT
separate physical-restock forecasts, and their start/eligibility criteria
differ from the generic 30-day tournament; comparisons need matching cohorts.

Requires numpy and scikit-learn on Python 3.12; local SQLite only.
Example: python scripts/run_pc_original_specialists.py --source historical_pc_data/stock_history_research.db --workers 6 --output historical_pc_results/original-specialists
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.run_pc_historical_sixcore import verify_local_source, hash_source, git_sha

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"research"/"plushie_champions"
JOBS={
 "arg:Monkey Plushie":("checkpoint4_online_selector.py","monkey"),
 "swi:Chamois Plushie":("checkpoint4_online_selector.py","chamois"),
 "chi:Panda Plushie":("panda_pair_selector_ml.py",None),
 "sou:Lion Plushie":("lion_pair_selector_ml.py",None),
 "uae:Camel Plushie":("camel_fast_selector.py",None),
 "uni:Nessie Plushie":("recent_phase_select.py",None),
 "uni:Red Fox Plushie":("rf_localgrid.py",None),
}
MAX_WORKERS=6


def command(key,source):
    if key not in JOBS:raise ValueError("Not a pinned seven-item original specialist")
    filename,target=JOBS[key]
    script=(DIR/filename).resolve(strict=True)
    if script.parent!=DIR.resolve() or script.suffix!=".py":
        raise ValueError("Original specialist source path did not verify")
    cmd=[sys.executable,"-B",str(script),"--db",str(source)]
    if target:cmd+=["--target",target]
    return cmd


def _run_item(key,*,source,root,model_sha,timeout):
    name=key.replace(":","__").replace(" ","_")
    folder=root/name
    folder.mkdir(parents=True,exist_ok=True)
    finished=folder/"legacy_result.json"
    if finished.is_file():
        try:
            prior=json.loads(finished.read_text(encoding="utf-8"))
            if prior["model_sha"]==model_sha and prior["item_key"]==key and prior["source_file"]==JOBS[key][0]:
                return dict(item_key=key,status="CACHED",summary=prior,seconds=0)
        except (KeyError,ValueError,OSError):pass
    env=os.environ.copy()
    env.update({"OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1",
                "OMP_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1",
                "PYTHONDONTWRITEBYTECODE":"1"})
    cmd=command(key,source)
    begin=time.monotonic()
    try:
        process=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,
            text=True,errors="replace",timeout=timeout,check=False)
        (folder/"last_stderr.txt").write_text(
            "EXIT="+str(process.returncode)+"\n"+process.stderr[-100000:],
            encoding="utf-8")
        if process.returncode:
            return dict(item_key=key,status="ERROR_EXIT_"+str(process.returncode),
                        seconds=round(time.monotonic()-begin,2))
        raw=json.loads(process.stdout)
        if raw.get("item")!=key:raise ValueError("Unexpected item in original specialist output")
        hold=raw.get("holdout")
        if not isinstance(hold,dict) or type(hold.get("n")) is not int or hold["n"]<1:
            raise ValueError("Legacy specialist produced no holdout evidence")
        compact=dict(model_sha=model_sha,item_key=key,source_file=JOBS[key][0],
            champion_original_algorithm_executed=True,
            separate_physical_restock_accuracy_measured=False,
            directly_comparable_to_generic_30day_cohorts=False,
            source_sqlite_readonly=True,
            original_holdout=dict(hits=hold.get("hits"),n=hold.get("n"),
                success=hold.get("success"),coverage=hold.get("coverage")),
            original_validation=dict(hits=raw.get("validation",{}).get("hits"),
                n=raw.get("validation",{}).get("n"),
                success=raw.get("validation",{}).get("success"),
                coverage=raw.get("validation",{}).get("coverage")),
            original_configuration=raw.get("config"),
            actual_game_flights=False,production_promoted=False)
        (folder/"legacy_full_result.json").write_text(json.dumps(raw,indent=2,default=str)+"\n",
            encoding="utf-8")
        tmp=finished.with_suffix(".json.next")
        tmp.write_text(json.dumps(compact,indent=2,sort_keys=True,default=str)+"\n",
            encoding="utf-8")
        tmp.replace(finished)
        return dict(item_key=key,status="COMPLETED",summary=compact,
                    seconds=round(time.monotonic()-begin,2))
    except subprocess.TimeoutExpired as exc:
        (folder/"last_stderr.txt").write_text("TIMEOUT "+str(exc)+"\n",encoding="utf-8")
        return dict(item_key=key,status="TIMEOUT",seconds=round(time.monotonic()-begin,2))
    except (ValueError,KeyError,OSError) as exc:
        (folder/"last_stderr.txt").write_text(type(exc).__name__+": "+str(exc)+"\n",encoding="utf-8")
        return dict(item_key=key,status="ERROR_"+type(exc).__name__,
                    seconds=round(time.monotonic()-begin,2))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--workers",type=int,default=2)
    p.add_argument("--timeout-per-item",type=int,default=3600)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--item-key",action="append")
    a=p.parse_args(argv)
    if not 1<=a.workers<=MAX_WORKERS:p.error("Use 1..6 CPU workers")
    if not 60<=a.timeout_per_item<=14400:p.error("Use 60..14400s per specialist")
    chosen=a.item_key or list(JOBS)
    if not chosen or len(set(chosen))!=len(chosen) or not set(chosen)<=set(JOBS):
        p.error("Choose unique keys from original seven plushie specialists")
    source,meta=verify_local_source(a.source)
    if meta["research_metadata"].get("sanitized_stock_only")!="true":
        raise ValueError("Original specialist experiments require sanitized research-only SQLite")
    sha=git_sha();digest=hash_source(source)
    root=a.output.expanduser().resolve()
    if root==ROOT or root==source or root in source.parents or source in root.parents:
        raise ValueError("Unsafe research output location")
    root.mkdir(parents=True,exist_ok=True)
    inventory_sha={}
    for key in chosen:
        script=DIR/JOBS[key][0]
        inventory_sha[JOBS[key][0]]=hashlib.sha256(script.read_bytes()).hexdigest()
    manifest=dict(source_sha256=digest,model_sha=sha,keys=sorted(chosen),
        scripts_sha256=inventory_sha)
    fp=root/"input_manifest.json"
    if fp.exists():
        if json.loads(fp.read_text(encoding="utf-8"))!=manifest:
            raise ValueError("Old output folder belongs to different models or SQLite")
    else:fp.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    completed={}
    def save():
        compact={key:{k:v for k,v in val.items() if k!="summary"} for key,val in completed.items()}
        full=dict(status=("COMPLETE" if len(completed)==len(chosen) and
            all(v["status"] in ("COMPLETED","CACHED") for v in completed.values())
            else "PARTIAL_NO_PROMOTION"),model_sha=sha,source_sha256=digest,
            items=dict(sorted(compact.items())),
            evaluated_original_models=sorted(k for k,v in completed.items()
                     if v["status"] in ("COMPLETED","CACHED")),
            failure_items=sorted(k for k,v in completed.items()
                     if v["status"] not in ("COMPLETED","CACHED")),
            original_legacy_holdout_noncomparable_to_30day_baseline=True,
            original_specialists_are_flight_selectors_not_physical_restock_clocks=True,
            source_sqlite_readonly=True,production_modified=False)
        tmp=root/"summary.json.next"
        tmp.write_text(json.dumps(full,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        tmp.replace(root/"summary.json")
        return full
    print("ORIGINAL_SPECIALISTS",len(chosen),"WORKERS",a.workers,
          "MODEL",sha,"DB",source,flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(_run_item,key,source=source,root=root,
                             model_sha=sha,timeout=a.timeout_per_item):key
                 for key in chosen}
        for fut in as_completed(futures):
            key=futures[fut]
            try:completed[key]=fut.result()
            except Exception as exc:
                completed[key]=dict(item_key=key,status="ERROR_"+type(exc).__name__,
                    message=str(exc)[:120])
            report=save()
            print(f"[{len(completed)}/{len(chosen)}] {key} "+
                  completed[key]["status"],flush=True)
    if hash_source(source)!=digest:raise RuntimeError("SQLite mutated during original replay")
    print("RESULT",report["status"],"REPORT",root/"summary.json",flush=True)
    return 0 if report["status"]=="COMPLETE" else 2


if __name__=="__main__":
    raise SystemExit(main())
