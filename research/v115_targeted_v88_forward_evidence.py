"""V115: bounded, item-filtered read-only V88 forward evidence.

V88 intentionally refuses >1200 distinct item/arrival targets per run.
With a 200+ item roster, one day of all-item forecasts easily exceeds it.
This script NEVER raises that global cap or silently truncates the roster.

Select Red Fox/Nessie at SQL level BEFORE V76 validity filtering and
(item_key,arrival) deduplication. Reuse V88's entire unchanged polling,
grace and paired depart-now evidence logic within a scoped selector patch.
A configurable last-1..24-hour issue window narrows the selected cohort
without pretending it covers every item.

All-item issue volume is reported separately using COUNT(*), not used as a
sample or summed successes. Fails closed if target rows >50000 or valid
unique target arrivals >1200. No game action, API, key, DB/service writes.
Global heartbeat does not establish country-specific provider freshness.
The previously seen V75 holdout is not a pristine blind validation set.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from functools import partial
from pathlib import Path
from unittest.mock import patch

from research import v88_poll_state_forward_report as v88
from research.v76_forward_research_report import (
    eligible, MAX_CANDIDATE_ROWS, MAX_PROXY_EVENTS, V75
)
from research.v60_private_snapshot_probe import approved_collector_source

ITEMS = {
    "redfox": "uni:Red Fox Plushie",
    "nessie": "uni:Nessie Plushie",
}
MAX_HOURS=24


def select_item_arrivals(con,*,start,end,keys,cap=MAX_PROXY_EVENTS):
    """Bounded SQL item-key pushdown BEFORE dedup and validity validation."""
    if not 1<=len(keys)<=len(ITEMS) or any(key not in ITEMS.values()
                                           for key in keys):
        raise ValueError("unapproved targeted item keys")
    if not 1<=cap<=MAX_PROXY_EVENTS:
        raise ValueError("invalid target cap")
    placeholders=",".join("?" for _ in keys)
    clause=(
        "FROM v42_candidate_decisions "
        "WHERE computed_at>=? AND computed_at<=? "
        f"AND item_key IN ({placeholders})"
    )
    params=[int(start),int(end),*keys]
    raw=int(con.execute("SELECT count(*) "+clause,params).fetchone()[0])
    if raw>MAX_CANDIDATE_ROWS:
        raise ValueError(
            "Target raw candidate rows exceed 50000; narrow --hours")
    rows=con.execute(
        "SELECT item_key,computed_at,stock_as_of,status,"
        "valid_until,departure,arrival,actual_player_departure "
        +clause+" ORDER BY computed_at ASC,id ASC",
        params
    ).fetchall()
    if len(rows)!=raw:
        raise AssertionError("nonrepeatable target count in read-only query")
    unique={}
    invalid=0
    for row in rows:
        if not eligible(row):
            invalid+=1
            continue
        key=row["item_key"],row["arrival"]
        if key not in unique:
            unique[key]=row
            if len(unique)>cap:
                raise ValueError(
                    "More than 1200 unique targeted arrival times; "
                    "narrow --hours")
    return list(unique.values()),raw,invalid


def audit(*,ledger=V75,stock=v88.SOURCE,now=None,hours=24,
          keys=(ITEMS["redfox"],ITEMS["nessie"]),cap=MAX_PROXY_EVENTS):
    if not 1<=hours<=MAX_HOURS or not 1<=cap<=MAX_PROXY_EVENTS:
        raise ValueError("invalid bounded audit options")
    if len(set(keys))!=len(keys) or not set(keys)<=set(ITEMS.values()):
        raise ValueError("invalid target keys")
    if Path(ledger).resolve(strict=True)==Path(stock).resolve(strict=True):
        raise ValueError("ledger must be separate from collector")
    issued_to=int(time.time() if now is None else now)
    issued_from=issued_to-hours*3600
    # V88 reports 'days=1' internally. Restrict selection to explicit
    # requested hours *in the query*; never claim full-day coverage.
    def selector(con,*,start,end):
        return select_item_arrivals(
            con,start=max(start,issued_from),end=min(end,issued_to),
            keys=keys,cap=cap)
    with sqlite3.connect(
        Path(ledger).resolve(strict=True).as_uri()+"?mode=ro",
        uri=True,timeout=10
    ) as con:
        con.execute("PRAGMA query_only=ON")
        volume=int(con.execute(
            "SELECT count(*) FROM v42_candidate_decisions "
            "WHERE computed_at>=? AND computed_at<=?",
            (issued_from,issued_to)
        ).fetchone()[0])
        item_volumes=con.execute(
            "SELECT item_key,count(*) AS rows "
            "FROM v42_candidate_decisions "
            "WHERE computed_at>=? AND computed_at<=? "
            "GROUP BY item_key ORDER BY rows DESC LIMIT 10",
            (issued_from,issued_to)
        ).fetchall()
    with patch.object(v88,"select_unique",new=selector):
        result=v88.report(
            ledger=ledger,stock=stock,days=1,limit=cap,now=issued_to)
    report={
        "status":"V115_TARGETED_V88_FORWARD_EVIDENCE",
        "read_only":True,
        "target_keys":list(keys),
        "issued_window_hours":hours,
        "issued_from_epoch":issued_from,
        "issued_to_epoch":issued_to,
        "all_roster_raw_candidate_rows_NOT_ALL_SCORED":volume,
        "top_10_item_raw_candidate_volumes":[
            {"item_key":item,"rows":count}
            for item,count in item_volumes
        ],
        "targeted_v88_evidence":result,
        "upstream_country_stock_freshness_verified":False,
        "gameplay_success_verified":False,
        "targets_not_independent_restock_cycles":True,
        "roster_wide_accuracy_claimed":False,
    }
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--items",nargs="+",choices=tuple(ITEMS),default=[
        "redfox","nessie"])
    p.add_argument("--limit",type=int,default=MAX_PROXY_EVENTS)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not approved_collector_source(v88.SOURCE):
        raise SystemExit("Collector source did not pass approval")
    report=audit(hours=a.hours,
                 keys=tuple(ITEMS[x] for x in dict.fromkeys(a.items)),
                 cap=a.limit)
    if a.json:
        print(json.dumps(report,sort_keys=True))
        return
    x=report["targeted_v88_evidence"]
    print("===== V115 SQL-FILTERED RED FOX / NESSIE FORWARD EVIDENCE =====")
    print("Window:",report["issued_window_hours"],"hours")
    print("All-roster RAW rows (NOT validated/scored):",
          report["all_roster_raw_candidate_rows_NOT_ALL_SCORED"])
    print("Selected item keys:",json.dumps(report["target_keys"]))
    print("Selected unique item/arrival targets:",
          x["unique_item_arrival_targets"])
    print("Polling proxy: scorable",x["proxy_scorable"],
          "stocked",x["proxy_success"],"below30",x["proxy_miss"],
          "pending",x["pending"])
    print("Selected research statuses:",json.dumps(x["outcomes"],sort_keys=True))
    print("Paired V88 selected-vs-depart-now:",
          json.dumps(x["matched_immediate_departure_baseline"],sort_keys=True))
    print("Paired by item:",
          json.dumps(x["matched_baseline_by_item"],sort_keys=True))
    print("Source/model health and per-item:",
          json.dumps(x["per_item"],sort_keys=True))
    print("Top raw roster volume:",
          json.dumps(report["top_10_item_raw_candidate_volumes"],sort_keys=True))
    print("COUNTRY FEED FRESHNESS NOT VERIFIED; NO PLAYER FLIGHTS CONFIRMED.")


if __name__=="__main__":
    main()
