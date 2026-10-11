"""V118: why 5-minute research forecasts fail to become departures.

V117: 7/50 first hourly starts produced an executable flight (Red Fox 7,
Nessie 0), 27 finished an 8-hour watch without such a proposal and 16
had not matured. This diagnostic keeps V117's EXACT same start cohort,
forecast validity rules, first-ready selector, and 8-hour horizon.

For each start, examine ONLY frozen forecast issuance/replan timestamps:
- how many same-family valid ticks occurred within the observation window;
- gaps in stored research ticks (as distinct from invalid/abstained ticks);
- forecast waiting-lead distribution and nearest lead;
- consecutive scheduled departure drifts and whether watch is "rolling away";
- whether the first predicted departure is later reconfirmed in a nearby
  five-minute-valid research tick.
NEVER use eventual observed stocks for the diagnosis or forecast selection.
Future-issued ticks are used only chronologically as they would have appeared.
Do not mistake original distant watches for executable departure instructions.

This is a research-only observational diagnostic and does not test actual
player flights, freshness of upstream per-country stock, or true restock time.
Read both SQLite sources in read-only mode; no collector, website, VM timer,
API, production worker, or gameplay actions.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing

from research.v76_forward_research_report import (
    V75,eligible,ro,MAX_PROXY_EVENTS
)
from research.v88_poll_state_forward_report import SOURCE
from research.v115_targeted_v88_forward_evidence import ITEMS
from research.v116_attributed_hourly_forward_audit import (
    select_candidates,first_per_item_hour
)
from research.v117_first_executable_replan_audit import (
    first_actionable_tick,future_candidate_timelines
)
from research.v60_private_snapshot_probe import approved_collector_source

MAX_WAIT=8*3600
STEP=300
NEARBY_ISSUE_SECONDS=600


def target_recheck(original,timeline,times,asof):
    """One last frozen proposal issued during 10m before original depart.

    This is a research persistence check, NOT a candidate flight selection.
    A future original target is pending; no outcome-fitted nearest proposal.
    """
    initial_dep=int(original["departure"])
    if asof<initial_dep+STEP:
        return {"status":"ORIGINAL_TARGET_NOT_MATURE",
                "shift_seconds":None}
    pos=bisect.bisect_right(times,initial_dep)
    left=bisect.bisect_left(times,initial_dep-NEARBY_ISSUE_SECONDS)
    nearby=timeline[left:pos]
    if not nearby:
        return {"status":"NO_REPLAN_NEAR_ORIGINAL_TARGET",
                "shift_seconds":None}
    last=nearby[-1]
    if not eligible(last):
        return {"status":"LAST_REPLAN_INVALID_OR_ABSTAINED",
                "shift_seconds":None,
                "last_status":last["status"]}
    delta=int(last["departure"])-initial_dep
    if (int(last["departure"])<=int(last["valid_until"])
        and abs(delta)<=STEP):
        category="ORIGINAL_TARGET_RECONFIRMED_ACTIONABLE"
    elif delta>STEP:
        category="ORIGINAL_TARGET_SHIFTED_LATER"
    elif delta<-STEP:
        category="ORIGINAL_TARGET_SHIFTED_EARLIER"
    else:
        category="ORIGINAL_TARGET_NOT_EXECUTABLE_AT_RECHECK"
    return {
        "status":category,
        "shift_seconds":delta,
        "last_replan_issue":int(last["computed_at"]),
        "last_replan_lead_seconds":(
            int(last["departure"])-int(last["computed_at"]))
    }


def diagnose_start(original,rows,times,*,asof):
    begin=int(original["computed_at"])
    end=min(int(asof),begin+MAX_WAIT)
    left=bisect.bisect_left(times,begin)
    right=bisect.bisect_right(times,end)
    stream=rows[left:right]
    decision=first_actionable_tick(original,rows,times,now=asof)
    if not stream or int(stream[0]["computed_at"])!=begin:
        raise AssertionError("missing initial issued candidate")
    if stream[0]["item_key"]!=original["item_key"]:
        raise AssertionError("mis-scoped future candidate")
    statuses=Counter()
    leads=[]
    proposals=[]
    other=0
    for row in stream:
        if row["model_family"]!=original["model_family"]:
            other+=1
            continue
        statuses[str(row["status"])]+=1
        if eligible(row):
            issued=int(row["computed_at"])
            depart=int(row["departure"])
            if not issued<=depart<=issued+MAX_WAIT:
                raise AssertionError("eligible proposal violates horizon")
            leads.append(depart-issued)
            proposals.append((issued,depart))
    gaps=[
        int(b["computed_at"])-int(a["computed_at"])
        for a,b in zip(stream,stream[1:])
    ]
    large_gaps=[x for x in gaps if x>2*STEP]
    drifts=[
        b[1]-a[1]
        for a,b in zip(proposals,proposals[1:])
        if 0<b[0]-a[0]<=2*STEP
    ]
    future_only=sum(x>STEP for x in leads)
    recheck=target_recheck(original,rows,times,asof)
    completed=asof>=begin+MAX_WAIT
    if completed and decision["status"]=="STILL_WAITING_HORIZON_NOT_MATURE":
        raise AssertionError("mature horizon still pending")
    return {
        "initial_epoch":begin,
        "initial_departure_epoch":int(original["departure"]),
        "item_key":original["item_key"],
        "model_family":original["model_family"],
        "first_ready_status":decision["status"],
        "first_ready_epoch":decision["departure"],
        "horizon_complete":completed,
        "tracked_seconds":end-begin,
        "all_stored_ticks":len(stream),
        "same_family_stored_ticks":len(stream)-other,
        "other_family_ticks":other,
        "same_family_stored_statuses":dict(sorted(statuses.items())),
        "valid_proposal_ticks":len(leads),
        "watch_only_valid_proposals":future_only,
        "ready_valid_proposals":len(leads)-future_only,
        "min_valid_departure_lead_seconds":min(leads) if leads else None,
        "median_valid_departure_lead_seconds":(
            int(statistics.median(leads)) if leads else None),
        "tick_gaps_over_10_minutes":len(large_gaps),
        "largest_tick_gap_seconds":max(gaps) if gaps else None,
        "valid_adjacent_departure_drift_pairs":len(drifts),
        "future_departure_shifted_later_pairs":sum(x>STEP for x in drifts),
        "future_departure_shifted_earlier_pairs":sum(x<-STEP for x in drifts),
        "future_departure_roughly_stable_pairs":sum(abs(x)<=STEP for x in drifts),
        "median_departure_shift_seconds":(
            int(statistics.median(drifts)) if drifts else None),
        "original_departure_recheck":recheck,
    }


def audit(*,ledger=V75,now=None,hours=24,
          keys=tuple(ITEMS.values()),limit=MAX_PROXY_EVENTS):
    if (not 1<=hours<=24 or not 1<=limit<=MAX_PROXY_EVENTS
        or not 1<=len(keys)<=len(ITEMS) or len(set(keys))!=len(keys)
        or not set(keys)<=set(ITEMS.values())):
        raise ValueError("invalid bounded diagnostic")
    asof=int(time.time() if now is None else now)
    start=asof-hours*3600
    with closing(ro(ledger)) as db:
        selected,raw,invalid=select_candidates(
            db,start=start,end=asof,keys=keys,limit=limit)
        anchors=first_per_item_hour(selected)
        timeline,times,n=future_candidate_timelines(
            db,start=start,end=asof,keys=keys)
        diagnoses=[diagnose_start(
            anchor,timeline[anchor["item_key"]],
            times[anchor["item_key"]],asof=asof)
            for anchor in anchors]
    groupings=defaultdict(list)
    for row in diagnoses:
        groupings[row["item_key"]].append(row)
    def aggregate(rows):
        c=Counter()
        for row in rows:
            c["starts"]+=1
            c[row["first_ready_status"]]+=1
            c["valid_tick_total"]+=row["valid_proposal_ticks"]
            c["watch_only_proposals"]+=row["watch_only_valid_proposals"]
            c["ready_valid_proposals"]+=row["ready_valid_proposals"]
            c["all_stored_ticks"]+=row["all_stored_ticks"]
            c["large_tick_gaps_over_10m"]+=row["tick_gaps_over_10_minutes"]
            c["no_valid_replans"]+=int(row["valid_proposal_ticks"]<=1)
            c["no_ready_proposals"]+=int(row["ready_valid_proposals"]==0)
            c["drift_later_pairs"]+=row["future_departure_shifted_later_pairs"]
            c["drift_earlier_pairs"]+=row["future_departure_shifted_earlier_pairs"]
            c["stable_pairs"]+=row["future_departure_roughly_stable_pairs"]
            c["departure_drift_adjacent_pairs"]+=(
                row["valid_adjacent_departure_drift_pairs"])
            c["recheck_"+row["original_departure_recheck"]["status"]]+=1
            if row["min_valid_departure_lead_seconds"] is not None:
                c["nearest_lead_under_15m"]+=int(
                    row["min_valid_departure_lead_seconds"]<=900)
                c["nearest_lead_over_60m"]+=int(
                    row["min_valid_departure_lead_seconds"]>3600)
        return dict(sorted(c.items()))
    return {
        "status":"V118_FIVE_MINUTE_WATCH_CONVERGENCE_AND_TICK_COVERAGE",
        "read_only":True,"research_only":True,
        "same_first_per_item_hour_cohort_as_v117":True,
        "uses_future_stock_to_select_departure":False,
        "fresh_country_provider_update_epoch_available":False,
        "actual_player_flights_observed":False,
        "hours":hours,
        "asof_epoch":asof,
        "selected_original_valid_arrivals":len(selected),
        "raw_initial_candidate_rows":raw,
        "invalid_initial_rows":invalid,
        "raw_tracked_issued_ticks":n,
        "hourly_starts":len(anchors),
        "overall":aggregate(diagnoses),
        "per_item":{key:aggregate(rows) for key,rows in sorted(groupings.items())},
        "examples":[
            {k:v for k,v in row.items() if k in (
                "initial_epoch","item_key","model_family",
                "first_ready_status","all_stored_ticks",
                "valid_proposal_ticks","watch_only_valid_proposals",
                "min_valid_departure_lead_seconds",
                "tick_gaps_over_10_minutes",
                "median_departure_shift_seconds",
                "original_departure_recheck"
            )}
            for row in diagnoses[:8]
        ],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--items",nargs="+",choices=tuple(ITEMS),
                   default=["redfox","nessie"])
    p.add_argument("--limit",type=int,default=MAX_PROXY_EVENTS)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved production collector path")
    report=audit(hours=a.hours,limit=a.limit,
                 keys=tuple(ITEMS[k] for k in dict.fromkeys(a.items)))
    if a.json:
        print(json.dumps(report,sort_keys=True))
        return
    print("===== V118 WHY FUTURE WATCHES NEVER CONVERGE =====")
    print("Same V117 cohort; V75 frozen 5m research ticks only.")
    print("Hour starts:",report["hourly_starts"],
          "valid initial:",report["selected_original_valid_arrivals"],
          "raw ticks:",report["raw_tracked_issued_ticks"])
    print("Overall:",json.dumps(report["overall"],sort_keys=True))
    for item,data in report["per_item"].items():
        print(item,json.dumps(data,sort_keys=True))
    print("Sample causal research tick diagnostics:",
          json.dumps(report["examples"][:4],sort_keys=True))
    print("NO LIVE CHANGES. Watch persistence not certified game or travel.")


if __name__=="__main__":
    main()
