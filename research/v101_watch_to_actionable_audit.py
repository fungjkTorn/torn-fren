"""V101 read-only watch-to-actionable conversion study.

V100 checks whether the LAST replan matches one original future departure
within five minutes. That strict test can miss a good replan which told a
player to depart 1-5 minutes earlier. This audit instead asks whether at ANY
point near the originally projected departure, a later five-minute research
snapshot offered an *actually reachable* departure within 5m/15m of the
original target.

This is NOT long-horizon stability or a hit-rate validation. Multiple original
watch targets can lead to one actionable window; output candidate attribution
counts separately. Never claim verified player travel.

Only reads V75 private SQLite sidecar with mode=ro. Does not use stock data,
YATA, website, API, or gameplay. Strict 1-day limit by default; hard row cap.
"""
from __future__ import annotations

import argparse
import bisect
import json
import time
from collections import Counter,defaultdict
from contextlib import closing

from research.v76_forward_research_report import (
    V75,MAX_CANDIDATE_ROWS,eligible,ro,select_unique
)
from research.v89_pending_horizon_diagnostic import wait_bucket

MAX_DAYS=3
MAX_TARGETS=12000
MAX_ROWS=MAX_CANDIDATE_ROWS
EXECUTABLE_WINDOW=300
NEAR_WINDOW=300
WIDE_WINDOW=900


def converted(original, timeline, times, *, max_shift=WIDE_WINDOW):
    """Consider only snapshots issued no later than original departure."""
    dep=int(original["departure"])
    issued=int(original["computed_at"])
    lower=dep-max_shift-EXECUTABLE_WINDOW
    left=bisect.bisect_left(times,lower)
    right=bisect.bisect_right(times,dep)
    matches=[]
    for c in timeline[left:right]:
        at=int(c["computed_at"])
        if at<=issued or not eligible(c):
            continue
        new_dep=int(c["departure"])
        if not at<=new_dep<=int(c["valid_until"]):
            continue
        delta=new_dep-dep
        if abs(delta)>max_shift:
            continue
        matches.append((abs(delta),-at,new_dep,at,c["item_key"]))
    matches.sort()
    return matches


def audit(*,sidecar=V75,asof=None,days=1,max_targets=MAX_TARGETS):
    if not 1<=days<=MAX_DAYS or not 1<=max_targets<=MAX_TARGETS:
        raise ValueError("invalid bounded research cohort")
    now=int(time.time() if asof is None else asof)
    start=now-days*86400
    with closing(ro(sidecar)) as db:
        events,raw,invalid=select_unique(db,start=start,end=now)
        candidates=db.execute(
            """SELECT item_key,computed_at,stock_as_of,status,
                      valid_until,departure,arrival,actual_player_departure
               FROM v42_candidate_decisions
               WHERE computed_at>=? AND computed_at<=?
               ORDER BY computed_at,id LIMIT ?""",
            (start,now,MAX_ROWS+1)).fetchall()
    if len(events)>max_targets or len(candidates)>MAX_ROWS:
        raise ValueError("event/decision cap reached, narrow --days")
    by_item=defaultdict(list)
    for r in candidates:
        by_item[r["item_key"]].append(r)
    by_time={key:[int(r["computed_at"]) for r in rows]
             for key,rows in by_item.items()}

    summary=Counter()
    item_results=defaultdict(Counter)
    delay_results=defaultdict(Counter)
    live_candidates=set()
    attr=Counter()
    sample_examples=[]
    for original in events:
        issued=int(original["computed_at"])
        dep=int(original["departure"])
        if dep-issued<=EXECUTABLE_WINDOW:
            continue
        item=original["item_key"]
        counter=item_results[item]
        waiting=delay_results[wait_bucket(dep-issued)]
        for c in (summary,counter,waiting):
            c["future_watch_targets"]+=1
        if dep>now:
            for c in (summary,counter,waiting):
                c["not_yet_reached"]+=1
            continue
        matches=converted(original,by_item.get(item,()),
                          by_time.get(item,()))
        near=[m for m in matches if m[0]<=NEAR_WINDOW]
        for c in (summary,counter,waiting):
            c["reached"]+=1
            if matches:c["any_actionable_near_15m"]+=1
            if near:c["any_actionable_near_5m"]+=1
            if matches and not near:c["only_within_15m"]+=1
            if not matches:c["no_nearby_actionable"]+=1
        if matches:
            chosen=near[0] if near else matches[0]
            absdiff, neg_at, action_dep, action_issue, _=chosen
            diff=action_dep-dep
            kind=("exact" if diff==0 else "earlier" if diff<0 else "later")
            for c in (summary,counter,waiting):
                c["best_"+kind]+=1
            candidate_id=(item,action_issue,action_dep)
            live_candidates.add(candidate_id)
            attr[candidate_id]+=1
            if len(sample_examples)<6:
                sample_examples.append({
                    "item":item,
                    "original_departure_epoch":dep,
                    "original_issue_epoch":issued,
                    "actionable_issue_epoch":action_issue,
                    "actionable_departure_epoch":action_dep,
                    "difference_seconds":diff,
                })

    def materialize(c):
        n=c["reached"]
        return {
            "original_future_targets":c["future_watch_targets"],
            "reached":n,
            "unreached":c["not_yet_reached"],
            "converted_within_5m":c["any_actionable_near_5m"],
            "converted_within_15m":c["any_actionable_near_15m"],
            "only_within_15m":c["only_within_15m"],
            "not_converted_within_15m":c["no_nearby_actionable"],
            "best_exact":c["best_exact"],
            "best_earlier":c["best_earlier"],
            "best_later":c["best_later"],
            "conversion_5m_fraction":round(
                c["any_actionable_near_5m"]/n,4) if n else None,
            "conversion_15m_fraction":round(
                c["any_actionable_near_15m"]/n,4) if n else None,
        }
    result={
        "status":"V101_WATCH_TO_ACTIONABLE_WINDOW_DIAGNOSTIC",
        "read_only":True,"research_only":True,"stock_data_read":False,
        "sidecar_written":False,"live_system_modified":False,
        "player_flight_verified":False,
        "independent_opportunities_verified":False,
        "asof_epoch":now,"days":days,
        "raw_candidate_rows":raw,"invalid_or_abstained":invalid,
        "distinct_item_arrival_targets":len(events),
        "overall":materialize(summary),
        "by_item":{k:materialize(c) for k,c in sorted(item_results.items())},
        "by_original_wait":{k:materialize(c)
                            for k,c in sorted(delay_results.items())},
        "distinct_later_actionable_candidate_instances_selected":
            len(live_candidates),
        "max_original_watch_targets_linked_to_one_actionable_instance":
            max(attr.values(),default=0),
        "illustrative_instances":sample_examples,
        "caution":(
            "A near-by actionable candidate is a fresh five-minute research "
            "proposal, not proven stock success, not stable advance notice, "
            "and not evidence that a player actually traveled. One short-term "
            "proposal may serve many original watch targets. This can reveal "
            "moving departures that V100's last-at-original-time matching "
            "classified as changed or already passed."
        )
    }
    assert (result["overall"]["reached"]+result["overall"]["unreached"]
            ==result["overall"]["original_future_targets"])
    return result


def pretty(r):
    print("===== V101: LONG WATCH -> ACTUALLY ACTIONABLE NEARBY DEPARTURE =====")
    for key in ("raw_candidate_rows","distinct_item_arrival_targets",
                "distinct_later_actionable_candidate_instances_selected",
                "max_original_watch_targets_linked_to_one_actionable_instance"):
        print(f"{key}: {r[key]}")
    print("===== ALL HISTORICAL FUTURE WATCHES =====")
    print(json.dumps(r["overall"],sort_keys=True))
    print("===== ORIGINAL WAIT-TIME BREAKDOWN =====")
    for k,d in r["by_original_wait"].items():
        print(f'{k}: reached={d["reached"]} '
              f'within_5m={d["converted_within_5m"]} '
              f'within_15m={d["converted_within_15m"]} '
              f'earlier={d["best_earlier"]} later={d["best_later"]} '
              f'missed_15m={d["not_converted_within_15m"]}')
    print("===== PER ITEM =====")
    for k,d in r["by_item"].items():
        print(f'{k:30} reached={d["reached"]:4} '
              f'within_5m={d["converted_within_5m"]:4} '
              f'within_15m={d["converted_within_15m"]:4} '
              f'earlier={d["best_earlier"]:3} later={d["best_later"]:3} '
              f'no_near={d["not_converted_within_15m"]:4}')
    print("===== LIMITATION =====")
    print(r["caution"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=1)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    result=audit(days=a.days)
    if a.json:
        print(json.dumps(result,sort_keys=True))
    else:
        pretty(result)


if __name__=="__main__":
    main()
