"""V98: decision-ready vs future-watch real as-issued V75 accuracy audit.

The V76 '99.2%' figure is selected near item changes, and 24h audit has
more than 1200 forecast targets. V98 scores ALL valid targets in an issuance
window, with *no 1200-event truncation*, using V88's read-only poll-time
reconstructed stock-state proxy.

Crucially, separates departure within the issued snapshot's 5-min lifetime
(a user could plausibly commit now) from >5min forecasts (WATCH, not a
guaranteed later executable recommendation). It checks the same-point-time
immediate-departure counterfactual independently of target maturity.

Not calibrated game-world accuracy: YATA per-country age was not saved,
provider bounces and shared restocks may correlate many points, and nothing
here proves a real player flight or an independent restock opportunity.
No source writes, no collection or inference changes, no gameplay action.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from research.v76_forward_research_report import (
    V75, SOURCE, MAX_CANDIDATE_ROWS, GRACE, ro, select_unique, strict_samples
)
from research.v88_poll_state_forward_report import observation
from research.v89_pending_horizon_diagnostic import stage,wait_bucket
from research.plushie_champions.common import TRAVEL_SECONDS
from research.v60_private_snapshot_probe import approved_collector_source

MAX_TARGETS = 12000
MAX_DAYS = 3
READY_WINDOW_SECONDS = 300
SUCCESS="POLL_STATE_PROXY_SUCCESS"
MISS="POLL_STATE_PROXY_MISS"


def audit(*, ledger=V75, source=SOURCE, now=None, days=1,
          max_targets=MAX_TARGETS, include_direct=True):
    if not 1<=days<=MAX_DAYS or not 1<=max_targets<=MAX_TARGETS:
        raise ValueError("bound retrospective issue window and target count")
    asof=int(time.time() if now is None else now)
    if Path(ledger).resolve(strict=True)==Path(source).resolve(strict=True):
        raise ValueError("private ledger and live collector may not be same DB")
    with closing(ro(ledger)) as e:
        events,raw,excluded=select_unique(
            e,start=asof-days*86400,end=asof)
    if len(events)>max_targets:
        raise ValueError("too many target arrivals for bounded offline audit")

    partitions={
        "ISSUED_READY_WITHIN_5M":{
            "outcomes":Counter(),"pending_stage":Counter(),
            "wait_at_issue":Counter(),"per_item":defaultdict(Counter),
            "matched":Counter(),"strict":Counter()},
        "FUTURE_WATCH_GT_5M":{
            "outcomes":Counter(),"pending_stage":Counter(),
            "wait_at_issue":Counter(),"per_item":defaultdict(Counter),
            "matched":Counter(),"strict":Counter()},
    }
    with closing(ro(source)) as stock:
        for r in events:
            key=r["item_key"]
            country,item=key.split(":",1)
            issued=int(r["computed_at"])
            dep=int(r["departure"])
            arr=int(r["arrival"])
            is_ready=(0<=dep-issued<=READY_WINDOW_SECONDS
                      and dep<=int(r["valid_until"]))
            bucket="ISSUED_READY_WITHIN_5M" if is_ready else "FUTURE_WATCH_GT_5M"
            p=partitions[bucket]
            p["wait_at_issue"][wait_bucket(dep-issued)]+=1
            p["per_item"][key]["targets"]+=1
            if bucket=="FUTURE_WATCH_GT_5M":
                p["per_item"][key]["non_actionable_at_issue"]+=1
            stage_now=stage(r,asof)
            p["pending_stage"][stage_now]+=1

            label,success,_=observation(stock,country,item,arr,asof)
            p["outcomes"][label]+=1
            p["per_item"][key][label]+=1

            if include_direct and label!="PENDING":
                # This is NOT direct entire-snapshot observation. It is the
                # limited change-only stock-history event within +10s.
                p["strict"][strict_samples(stock,country,item,arr)]+=1

            immediately_at=issued+TRAVEL_SECONDS[country]
            baseline,base_success,_=observation(
                stock,country,item,immediately_at,asof)
            if success is not None and base_success is not None:
                pair=("BOTH_SUCCESS" if success and base_success else
                      "RECOMMENDATION_ONLY" if success else
                      "IMMEDIATE_ONLY" if base_success else
                      "BOTH_MISS")
                p["matched"][pair]+=1
                p["per_item"][key]["MATCHED_"+pair]+=1
            elif success is not None:
                p["matched"]["BASELINE_NOT_SCORABLE"]+=1
            elif base_success is not None:
                p["matched"]["RECOMMENDATION_NOT_SCORABLE"]+=1
    def build(p):
        successes=p["outcomes"][SUCCESS]
        misses=p["outcomes"][MISS]
        scored=successes+misses
        total=sum(p["outcomes"].values())
        per={}
        for key,c in sorted(p["per_item"].items()):
            hits=c[SUCCESS];fails=c[MISS];n=hits+fails
            per[key]={
                "arrival_targets":c["targets"],
                "proxy_scorable":n,
                "proxy_success":hits,
                "proxy_miss":fails,
                "proxy_success_rate":round(hits/n,4) if n else None,
                "waiting_for_departure_or_hypothetical_flight":
                    c.get("PENDING",0),
                "matched_both_success":c["MATCHED_BOTH_SUCCESS"],
                "matched_immediate_only":c["MATCHED_IMMEDIATE_ONLY"],
                "matched_recommendation_only":c["MATCHED_RECOMMENDATION_ONLY"],
            }
        return {
            "arrival_targets":total,
            "proxy_scorable":scored,
            "proxy_success":successes,
            "proxy_miss":misses,
            "proxy_success_fraction":round(successes/scored,4) if scored else None,
            "outcomes":dict(sorted(p["outcomes"].items())),
            "maturation_stage":dict(sorted(p["pending_stage"].items())),
            "departure_wait_buckets":dict(sorted(p["wait_at_issue"].items())),
            "matched_depart_now_comparison":dict(sorted(p["matched"].items())),
            "change_only_samples_within_plus_10s":dict(sorted(p["strict"].items())),
            "per_item":per,
        }
    out={
        "status":"V98_READY_VS_WATCH_FORWARD_PROXY_REPORT",
        "research_only":True,
        "collector_written":False,
        "sidecar_written":False,
        "certified_actual_player_success":False,
        "exact_10s_accuracy_certified":False,
        "country_provider_update_age_available":False,
        "unique_independent_stock_windows":None,
        "asof_epoch":asof,"issued_window_days":days,
        "raw_as_issued_rows":raw,
        "invalid_or_abstained_issued_rows":excluded,
        "distinct_item_arrival_targets":len(events),
        "duplicate_item_arrival_issue_rows":raw-excluded-len(events),
        "partitions":{k:build(v) for k,v in partitions.items()},
        "warning":(
            "Five-minute issued snapshot validity does not authorize a "
            "six-hour-later gameplay departure. V88 outcomes are poll-state "
            "proxies reconstructed from change-only stock rows and global "
            "heartbeats, NOT direct country-verified YATA updates. Repeated "
            "targets can share one stock window. 180s evidence stays separate "
            "from +10s precise evidence."
        )
    }
    assert sum(p["arrival_targets"] for p in out["partitions"].values())==len(events)
    return out


def readable(result):
    print("===== V98 24H REAL FORWARD ACCURACY: READY VS FUTURE WATCH =====")
    for k in ("issued_window_days","raw_as_issued_rows",
              "invalid_or_abstained_issued_rows",
              "distinct_item_arrival_targets",
              "duplicate_item_arrival_issue_rows"):
        print(f"{k}: {result[k]}")
    for title,p in result["partitions"].items():
        print(f"===== {title} =====")
        for k in ("arrival_targets","proxy_scorable","proxy_success",
                  "proxy_miss","proxy_success_fraction"):
            print(f"{k}: {p[k]}")
        print("Maturation:",json.dumps(p["maturation_stage"],sort_keys=True))
        print("Outcomes:",json.dumps(p["outcomes"],sort_keys=True))
        print("Depart-now matched:",json.dumps(
            p["matched_depart_now_comparison"],sort_keys=True))
        print("Change-only +10s sample:",json.dumps(
            p["change_only_samples_within_plus_10s"],sort_keys=True))
        print(f'{"ITEM":30} {"TARGETS":>7} {"SCORED":>7} {"HITS":>6} {"MISSES":>7} {"RATE":>7}')
        for key,r in p["per_item"].items():
            hit=r["proxy_success"];scored=r["proxy_scorable"]
            rate=f'{hit/scored:.1%}' if scored else 'N/A'
            print(f'{key:30} {r["arrival_targets"]:7d} '
                  f'{scored:7d} {hit:6d} {r["proxy_miss"]:7d} {rate:>7}')
    print("===== IMPORTANT: PROXY ONLY, NO VERIFIED EXACT ARRIVAL ACCURACY =====")
    print(result["warning"])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days",type=int,default=1)
    parser.add_argument("--max-targets",type=int,default=MAX_TARGETS)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("STOP: collector path not approved")
    result=audit(days=args.days,max_targets=args.max_targets)
    if args.json:
        print(json.dumps(result,sort_keys=True))
    else:
        readable(result)

if __name__=="__main__":
    main()
