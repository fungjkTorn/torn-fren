"""V133: safe full-24 PRIVATE research departure-display contract.

Standalone read-only view model for a future optional research panel,
NOT a web endpoint, not the public graph, and NOT an actionable game-trip
directive. Preserves old V2 predicted-restock visualization separately.
V128 does not estimate a single next restock time; it estimates arrival
availability under empirical simulated HIGH/LOW phases. Never label a
scenario fraction a certified success probability, never show future WATCH
as GO, and discard expired / incomplete / malformed issue snapshots.

Reads only v128 private sidecar. Any non-5min snapshot is unavailable.
No collector, service or website writes; no future restock claim.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.v128_full24_earliest_shadow import (
    SIDECAR,ROSTER,GENERATION,exact_roster
)
from research.v129_full24_forward_report import ro,_parse

MAX_ISSUE_AGE_SECONDS=300
MAX_CLOCK_SKEW_SECONDS=30
MAX_LOOKAHEAD_SECONDS=8*3600
NEAR_TERM_SECONDS=300
MIN_STOCK=30


def display_record(r,*,now):
    """No countdown for old or uncertified provider-country input."""
    key=r["item_key"]
    issue=int(r["issued_epoch"])
    dep=r["earliest_departure"]
    wait=r.get("wait_minutes")
    base={
        "item_key":key,"research_only":True,
        "forecast_issued_epoch":issue,
        "research_model_family":"V128",
        "latest_observed_stock_quantity":r.get("last_stock_quantity"),
        "observed_phase":r.get("phase"),
        "proposed_departure_epoch":None,
        "proposed_arrival_epoch":None,
        "seconds_until_proposed_departure":None,
        "proposed_wait_minutes_from_issue":wait,
        "current_flight_seconds":r["travel_seconds"],
        "minimum_stock_at_arrival":MIN_STOCK,
        "simulation_arrival_fraction_not_calibrated_probability":
            r.get("earliest_score"),
        "live_country_stock_freshness_verified":False,
        "actual_arrival_stock_verified":False,
        "in_game_travel_executed":False,
        "next_restock_estimate_epoch":None,
        "estimated_stock_depletion_epoch":None,
        "original_v2_graph_unchanged":True,
        "display_never_issues_gameplay_instruction":True,
    }
    if issue>now+MAX_CLOCK_SKEW_SECONDS:
        return dict(base,display_status="FUTURE_ISSUANCE_REJECTED",
                    message="Cannot display future-dated research snapshot.")
    age=now-issue
    if age>MAX_ISSUE_AGE_SECONDS:
        return dict(base,display_status="RESEARCH_SNAPSHOT_EXPIRED",
                    message="No fresh model result; keep existing graph guidance separate.")
    if dep is None:
        return dict(
            base,display_status="NO_QUALIFYING_RESEARCH_DEPARTURE",
            message="No sufficiently supported arrival window in the 8h horizon; no departure advice.")
    if not issue<=dep<=issue+MAX_LOOKAHEAD_SECONDS:
        raise ValueError("invalid research departure range")
    if dep<now:
        return dict(
            base,display_status="PROPOSED_DEPARTURE_ALREADY_PASSED",
            message="This proposed departure has passed; await a fresh issue.")
    state=(
        "RESEARCH_NEAR_TERM_NOT_CERTIFIED"
        if dep-now<=NEAR_TERM_SECONDS else
        "RESEARCH_FUTURE_WATCH_RECHECK_REQUIRED")
    msg=(
        "Research indicates a nearby departure, but this is not a verified GO or game-stock guarantee."
        if state=="RESEARCH_NEAR_TERM_NOT_CERTIFIED" else
        "Future stock opportunity is provisional; recheck with a new forecast near departure.")
    return dict(
        base,display_status=state,
        proposed_departure_epoch=dep,
        proposed_arrival_epoch=r["earliest_arrival"],
        seconds_until_proposed_departure=dep-now,
        message=msg
    )


def preview(*,sidecar=SIDECAR,roster=ROSTER,now=None):
    now=int(time.time() if now is None else now)
    keys=exact_roster(roster)
    with closing(ro(sidecar)) as db:
        batch=db.execute(
            """SELECT issued_epoch,captured_epoch,source_heartbeat,
                      roster_size,policy_id
               FROM v128_ticks WHERE policy_id=?
               ORDER BY issued_epoch DESC LIMIT 1""",(GENERATION,)
        ).fetchone()
        if not batch:
            return {
                "status":"NO_RECORDED_V128_BATCH",
                "read_only":True,
                "items":{},"roster_size":24,
                "country_stock_freshness_verified":False,
            }
        issued,captured,hb,size,policy=map(
            lambda x:x, batch)
        if size!=24 or issued>captured or hb>captured:
            raise ValueError("inconsistent recorded issue batch")
        raw=db.execute(
            """SELECT item_key,issued_epoch,payload_json FROM v128_issued
               WHERE issued_epoch=? AND policy_id=?
               ORDER BY item_key""",(issued,GENERATION)
        ).fetchall()
    records,invalid=_parse(raw,keys)
    if len(records)!=24 or set(x["item_key"] for x in records)!=set(keys):
        return {
            "status":"INCOMPLETE_OR_INVALID_24_ITEM_ISSUE_BATCH",
            "read_only":True,
            "issued_epoch":issued,"stored_row_count":len(raw),
            "valid_rows":len(records),"invalid_counts":dict(invalid),
            "items":{},"roster_size":24,
            "country_stock_freshness_verified":False,
        }
    result={
        r["item_key"]:display_record(r,now=now)
        for r in sorted(records,key=lambda x:x["item_key"])
    }
    statuses=Counter(x["display_status"] for x in result.values())
    return {
        "status":"V133_SAFE_RESEARCH_24_ITEM_DEPARTURE_PANEL_DATA",
        "read_only":True,
        "roster_size":24,
        "selected_issued_epoch":issued,
        "selected_captured_epoch":captured,
        "global_collector_heartbeat_epoch_at_issue":hb,
        "snapshot_age_seconds":now-issued,
        "display_status_counts":dict(sorted(statuses.items())),
        "items":result,
        "all_stock_scores_uncalibrated":True,
        "per_country_provider_update_age_unverified":True,
        "original_website_prediction_v2_untouched":True,
        "no_gameplay_departures_claimed":True,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json",action="store_true")
    a=parser.parse_args()
    result=preview()
    if a.json:
        print(json.dumps(result,sort_keys=True))
        return
    print("===== V133 PRIVATE RESEARCH LEAVE-TIME PREVIEW =====")
    print("Status:",result["status"])
    if "selected_issued_epoch" in result:
        print("Snapshot age:",result["snapshot_age_seconds"],"seconds")
        print("Item decisions:",json.dumps(
            result["display_status_counts"],sort_keys=True))
        for key,item in result["items"].items():
            print(key,item["display_status"],
                  "depart",item["proposed_departure_epoch"],
                  "arrive",item["proposed_arrival_epoch"],
                  "simulation fraction",
                  item["simulation_arrival_fraction_not_calibrated_probability"])
    print("Provisional forecasts only; NO website or game changes.")


if __name__=="__main__":
    main()
