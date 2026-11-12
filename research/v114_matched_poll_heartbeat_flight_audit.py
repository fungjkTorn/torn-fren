"""V114 evidence-complete paired flight analysis using collector poll heartbeats.

V113 required TWO item stock-CHANGE records near each hypothetical landing.
That is a selection bias: the stock_history table stores item changes, not
poll snapshots. A steady stocked item may have no recent change rows.

V114 replays V113's exact model selection and the same 0/5/15/30 minute
issues, but evaluates counterfactual landings through V88's existing
successful POLL HEARTBEAT bracket evidence. Identical departure choices
remain paired outcomes with provably zero policy difference.

A poll heartbeat certifies collector fetch success, NOT a fresh country
stock update. V88 carries the most recent change-only item stock row
forward to each poll. Keep a MORE CONSERVATIVE default max age of 3600s
for that carried row instead of V88's broad 24h allowance.

The upstream YATA per-country 'update' epoch was not saved; success is a
historical poll-state PROXY, not certified game-world arrival stock.
Both comparisons use exactly the same scoring function. No player flights
were observed. Historical holdout seen and offsets correlated. All source
SQLite access is query_only; no API, website, or collector actions.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.v88_poll_state_forward_report import observation as poll_observation
from research.v109_raw_restock_transition_event_audit import (
    SOURCE,TARGETS,read_collector_item
)
from research.v113_phase_offset_departure_comparison import (
    analyze_item,OFFSETS_MINUTES
)
from research.v60_private_snapshot_probe import approved_collector_source

MAX_STOCK_CHANGE_AGE_SECONDS=3600
MAX_EPISODES_PER_PHASE=25


def heartbeat_arrival_evidence(conn,country,item,arrival,asof, *,
                               max_stock_change_age=MAX_STOCK_CHANGE_AGE_SECONDS,
                               poll_func=poll_observation):
    """Translate existing V88 poll evidence into V113 paired evidence schema.

    A global collector heartbeat does not assert that this COUNTRY was
    refreshed. No per-country provider-age verification is possible.
    """
    if not 60<=max_stock_change_age<=86400:
        raise ValueError("invalid forward-filled state age cap")
    status,hit,detail=poll_func(
        conn,country,item,int(arrival),int(asof))
    detail=detail or {}
    age_values=[
        detail.get("pre_state_age_s"),
        detail.get("post_state_age_s")
    ]
    newest_state_age=(
        max(int(v) for v in age_values)
        if all(type(v) in (int,float) and v>=0 for v in age_values)
        else None
    )
    if hit is not None and newest_state_age is None:
        raise AssertionError("scored polling proxy lacks stock change ages")
    if (hit is not None and
        newest_state_age>max_stock_change_age):
        status="CARRIED_STOCK_CHANGE_TOO_OLD"
        hit=None
    return {
        "arrival_epoch":int(arrival),
        "strict_bracket_proxy":hit,
        "last_known_proxy":None,
        "reason":status,
        "poll_bracket_data":detail,
        "last_change_state_age_seconds":newest_state_age,
        "polling_proxy_country_freshness_verified":False,
    }


def analyze_heartbeat_item(conn,obs,gaps,*,country,item,asof,
                           max_episodes=12,
                           max_stock_change_age=MAX_STOCK_CHANGE_AGE_SECONDS):
    statuses=Counter()
    def scored(observations,epochs,gaplist,arrival):
        ev=heartbeat_arrival_evidence(
            conn,country,item,arrival,asof,
            max_stock_change_age=max_stock_change_age)
        statuses[ev["reason"]]+=1
        return ev
    result=analyze_item(
        obs,gaps,item_key=f"{country}:{item}",
        max_per_phase=max_episodes,scorer=scored)
    result["poll_state_evidence_statuses"]=dict(sorted(statuses.items()))
    result["max_accepted_carry_forward_stock_row_age_seconds"]=(
        max_stock_change_age)
    result["scoring_method"]="V88_GLOBAL_POLL_BRACKET_STATE_CARRIED_FORWARD"
    result["provider_country_asof_timestamp_available"]=False
    result["genuine_gameplay_success_certified"]=False
    return result


def pretty(out):
    print("===== V114 V113 MATCHED FLIGHTS / SUCCESSFUL POLL-STATE BRACKETS =====")
    print("Global fetch/poll does NOT guarantee country-specific fresh source stock.")
    for name,item in out["items"].items():
        print("====",name,item["item_key"],"====")
        print("scoring_statuses:",json.dumps(
            item["poll_state_evidence_statuses"],sort_keys=True))
        for phase,groups in item["phases"].items():
            print("ORIGINAL EVENT",phase)
            for offset,g in groups.items():
                d=g["DELAYED_ONLY_matched_proxy"]
                model=d["model"]
                now=d["depart_now"]
                print(
                    f'  +{offset:>2}m issues={g["eligible_decision_issues"]:2}'
                    f' same={g["same_as_now"]:2}'
                    f' delayed={g["model_delayed"]:2}'
                    f' abstained={g["model_abstained"]:2}'
                    f' | DELAYED-ONLY model={model["evidence_hits"]}H/'
                    f'{model["evidence_misses"]}M/{model["uncertain"]}U'
                    f' vs now={now["evidence_hits"]}H/'
                    f'{now["evidence_misses"]}M/{now["uncertain"]}U')
                print("      paired fully-known:",d["paired_known_comparisons"],
                      "known model-only positives:",
                      d["certain_model_better_now_worse"],
                      "known now-only positives:",
                      d["certain_model_worse_now_better"])
                print("      unknown-outcome difference bounds:",
                      json.dumps(d[
                        "possible_delta_success_per_anchor_bounds"],
                        sort_keys=True))
    print("RESEARCH PROXY ONLY; old collector lacks country-update epochs.")
    print("Not player gameplay success, not fresh-data-certified accuracy.")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",choices=["redfox","nessie","both"],
                   default="both")
    p.add_argument("--events-per-phase",type=int,default=12)
    p.add_argument("--max-stock-change-age",type=int,
                   default=MAX_STOCK_CHANGE_AGE_SECONDS)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not 1<=a.events_per_phase<=MAX_EPISODES_PER_PHASE:
        p.error("events per phase must be 1..25")
    if not 60<=a.max_stock_change_age<=86400:
        p.error("max stock change age must be 60..86400 seconds")
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved stock source")
    names=TARGETS if a.target=="both" else {
        a.target:TARGETS[a.target]}
    tick=time.monotonic()
    with closing(sqlite3.connect(
        Path(SOURCE).resolve(strict=True).as_uri()+"?mode=ro",
        uri=True,timeout=15)) as db:
        db.execute("PRAGMA query_only=ON")
        hb=db.execute(
            """SELECT max(timestamp), count(*) FROM poll_heartbeats
               WHERE mode='poll-cycle' AND success=1"""
        ).fetchone()
        if hb[0] is None:
            raise SystemExit("No successful historical poll heartbeats")
        last_poll=int(hb[0])
        items={}
        for name,(country,item) in names.items():
            obs,gaps=read_collector_item(db,country,item)
            items[name]=analyze_heartbeat_item(
                db,obs,gaps,country=country,item=item,
                asof=last_poll,
                max_episodes=a.events_per_phase,
                max_stock_change_age=a.max_stock_change_age)
    report={
        "status":"V114_MATCHED_FLIGHT_POLL_HEARTBEAT_STATE_AUDIT",
        "read_only":True,
        "same_event_offset_cohort_as_v113":True,
        "country_fresh_provider_update_epoch_available":False,
        "actual_player_flights_observed":False,
        "predeclared_offsets_minutes":list(OFFSETS_MINUTES),
        "max_last_item_change_age_seconds":a.max_stock_change_age,
        "successfully_polled_historic_snapshots":int(hb[1]),
        "historical_last_poll_epoch":last_poll,
        "duration_seconds":round(time.monotonic()-tick,2),
        "items":items,
    }
    if a.json:print(json.dumps(report,sort_keys=True))
    else:
        pretty(report)
        print("poll_count",report["successfully_polled_historic_snapshots"],
              "elapsed_s",report["duration_seconds"])


if __name__=="__main__":
    main()
