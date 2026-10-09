"""Bounded read-only V38 resource probe for ORIGINAL flower/plushie models.

This is NOT the scheduled collector and never writes the stock DB or research
ledger. Executes up to four representative models by default, sequentially;
--all deliberately expands to all 13 original V18/V19 frozen candidates.
No baseline HTTP requests, no secrets, no web service restarts.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from research.v38_v18_single_tick import V18_APPROVED
from research.v38_v19_single_tick import V19_APPROVED

PROBES=("uni:Heather","can:Wolverine Plushie",
        "arg:Ceibo Flower","jap:Cherry Blossom")
ALL={**{k:"research.v38_v18_single_tick" for k in V18_APPROVED},
     **{k:"research.v38_v19_single_tick" for k in V19_APPROVED}}


def probe(db: str, keys, *, per_item_seconds=20.0, budget_seconds=100.0,
          runner=subprocess.run, clock=time.monotonic, wall_clock=time.time):
    """Capped sequential model measurements; failures are honest abstentions."""
    if not (1<=per_item_seconds<=60 and per_item_seconds<=budget_seconds<=600):
        raise ValueError("invalid run limits")
    started=clock()
    rows=[]
    for key in keys:
        if key not in ALL:
            rows.append({"item":key,"status":"UNSUPPORTED"})
            continue
        elapsed=clock()-started
        remaining=budget_seconds-elapsed
        if remaining<1:
            rows.append({"item":key,"status":"SKIPPED_BUDGET"})
            continue
        country,item=key.split(":",1)
        args=[sys.executable,"-m",ALL[key],"--db",db,
              "--country",country,"--item",item,"--now",str(int(wall_clock()))]
        t0=clock()
        try:
            job=runner(args,capture_output=True,text=True,
                       timeout=min(per_item_seconds,remaining),check=False)
            if job.returncode!=0 or len(job.stdout)>8192:
                status="WORKER_ERROR"
            else:
                result=json.loads(job.stdout)
                status=(str(result.get("status") or "MISSING_STATUS")[:80]
                        if isinstance(result,dict) else "INVALID_RESULT")
        except subprocess.TimeoutExpired:
            status="WORKER_TIMEOUT"
        except (ValueError,OSError):
            status="WORKER_ERROR"
        rows.append({"item":key,"status":status,
                     "elapsed_seconds":round(clock()-t0,3)})
    return {"items":rows,"total_elapsed_seconds":round(clock()-started,3),
            "tested_count":len([r for r in rows if "elapsed_seconds" in r]),
            "proposal_count":sum(r.get("status")=="RESEARCH_PROPOSAL_ONLY" for r in rows),
            "stock_db_modified":False,"v2_http_called":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",default="/opt/torn-fren/data/stock_history.db")
    p.add_argument("--all",action="store_true",help="Explicitly test all 13 models")
    p.add_argument("--timeout",type=float,default=20)
    p.add_argument("--budget",type=float,default=100)
    args=p.parse_args()
    result=probe(args.db,sorted(ALL) if args.all else PROBES,
                 per_item_seconds=args.timeout,budget_seconds=args.budget)
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
