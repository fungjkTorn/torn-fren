"""V135: single compact morning brief from three UNCHANGED research audits.

- original website Prediction V2 archival restock windows / cycle arrivals
- historical first-hour frozen V75 poll-state <= / >=30 stock at arrival
- experimental 24-item V128 actual as-issued arrival-stock proxy (V129)
- V128 departure wait / forward-watch reconfirmation / same-input churn

Source inventory, maturity and provider-freshness disclaimers intact.
No API calls, imports of live prediction engine, retroactive predictions,
db writes, model tuning, systemd changes or website changes.
"""
from __future__ import annotations

import argparse
import json
import time

from research.v131_multiledger_historical_arrival_audit import full_audit
from research.v132_departure_timing_quality_audit import audit as timing_audit
from research.v134_original_graph_v2_audit import audit as original_v2_audit


def assemble(*,now=None,old_v75_days=3,new_days=2,old_graph_days=30,
             multiple_ledger=full_audit,
             timing=timing_audit,
             oldgraph=original_v2_audit):
    asof=int(time.time() if now is None else now)
    archived=oldgraph(asof=asof,days=old_graph_days)
    frozen=multiple_ledger(asof=asof,days=old_v75_days)
    new=timing(now=asof,days=new_days)
    if frozen["all_24_roster_count"]!=24 or new["all_24_items"]!=24:
        raise ValueError("exact 24-item audit basis changed")
    old=frozen["old_V75"]
    newer=frozen["new_V128"]
    result={
        "status":"V135_HISTORICAL_OLD_GRAPH_AND_NEW_DEPARTURE_BRIEF",
        "asof_epoch":asof,
        "collector_and_sidecars_read_only":True,
        "original_graph_v2":{
            "status":archived["status"],
            "historical_window_days":old_graph_days,
            "overall":archived.get("overall"),
            "by_projection_depth":archived.get("per_projection_depth"),
            "per_item":archived.get("per_item"),
            "selected_hourly_original_graph_audits":archived.get(
                "24_item_first_issued_active_UTC_hours"),
        },
        "prior_v75":{
            "status":old["status"],
            "historical_window_days":old_v75_days,
            "overall":old.get("summary"),
            "per_item":old.get("per_item"),
            "unknown_proxy_reasons":old.get(
                "missing_and_proxy_reason_counts"),
        },
        "new_v128":{
            "status":newer["status"],
            "registered_raw_five_minute_rows":newer.get(
                "raw_five_minute_rows"),
            "first_issued_item_UTC_hours":newer.get(
                "first_issued_item_hour_cohorts"),
            "observed_30_stock_arrival_proxy":newer.get("summary"),
            "per_item":newer.get("per_item"),
            "departure_timing_quality":{
                "status":new["status"],
                "overall":new["overall"],
                "per_item":new["per_item"],
            },
        },
        "optional_older_research_ledgers":{
            **frozen["older_sidecar_inventory"],
        },
        "limitations":{
            "original_graph_restock_cycle_hit_not_verified_30_stock_at_arrival":True,
            "V75_and_V128_stock_proxy_not_gameplay":True,
            "country_specific_source_update_age_unverified":True,
            "repeated_item_hours_not_independent_restock_cycles":True,
            "future_watch_not_a_go_decision_until_fresh_reconfirmation":True,
            "simulated_scores_not_calibrated":True,
        },
    }
    return result


def short_summary(report):
    old=report["original_graph_v2"]
    v75=report["prior_v75"]
    v128=report["new_v128"]
    timing=v128["departure_timing_quality"]
    lines=[
        "===== V135 ONE-PASS OVERNIGHT RESEARCH EVIDENCE =====",
        f"Research evaluation UTC epoch: {report['asof_epoch']}",
        "OLD ORIGINAL GRAPH V2: "+old["status"],
        "Original graph restock/cycle accuracy: "+json.dumps(
            old.get("overall"),sort_keys=True),
        "OLDER V75 HISTORICAL ARRIVAL STOCK: "+v75["status"],
        "V75 versus leave now, first-item-UTC-hour: "+json.dumps(
            v75.get("overall"),sort_keys=True),
        "CURRENT 24-ITEM V128 RECORDER: "+v128["status"],
        "V128 observed arrival stock and matched leave-now: "+json.dumps(
            v128.get("observed_30_stock_arrival_proxy"),sort_keys=True),
        "V128 latest time-to-leave coverage/forecast shifts: "+json.dumps({
            k:v for k,v in timing["overall"].items()
            if k not in ("examples_of_shift_over_15min_same_collector_state",
                         "status_counts","median_absolute_departure_shift_same_obs_minutes")
        },sort_keys=True),
    ]
    byv2=old.get("per_item") or {}
    byv75=v75.get("per_item") or {}
    byv128=v128.get("per_item") or {}
    bytiming=timing["per_item"]
    names=sorted(set(byv2)|set(byv75)|set(byv128)|set(bytiming))
    lines.append("===== ITEM-BY-ITEM CHECKPOINT =====")
    for name in names:
        oldx=byv2.get(name,{})
        past=byv75.get(name,{})
        recent=byv128.get(name,{})
        move=bytiming.get(name,{})
        volume=(
            (oldx.get("selected_first_issued_active_item_hours") or 0)+
            (past.get("first_item_UTC_hourly_starts") or 0)+
            (recent.get("first_issue_UTC_item_hours") or 0)+
            (move.get("issued_five_minute_snapshots") or 0)
        )
        if volume==0:continue
        compact={
            "old_v2_valid_restock_cycles":
                oldx.get("resolved_valid_target_cycles",0),
            "old_v2_restock_window_hit_fraction":
                oldx.get("observed_restock_window_hit_rate"),
            "old_v2_arrival_inside_restock_depletion_fraction":
                oldx.get("arrival_inside_target_cycle_rate"),
            "v75_matched_flights":
                past.get("matched_flight_outcomes",0),
            "v75_model_only_vs_leave_now_only_net":
                past.get("model_minus_now_only_known_pairs",0),
            "v128_issued_ticks":
                move.get("issued_five_minute_snapshots",0),
            "v128_mature_stock_proxies":
                recent.get("model_proxy_success",0)+
                recent.get("model_proxy_miss",0),
            "v128_model_stocked":
                recent.get("model_proxy_success",0),
            "v128_model_below30":
                recent.get("model_proxy_miss",0),
            "v128_future_watches":
                move.get("issued_future_watches_not_executable",0),
            "v128_watch_reconfirmed":
                move.get("maturity_counts_for_first_hour_proposals",{}).get(
                    "matured_watch_properly_reconfirmed",0),
            "v128_wait_mean_minutes":
                move.get("mean_proposed_wait_minutes"),
        }
        lines.append(name+" "+json.dumps(compact,sort_keys=True))
    lines.append("===== CAUTION =====")
    lines.append(json.dumps(report["limitations"],sort_keys=True))
    lines.append("No real flights/purchases confirmed. Country feed age unknown.")
    lines.append("No source, model, timer, website, or research sidecar writes.")
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old-days",type=int,default=3)
    p.add_argument("--graph-days",type=int,default=30)
    p.add_argument("--v128-days",type=int,default=2)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    result=assemble(old_v75_days=a.old_days,
                    new_days=a.v128_days,
                    old_graph_days=a.graph_days)
    print(json.dumps(result,sort_keys=True)
          if a.json else short_summary(result))


if __name__=="__main__":
    main()
