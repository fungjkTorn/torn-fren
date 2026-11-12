#!/usr/bin/env python3
"""Read-only truth audit: historical threshold restocks vs NEW V160 forecasts.

Restock evidence: collector change rows (not every poll heartbeat). A restock
here is a same-provider observed crossing from stock <30 to stock >=30.
Cross-provider/conflicting or gap-crossing changes are separately flagged, not
invented as proven restocks. This does NOT backfill historical model forecasts.
V160 was only started recently; its first-issued hourly score denominator is
NOT a count of recorded restocks or completed stock cycles.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

COLLECTOR=Path("/opt/torn-fren/data/stock_history.db")
LEDGER=Path("/var/lib/torn-fren-v38/v160_v151_prospective24.db")
ROSTER=Path("/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json")
EXTRA=frozenset(("can:Xanax","uni:Xanax"))
MAX_CHANGES_PER_ITEM=50000
MAX_GAPS=15000
POLICY="v160_v151_independent_paired_asissued_20261013"
THRESHOLD=30


def read_only(source):
    source=Path(source).resolve(strict=True)
    if not source.is_file():
        raise ValueError("not a regular SQLite file")
    conn=sqlite3.connect(source.as_uri()+"?mode=ro",uri=True,timeout=12)
    conn.execute("PRAGMA query_only=ON")
    return conn


def restock_edges(rows,*,window_start,gaps):
    """Track observed crossings only, omitting ambiguous/collection-gap edges.

    rows are (timestamp,qty,source,id) sorted by timestamp then id.
    Optionally include ONE row before window_start to establish first state.
    """
    count=Counter()
    seen=set()
    prev=None
    first=None
    last=None
    g=[(int(start),int(end) if end is not None else 2**63-1)
       for start,end in gaps]
    for t,q,src,ident in rows:
        if type(t) is not int or type(q) is not int or q<0 or not src:
            count["bad_rows"]+=1
            continue
        current=(t,q,src)
        if t>=window_start:
            count["delta_rows"]+=1
            first=t if first is None else min(first,t)
            last=t if last is None else max(last,t)
        if prev is not None and t>=window_start:
            old,qty,provider=prev
            if t<old:
                count["clock_backwards"]+=1
            elif any(start<=t and end>=old for start,end in g):
                count["known_gap_edges"]+=1
            elif src!=provider:
                count["provider_switch_edges"]+=1
                if (qty<THRESHOLD)!=(q<THRESHOLD):
                    count["ambiguous_cross_provider_threshold_changes"]+=1
            else:
                if qty<THRESHOLD<=q:
                    count["observed_threshold_restocks"]+=1
                if q>qty:
                    count["same_provider_positive_quantity_changes"]+=1
                if qty>=THRESHOLD>q:
                    count["observed_depletions_below_30"]+=1
        prev=current
    return {
        "delta_rows":count["delta_rows"],
        "observed_threshold_restocks":count["observed_threshold_restocks"],
        "observed_depletions_below_30":count["observed_depletions_below_30"],
        "same_provider_positive_quantity_changes":count["same_provider_positive_quantity_changes"],
        "ambiguous_cross_provider_threshold_changes":
            count["ambiguous_cross_provider_threshold_changes"],
        "provider_switch_edges":count["provider_switch_edges"],
        "known_gap_edges":count["known_gap_edges"],
        "bad_rows":count["bad_rows"],
        "history_first_change_epoch":first,
        "history_last_change_epoch":last,
        "latest_known_stock":prev[1] if prev else None,
        "latest_stock_change_epoch":prev[0] if prev else None,
        "latest_known_provider":prev[2] if prev else None,
    }


def _roster(path):
    raw=json.loads(Path(path).read_text(encoding="utf8"))
    base=raw.get("items")
    if not isinstance(base,dict) or len(base)!=22 or not EXTRA.isdisjoint(base):
        raise ValueError("pinned roster must hold 22 canonical items")
    return sorted(set(base)|EXTRA)


def audit(*,collector=COLLECTOR,ledger=LEDGER,roster=ROSTER,
          now=None,days=7,max_changes=MAX_CHANGES_PER_ITEM):
    if type(days) is not int or not 1<=days<=30:
        raise ValueError("history window must be 1–30 days")
    if type(max_changes) is not int or not 100<=max_changes<=MAX_CHANGES_PER_ITEM:
        raise ValueError("unbounded change history")
    asof=int(time.time() if now is None else now)
    start=asof-days*86400
    items=_roster(roster)
    if len(items)!=24:
        raise ValueError("must audit exactly 24 identities")
    if Path(collector).resolve(strict=True)==Path(ledger).resolve(strict=True):
        raise ValueError("ledger and collector must not be the same")
    report={}
    with closing(read_only(collector)) as conn:
        heartbeat=conn.execute(
            """SELECT MAX(timestamp) FROM poll_heartbeats
               WHERE mode='poll-cycle' AND success=1 AND timestamp<=?""",
            (asof,)
        ).fetchone()[0]
        spans=conn.execute(
            """SELECT start_timestamp,end_timestamp FROM collection_gaps
               WHERE start_timestamp<=?
                 AND COALESCE(end_timestamp,9223372036854775807)>=?
               ORDER BY start_timestamp LIMIT ?""",(asof,start,MAX_GAPS+1)
        ).fetchall()
        if len(spans)>MAX_GAPS:
            raise ValueError("collection gap history exceeded audit cap")
        poll_count=conn.execute(
            """SELECT COUNT(*) FROM poll_heartbeats
               WHERE mode='poll-cycle' AND success=1
                 AND timestamp BETWEEN ? AND ?""",(start,asof)
        ).fetchone()[0]
        for key in items:
            country,name=key.split(":",1)
            earlier=conn.execute(
                """SELECT timestamp,quantity,source,id FROM stock_history
                   WHERE country=? AND lower(item_name)=lower(?) AND timestamp<?
                   ORDER BY timestamp DESC,id DESC LIMIT 1""",
                (country,name,start)
            ).fetchone()
            changes=conn.execute(
                """SELECT timestamp,quantity,source,id FROM stock_history
                   WHERE country=? AND lower(item_name)=lower(?)
                     AND timestamp BETWEEN ? AND ?
                   ORDER BY timestamp,id LIMIT ?""",
                (country,name,start,asof,max_changes+1)
            ).fetchall()
            if len(changes)>max_changes:
                raise ValueError("too many history changes for "+key)
            result=restock_edges(
                ([earlier] if earlier else [])+changes,
                window_start=start,gaps=spans)
            report[key]=result
    with closing(read_only(ledger)) as db:
        ticks=db.execute(
            """SELECT MIN(issued_epoch),MAX(issued_epoch),COUNT(*)
               FROM v160_ticks WHERE issued_epoch<=?""",(asof,)
        ).fetchone()
        forecasts=db.execute(
            """SELECT item_key,payload_json FROM v160_issued
               WHERE issued_epoch BETWEEN ? AND ? AND policy_id=?
               ORDER BY issued_epoch,item_key LIMIT 120001""",
            (start,asof,POLICY)
        ).fetchall()
        if len(forecasts)>120000:
            raise ValueError("unbounded V160 data")
    detail={k:{"issues":0,"independent_proposals":0,
                "paired_proposals":0,"independent_reasons":Counter(),
                "paired_reasons":Counter()} for k in items}
    for key,blob in forecasts:
        if key not in detail:
            raise ValueError("unknown V160 research item")
        payload=json.loads(blob)
        if payload.get("item_key")!=key or payload.get("policy_id")!=POLICY:
            raise ValueError("contaminated issued forecast")
        row=detail[key]
        row["issues"]+=1
        for v,name in (("independent","independent"),
                       ("paired_complete","paired")):
            m=payload.get("models",{}).get(v,{})
            if m.get("departure_epoch") is not None:
                row[name+"_proposals"]+=1
            reason=m.get("status")
            row[name+"_reasons"][reason if isinstance(reason,str) else "UNKNOWN"]+=1
    for key in items:
        sub=detail[key]
        report[key]["v160_five_minute_issues"]=sub["issues"]
        report[key]["v160_independent_proposals"]=sub["independent_proposals"]
        report[key]["v160_paired_proposals"]=sub["paired_proposals"]
        report[key]["v160_independent_statuses"]=dict(
            sub["independent_reasons"].most_common(4))
        report[key]["v160_paired_statuses"]=dict(
            sub["paired_reasons"].most_common(4))
    return {
        "status":"V162_READ_ONLY_RESTOCK_HISTORY_VS_V160_FORECAST_COVERAGE",
        "window_days":days,"history_start_epoch":start,"asof_epoch":asof,
        "last_successful_poll_epoch":int(heartbeat) if heartbeat else None,
        "last_poll_age_s":asof-int(heartbeat) if heartbeat else None,
        "successful_poll_heartbeats_in_window":poll_count,
        "v160_first_issue_epoch":ticks[0],
        "v160_last_issue_epoch":ticks[1],
        "v160_issue_batches":ticks[2],
        "threshold":THRESHOLD,"items":report,
        "restocks_are_delta_observed_threshold_crossings":True,
        "cross_provider_events_not_counted_as_confirmed":True,
        "v160_issues_are_not_restocks":True,
        "collector_and_sidecar_written":False,
    }


def summary(data):
    out=[
        "V162 RESTOCK AUDIT — "+str(data["window_days"])+" days of collector history",
        "Valid heartbeat age: "+str(data["last_poll_age_s"])+" sec; "+
          str(data["successful_poll_heartbeats_in_window"])+" successful poll heartbeats",
        "V160 first recorded issue: "+str(data["v160_first_issue_epoch"])+
          "; batches: "+str(data["v160_issue_batches"])+
          " (NEW recorder, not lifetime restocks)",
        "Restock = same-provider quantity <30 to >=30; provider switches/gaps counted separately.",
        "Unchanged 0 in delta-only collector IS NOT stale.",
        "",
        f"{'ITEM':<28} {'RESTOCKS':>8} {'DEPLETIONS':>10} {'+QTY':>5} {'AMBIG':>6} {'V160 ISSUES':>11} {'I/P PROPOSALS':>14}",
        "-"*93,
    ]
    for key,row in sorted(data["items"].items()):
        out.append(
            f"{key[:28]:<28} {row['observed_threshold_restocks']:>8} "
            f"{row['observed_depletions_below_30']:>10} "
            f"{row['same_provider_positive_quantity_changes']:>5} "
            f"{row['ambiguous_cross_provider_threshold_changes']:>6} "
            f"{row['v160_five_minute_issues']:>11} "
            f"{str(row['v160_independent_proposals'])+'/'+str(row['v160_paired_proposals']):>14}"
        )
    for key in ("uni:Nessie Plushie","jap:Xanax"):
        row=data["items"][key]
        out.append(
            "\n"+key+" DIAGNOSTIC: "+
            json.dumps({
                "history_threshold_restocks":row["observed_threshold_restocks"],
                "history_delta_rows":row["delta_rows"],
                "positive_quantity_changes":row["same_provider_positive_quantity_changes"],
                "provider_switch_edges":row["provider_switch_edges"],
                "known_gap_edges":row["known_gap_edges"],
                "v160_issues":row["v160_five_minute_issues"],
                "independent_statuses":row["v160_independent_statuses"],
                "paired_statuses":row["v160_paired_statuses"],
            },sort_keys=True))
    return "\n".join(out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days",type=int,default=7)
    args=parser.parse_args()
    print(summary(audit(days=args.days)))


if __name__=="__main__":
    main()
