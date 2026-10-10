"""V76 forward evaluation of research as-issued candidate evidence (READ ONLY).

Reads immutable candidate decisions from a PRIVATE V72/V75 SQLite sidecar
and observed stock from the approved live SQLite collector, opened mode=ro.
Reports independent item/arrival events, and separately labels:
  * strict sample evidence WITHIN [arrival, arrival + 10s] (if available)
  * conservative +/-180s observed-bracket outcome (PROXY, not exact truth)
  * missing coverage / pending outcomes.
The existing collection cadence cannot certify an exact arrival success
percentage without stock observations covering the 10-second window.
No source/ledger writes, no artificial player departures, no new predictions.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from research.v38_prediction_store import GRACE,MIN_QTY,HORIZON,STEP
from research.plushie_champions.common import TRAVEL_SECONDS
from research.v57_exception_fingerprint import fingerprint
from research.v60_private_snapshot_probe import approved_collector_source
from research.v34_prospective_ops_audit import arrival_truth

ROOT=Path("/var/lib/torn-fren-v38")
SOURCE=Path("/opt/torn-fren/data/stock_history.db")
V72=ROOT/"v72_private_predictions.db"
V75=ROOT/"v75_private_predictions.db"
MAX_CANDIDATE_ROWS=50000
MAX_PROXY_EVENTS=1200


def ro(path):
    p=Path(path).resolve(strict=True)
    if p.is_symlink() or not p.is_file():
        raise ValueError("not a regular research input")
    c=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=5)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    return c


def eligible(row):
    """Exact contract at issuance; expired now is not invalid at issue."""
    try:
        country,item=row["item_key"].split(":",1)
    except ValueError:
        return False
    issued,stock,valid,dep,arr=(row[x] for x in (
        "computed_at","stock_as_of","valid_until","departure","arrival"))
    if country not in TRAVEL_SECONDS or not item or row["status"]!="RESEARCH_PROPOSAL_ONLY":
        return False
    if (type(issued) is not int or type(stock) is not int
        or type(dep) is not int or type(arr) is not int
        or type(valid) is not int):
        return False
    if row["actual_player_departure"]!=0:
        return False
    return (0<=issued-stock<=180 and valid==issued+STEP
            and issued<=dep<=issued+HORIZON
            and arr-dep==TRAVEL_SECONDS[country])


def select_unique(con,*,start,end):
    """One independent arrival target per item, first as-issued event wins.

    Same forecast repeated on each five-minute replan is NOT independent.
    Different arrival times are separate forecasts and remain distinguishable.
    """
    rows=con.execute("""SELECT item_key,computed_at,stock_as_of,status,
                       valid_until,departure,arrival,actual_player_departure
                       FROM v42_candidate_decisions
                       WHERE computed_at>=? AND computed_at<=?
                       ORDER BY computed_at ASC,id ASC
                       LIMIT ?""",(start,end,MAX_CANDIDATE_ROWS+1)).fetchall()
    if len(rows)>MAX_CANDIDATE_ROWS:
        raise ValueError("candidate count exceeds safe bound; narrow --days")
    unique={}
    invalid=0
    for r in rows:
        if not eligible(r):
            invalid+=1
            continue
        k=(r["item_key"],r["arrival"])
        if k not in unique:
            unique[k]=r
    return list(unique.values()),len(rows),invalid


def strict_samples(con,country,item,arrival):
    samples=con.execute("""SELECT timestamp,quantity FROM stock_history
           WHERE country=? AND lower(item_name)=lower(?)
             AND timestamp>=? AND timestamp<=?
           ORDER BY timestamp,id LIMIT 100""",
           (country,item,arrival,arrival+GRACE)).fetchall()
    if not samples:
        return "NO_SAMPLE_WITHIN_10_SECONDS"
    if any(int(q)>=MIN_QTY for _,q in samples):
        return "DIRECT_THRESHOLD_OBSERVED_WITHIN_GRACE"
    return "ONLY_BELOW_THRESHOLD_SAMPLES_WITHIN_GRACE"


def audit(sidecar,source,*,now=None,days=3,limit=MAX_PROXY_EVENTS):
    if not 1<=days<=14 or not 1<=limit<=MAX_PROXY_EVENTS:
        raise ValueError("invalid research audit horizon")
    end=int(time.time() if now is None else now)
    start=end-int(days*86400)
    if Path(sidecar).resolve(strict=True)==Path(source).resolve(strict=True):
        raise ValueError("research ledger and collector must be separate")
    with closing(ro(sidecar)) as evidence:
        events,source_rows,invalid=select_unique(evidence,start=start,end=end)
    if len(events)>limit:
        raise ValueError("too many independent arrival events; narrow --days or adjust --limit")
    status=Counter()
    strict=Counter()
    per_item=defaultdict(Counter)
    with closing(ro(source)) as observations:
        for r in events:
            key=r["item_key"]
            arr=int(r["arrival"])
            country,item=key.split(":",1)
            if end<arr+GRACE+180:
                category="PENDING"
                sample="NOT_FINAL"
            else:
                sample=strict_samples(observations,country,item,arr)
                proxy,_=arrival_truth(observations,country,item,arr,end)
                category=(
                    "BRACKETED_PROXY_SUCCESS" if proxy=="SUCCESS" else
                    "BRACKETED_PROXY_MISS" if proxy=="MISS" else
                    proxy
                )
            status[category]+=1
            strict[sample]+=1
            per_item[key][category]+=1
    scored=status["BRACKETED_PROXY_SUCCESS"]+status["BRACKETED_PROXY_MISS"]
    return {
        "status":"V76_FORWARD_RESEARCH_REPORT",
        "research_only":True,
        "actual_player_departure_observed":False,
        "prediction_accuracy_calibrated":False,
        "reported_as_exact_arrival_accuracy":False,
        "collector_written":False,
        "sidecar_written":False,
        "independent_event_basis":"FIRST_AS_ISSUED_FOR_ITEM_AND_ARRIVAL",
        "arrival_grace_seconds":GRACE,
        "minimum_quantity":MIN_QTY,
        "stock_bracket_limit_seconds":180,
        "caution":"Bracketing high or low stock is a proxy, NOT certified stock exactly at arrival; sparse polling cannot prove exact 10-second misses.",
        "analysis_asof_epoch":end,
        "issued_window_days":days,
        "raw_candidate_rows":source_rows,
        "invalid_or_abstained_rows_excluded":invalid,
        "independent_valid_issued_events":len(events),
        "proxy_scorable_events":scored,
        "proxy_successes":status["BRACKETED_PROXY_SUCCESS"],
        "proxy_misses":status["BRACKETED_PROXY_MISS"],
        "proxy_success_fraction":round(status["BRACKETED_PROXY_SUCCESS"]/scored,4) if scored else None,
        "strict_threshold_directly_observed":strict["DIRECT_THRESHOLD_OBSERVED_WITHIN_GRACE"],
        "strict_only_below_threshold_observed":strict["ONLY_BELOW_THRESHOLD_SAMPLES_WITHIN_GRACE"],
        "strict_without_sample":strict["NO_SAMPLE_WITHIN_10_SECONDS"],
        "pending":status["PENDING"],
        "status_counts":dict(sorted(status.items())),
        "per_item_counts":{key:dict(sorted(v.items())) for key,v in sorted(per_item.items())},
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sidecar",choices=("v72","v75"),default="v72")
    ap.add_argument("--days",type=int,default=3)
    ap.add_argument("--limit",type=int,default=MAX_PROXY_EVENTS)
    a=ap.parse_args()
    sidecar={"v72":V72,"v75":V75}[a.sidecar]
    try:
        if not approved_collector_source(SOURCE):
            raise ValueError("collector path not approved")
        if sidecar.parent.resolve(strict=True)!=ROOT.resolve(strict=True):
            raise ValueError("non-private evidence path")
        result=audit(sidecar,SOURCE,days=a.days,limit=a.limit)
    except Exception as exc:
        result={"status":"V76_AUDIT_ERROR","research_only":True,
                "collector_written":False,"sidecar_written":False,
                **fingerprint(exc)}
    print(json.dumps(result,sort_keys=True))
    if result["status"]!="V76_FORWARD_RESEARCH_REPORT":
        raise SystemExit(1)


if __name__=="__main__":
    main()
