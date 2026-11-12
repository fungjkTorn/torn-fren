"""V134: OLD original graph Prediction V2 historical audit, strictly READ ONLY.

Original site prediction_v2_live /api/history displays projected restock
windows, 'best departure window', and arrival countdown. Its existing
forecast_audit_runs and forecast_audit_points in stock_history.db, if
populated, hold AS-ISSUED predictions and later-resolved expected restock,
restock-window hit and predicted-arrival-inside-target-cycle flags.

This reports evidence as recorded by the original auditor. No additional
post-hoc reprojection, no creation of missing tables or predictions, no
force-resolving pending rows. Unlike the new V88 poll-state stock proxy,
the old 'arrival_hit' means recommended arrival is BETWEEN reconstructed
target restock/depletion boundaries and may not verify stock >=30 at
arrival. Unknown/invalid boundaries excluded; repeat model signatures,
overlapping item hours and multiple projected cycles are NOT independent
flights. Do not conflate restock-window accuracy with stock-on-landing.
No updates, network calls, API keys, collector writes or web deployment.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

from research.v128_full24_earliest_shadow import (
    COLLECTOR,ROSTER,exact_roster
)

MAX_DAYS=90
MAX_ROWS=60000


def ro(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file():raise ValueError("not a regular collector file")
    con=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=15)
    con.execute("PRAGMA query_only=ON")
    return con


def _datetime(epoch):
    return (datetime.fromtimestamp(int(epoch),tz=timezone.utc)
            .isoformat(timespec="seconds"))


def _stats(points):
    n=len(points)
    c=Counter()
    deviations=[]
    for r in points:
        c["first_issued_active_item_hours"]+=1
        if r["status"]!="resolved":
            c["unresolved_or_pending"]+=1
            continue
        if r["ground_truth_valid"]!=1:
            c["resolved_but_invalid_observation"]+=1
            continue
        c["resolved_valid_target_cycles"]+=1
        if r["window_hit"]==1:c["restock_window_hit"]+=1
        elif r["window_hit"]==0:c["restock_window_miss"]+=1
        else:c["restock_window_unknown"]+=1
        if r["arrival_hit"]==1:c["arrival_inside_target_cycle"]+=1
        elif r["arrival_hit"]==0:c["arrival_outside_target_cycle"]+=1
        else:c["arrival_target_cycle_unknown"]+=1
        if r["absolute_error_seconds"] is not None:
            deviations.append(float(r["absolute_error_seconds"]))
    scored_windows=c["restock_window_hit"]+c["restock_window_miss"]
    scored_arrivals=c["arrival_inside_target_cycle"]+c[
        "arrival_outside_target_cycle"]
    return {
        "selected_first_issued_active_item_hours":n,
        "resolved_valid_target_cycles":c["resolved_valid_target_cycles"],
        "pending_or_unresolved":c["unresolved_or_pending"],
        "resolved_but_invalid_observation":c[
            "resolved_but_invalid_observation"],
        "window_scorable":scored_windows,
        "restock_window_hit":c["restock_window_hit"],
        "restock_window_miss":c["restock_window_miss"],
        "observed_restock_window_hit_rate":round(
            c["restock_window_hit"]/scored_windows,4)
            if scored_windows else None,
        "cycle_arrival_scorable":scored_arrivals,
        "arrival_inside_target_restock_to_depletion_period":
            c["arrival_inside_target_cycle"],
        "arrival_outside_target_restock_to_depletion_period":
            c["arrival_outside_target_cycle"],
        "arrival_inside_target_cycle_rate":round(
            c["arrival_inside_target_cycle"]/scored_arrivals,4)
            if scored_arrivals else None,
        "mean_absolute_restock_error_minutes":round(
            sum(deviations)/len(deviations)/60,2)
            if deviations else None,
        "arrival_hit_is_not_persisted_threshold_30_stock_truth":True,
        "snapshots_not_independent_gameplay_trips":True,
    }


def audit(*,collector=COLLECTOR,roster=ROSTER,asof=None,
          days=30,limit=MAX_ROWS):
    if not 1<=days<=MAX_DAYS or not 1<=limit<=MAX_ROWS:
        raise ValueError("invalid V134 bound")
    asof=int(time.time() if asof is None else asof)
    allowed=set(exact_roster(roster))
    with closing(ro(collector)) as db:
        tables={str(x[0]) for x in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        needed={"forecast_audit_runs","forecast_audit_points"}
        if not needed.issubset(tables):
            return {
                "status":"ORIGINAL_V2_FORECAST_AUDIT_TABLES_NOT_PRESENT",
                "missing_tables":sorted(needed-tables),
                "read_only":True,
                "selected_items":len(allowed),
                "no_accuracy_claim_without_stored_forecasts":True,
            }
        raw_count=int(db.execute(
            """SELECT COUNT(*) FROM forecast_audit_points AS p
               JOIN forecast_audit_runs AS r ON r.id=p.run_id
               WHERE r.created_at>=? AND r.created_at<=?""",
            (asof-days*86400,asof)).fetchone()[0])
        if raw_count>limit:
            raise ValueError("too many archived original graph forecasts; narrow days")
        raw=db.execute(
            """SELECT
                r.country,r.item_name,r.created_at,r.source,
                r.active_prediction_number,
                p.prediction_number,p.projection_depth,
                p.status,p.ground_truth_valid,p.window_hit,
                p.arrival_hit,p.absolute_error_seconds,
                p.estimate_timestamp,p.recommended_arrival_timestamp,
                p.recommended_leave_by_timestamp
               FROM forecast_audit_points AS p
               JOIN forecast_audit_runs AS r ON r.id=p.run_id
               WHERE r.created_at>=? AND r.created_at<=?
               ORDER BY r.created_at,p.id""",
            (asof-days*86400,asof)).fetchall()
    if len(raw)!=raw_count:
        raise ValueError("nonrepeatable historical original graph audit")
    byhour={}
    existing=Counter()
    sources=Counter()
    depth_all=Counter()
    invalid=Counter()
    for row in raw:
        (country,item,created,origin,active,num,depth,
         status,valid,window_hit,arrival_hit,absolute,restock,arrival,leave)=row
        key=f"{str(country).lower()}:{item}"
        if key not in allowed:
            invalid["OUTSIDE_CURRENT_24_ROSTER"]+=1
            continue
        existing[key]+=1
        sources[str(origin)]+=1
        if active is None:
            invalid["NO_ORIGINAL_ACTIVE_PREDICTION_NUMBER"]+=1
            continue
        if num!=active:
            continue
        if restock is None or arrival is None or leave is None:
            invalid["ACTIVE_WITH_MISSING_TIME_FIELDS"]+=1
            continue
        # One FIRST AS-ISSUED active graph Pn per item per UTC hour.
        # Original auditor only saves when forecast signature changes.
        bucket=(key,int(created)//3600)
        if bucket in byhour:
            continue
        projected_depth=int(depth) if depth is not None else None
        if projected_depth is None:
            invalid["UNKNOWN_ACTUAL_PROJECTION_DEPTH"]+=1
        else:depth_all[projected_depth]+=1
        byhour[bucket]={
            "item_key":key,"created_at":int(created),
            "source":str(origin),
            "prediction_number":int(num),
            "depth":projected_depth,
            "status":str(status),
            "ground_truth_valid":valid,
            "window_hit":window_hit,
            "arrival_hit":arrival_hit,
            "absolute_error_seconds":absolute,
            "predicted_restock_epoch":int(restock),
            "predicted_arrival_epoch":int(arrival),
            "predicted_leave_by_epoch":int(leave),
        }
    points=list(byhour.values())
    grouped=defaultdict(list)
    bydepth=defaultdict(list)
    for p in points:
        grouped[p["item_key"]].append(p)
        bydepth[str(p["depth"])].append(p)
    return {
        "status":"V134_ORIGINAL_GRAPH_PREDICTION_V2_RECORDED_AUDIT",
        "read_only":True,
        "asof_UTC":_datetime(asof),
        "lookback_days":days,
        "all_original_audit_point_rows":raw_count,
        "24_item_matching_audit_rows":sum(existing.values()),
        "24_item_first_issued_active_UTC_hours":len(points),
        "original_audit_record_sources":dict(sorted(sources.items())),
        "exclusions":dict(sorted(invalid.items())),
        "overall":_stats(points),
        "per_item":{key:_stats(grouped[key]) for key in sorted(allowed)},
        "per_projection_depth":{
            key:_stats(v) for key,v in sorted(bydepth.items())},
        "recent_original_active_departure_examples":[{
            "item_key":p["item_key"],
            "issued_UTC":_datetime(p["created_at"]),
            "prediction_Pn":p["prediction_number"],
            "projected_depth":p["depth"],
            "departure_by_UTC":_datetime(p["predicted_leave_by_epoch"]),
            "arrival_UTC":_datetime(p["predicted_arrival_epoch"]),
            "expected_restock_UTC":_datetime(p["predicted_restock_epoch"]),
            "window_hit":p["window_hit"],
            "arrival_cycle_hit":p["arrival_hit"],
            "ground_truth_valid":p["ground_truth_valid"],
        } for p in sorted(points,key=lambda z:z["created_at"],reverse=True)[:10]],
        "restock_hit_is_not_same_as_30_stock_on_arrival":True,
        "cycle_arrival_flag_is_not_direct_stock_30_poll_observation":True,
        "country_provider_age_not_certified":True,
        "original_forecast_signatures_not_every_five_minutes":True,
        "no_gameplay_trips_confirmed":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=30)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    out=audit(days=a.days)
    if a.json:
        print(json.dumps(out,sort_keys=True))
        return
    print("===== ORIGINAL WEBSITE PREDICTION V2 RESTOCK AND DEPARTURE AUDIT =====")
    print("Status:",out["status"])
    if "overall" in out:
        print("Overall:",json.dumps(out["overall"],sort_keys=True))
        print("By forecast depth:",json.dumps(
            out["per_projection_depth"],sort_keys=True))
        for item,data in out["per_item"].items():
            if data["selected_first_issued_active_item_hours"]:
                print(item,json.dumps(data,sort_keys=True))
        print("Recent original leave-by audits:",json.dumps(
            out["recent_original_active_departure_examples"],sort_keys=True))
    print("Old cycle arrival hit != verified 30-stock-at-arrival.")


if __name__=="__main__":
    main()
