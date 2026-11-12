"""V89 read-only audit of why V75 24-hour forward reports contain pending targets.

Reads ONLY the V75 private candidate sidecar in mode=ro. Does not evaluate
stock outcomes, change live policy, change timers, or treat distinct arrival
timestamps as independent restock opportunities.

At a fixed asof, V76 labels an issued candidate PENDING until its predicted
arrival +10s grace +180s observational buffer. V89 explains that pool by:
  * departure not reached (still waiting),
  * departed hypothetically, arrival in the future,
  * arrival past but buffer not finished;
plus wait-to-depart distribution and revisions of sequential recommendations.

The eight-hour horizon is a historical *permission*, not proof of utility.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from contextlib import closing

from research.v76_forward_research_report import V75, MAX_CANDIDATE_ROWS, eligible, ro

GRACE=10
OBSERVATION_BUFFER=180
MAX_DAYS=7
# Wait bins are at issue time, not relative to today's clock.
WAIT_BINS=((300,"0–5m"),(900,"5–15m"),(1800,"15–30m"),
           (3600,"30–60m"),(7200,"1–2h"),(14400,"2–4h"),
           (21600,"4–6h"),(28800,"6–8h"))
# A run of nearby arrival targets can be multiple versions of the same
# forecast. This heuristic is never interpreted as real restock independence.
NEARBY_SECONDS=900


def wait_bucket(wait_s):
    if wait_s<0:
        return "INVALID_NEGATIVE"
    for upper,label in WAIT_BINS:
        if wait_s<=upper:
            return label
    return "OVER_8H"


def stage(row, asof):
    dep=int(row["departure"])
    arr=int(row["arrival"])
    if dep>asof:
        return "WAITING_FOR_DEPARTURE"
    if arr>asof:
        return "HYPOTHETICALLY_IN_FLIGHT"
    if arr+GRACE+OBSERVATION_BUFFER>asof:
        return "AWAITING_POST_ARRIVAL_BUFFER"
    return "MATURED_FOR_OUTCOME_AUDIT"


def count_nearby_target_groups(events, gap=NEARBY_SECONDS):
    """Heuristic concentration diagnostic, NOT independent restock counts."""
    series=defaultdict(list)
    for row in events:
        series[row["item_key"]].append(int(row["arrival"]))
    groups=Counter()
    for key, times in series.items():
        last=None
        for ts in sorted(set(times)):
            if last is None or ts-last>gap:
                groups[key]+=1
            last=ts
    return dict(sorted(groups.items()))


def analyze(*, sidecar=V75, now=None, days=1, row_limit=MAX_CANDIDATE_ROWS):
    if not 1<=days<=MAX_DAYS or not 1<=row_limit<=MAX_CANDIDATE_ROWS:
        raise ValueError("days or row limit outside read-only safety bounds")
    asof=int(time.time() if now is None else now)
    start=asof-days*86400
    with closing(ro(sidecar)) as con:
        raw_rows=con.execute(
            """SELECT item_key,computed_at,stock_as_of,status,valid_until,
                      departure,arrival,actual_player_departure
               FROM v42_candidate_decisions
               WHERE computed_at>=? AND computed_at<=?
               ORDER BY computed_at ASC,id ASC LIMIT ?""",
            (start,asof,row_limit+1)).fetchall()
        if len(raw_rows)>row_limit:
            raise ValueError("too many rows; lower --days")
    all_valid=[r for r in raw_rows if eligible(r)]
    unique={}
    for row in all_valid:
        key=(row["item_key"],row["arrival"])
        if key not in unique:
            unique[key]=row
    targets=list(unique.values())

    stages=Counter()
    pending_wait_bins=Counter()
    all_wait_bins=Counter()
    per_item=defaultdict(Counter)
    delayed_over_hour=Counter()
    delays=[]
    for row in targets:
        key=row["item_key"]
        st=stage(row,asof)
        wait=int(row["departure"])-int(row["computed_at"])
        stages[st]+=1
        per_item[key]["targets"]+=1
        per_item[key][st]+=1
        bucket=wait_bucket(wait)
        all_wait_bins[bucket]+=1
        per_item[key]["wait_"+bucket]+=1
        delays.append(wait)
        if st!="MATURED_FOR_OUTCOME_AUDIT":
            pending_wait_bins[bucket]+=1
        if wait>3600:
            delayed_over_hour[key]+=1

    # Consecutive as-issued decisions: distinguish repeated issue vs real
    # target revisions. A new decision more than 15m after the previous
    # one starts a new sequence; abstentions break the sequence.
    latest_by_item={}
    changed=Counter()
    revision_by_item=defaultdict(Counter)
    for row in raw_rows:
        key=row["item_key"]
        at=int(row["computed_at"])
        prev=latest_by_item.get(key)
        valid=eligible(row)
        if prev is not None:
            p_at,p_valid,p_dep,p_arr=prev
            if at-p_at <=900 and at>p_at:
                if valid and p_valid:
                    change=int(row["departure"])-int(p_dep)
                    counter="SAME_DEPARTURE" if change==0 else (
                        "MOVED_EARLIER_15M_PLUS" if change<=-900 else
                        "MOVED_LATER_15M_PLUS" if change>=900 else
                        "SMALL_DEPARTURE_REVISION")
                    changed[counter]+=1
                    revision_by_item[key][counter]+=1
                elif p_valid and not valid:
                    changed["RECOMMENDATION_WITHDRAWN"]+=1
                    revision_by_item[key]["RECOMMENDATION_WITHDRAWN"]+=1
                elif not p_valid and valid:
                    changed["RECOMMENDATION_REAPPEARED"]+=1
                    revision_by_item[key]["RECOMMENDATION_REAPPEARED"]+=1
            # else: no continuity assumption across gaps.
        latest_by_item[key]=(at,valid,row["departure"],row["arrival"])

    def histogram_stats(xs):
        if not xs:return {"count":0}
        values=sorted(xs)
        def nearest(p):
            return values[min(len(values)-1,max(0,int((len(values)-1)*p)))]
        return {"count":len(values),
                "median_wait_minutes":round(nearest(.5)/60,1),
                "p75_wait_minutes":round(nearest(.75)/60,1),
                "p90_wait_minutes":round(nearest(.9)/60,1)}

    pending=sum(v for k,v in stages.items() if k!="MATURED_FOR_OUTCOME_AUDIT")
    grouped=count_nearby_target_groups(targets)
    return {
        "status":"V89_V75_PENDING_HORIZON_DIAGNOSTIC",
        "read_only":True,"website_or_live_policy_changed":False,
        "real_flights_observed":False,"actual_restock_independence_certified":False,
        "asof_epoch":asof,"issued_window_days":days,
        "raw_rows":len(raw_rows),"raw_valid_candidate_rows":len(all_valid),
        "invalid_or_abstained_rows":len(raw_rows)-len(all_valid),
        "exact_item_and_arrival_duplicate_rows":len(all_valid)-len(targets),
        "unique_item_arrival_targets":len(targets),
        "pending_equivalent_to_v76":pending,
        "matured_equivalent_to_v76":stages["MATURED_FOR_OUTCOME_AUDIT"],
        "stage_counts":dict(sorted(stages.items())),
        "wait_to_depart_all_targets":dict(sorted(all_wait_bins.items())),
        "wait_to_depart_pending_only":dict(sorted(pending_wait_bins.items())),
        "wait_to_depart_summary":histogram_stats(delays),
        "targets_with_wait_over_1_hour_per_item":dict(sorted(delayed_over_hour.items())),
        "forecast_revision_pair_counts":dict(sorted(changed.items())),
        "forecast_revision_counts_by_item":{
            k:dict(sorted(v.items())) for k,v in sorted(revision_by_item.items())},
        "per_item":{k:dict(sorted(v.items())) for k,v in sorted(per_item.items())},
        "nearby_15min_target_groups_heuristic_total":sum(grouped.values()),
        "nearby_15min_target_groups_by_item":grouped,
        "note":(
            "Pending is expected for long-departure and long-flight horizon "
            "forecasts and says nothing about their eventual success. "
            "A 15m neighboring-target grouping is only a diagnostic; "
            "it must not be treated as independent verified restocks. "
            "Revisions are measured from consecutive logged candidates, "
            "not a claim that every candidate was shown to a player."
        ),
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=1)
    p.add_argument("--row-limit",type=int,default=MAX_CANDIDATE_ROWS)
    p.add_argument("--table",action="store_true",
                   help="compact readable result, avoids massive JSON dump")
    args=p.parse_args()
    out=analyze(days=args.days,row_limit=args.row_limit)
    if not args.table:
        print(json.dumps(out,sort_keys=True))
        return
    print("===== V89 LAST %d DAY(S): ISSUE-TIME HORIZON / PENDING AUDIT =====" %
          args.days)
    for k in ("raw_rows","raw_valid_candidate_rows",
              "invalid_or_abstained_rows","exact_item_and_arrival_duplicate_rows",
              "unique_item_arrival_targets","pending_equivalent_to_v76",
              "matured_equivalent_to_v76"):
        print(f"{k}: {out[k]}")
    print("===== WHAT PENDING REALLY MEANS =====")
    for k,v in sorted(out["stage_counts"].items()):
        print(f"{k}: {v}")
    print("===== ORIGINAL ISSUE -> DEPARTURE WAIT DISTRIBUTION =====")
    for k,v in out["wait_to_depart_all_targets"].items():
        print(f"{k}: {v}")
    print("Summary:",json.dumps(out["wait_to_depart_summary"],sort_keys=True))
    print("===== FORECAST CHANGES ON CONSECUTIVE ISSUES =====")
    for k,v in out["forecast_revision_pair_counts"].items():
        print(f"{k}: {v}")
    print("===== PER-ITEM BREAKDOWN =====")
    print(f'{"ITEM":30} {"TARGETS":>7} {"WAITING":>7} {"FLIGHT":>7} '
          f'{"BUFFER":>7} {"MATURE":>7} {">1H WAIT":>8}')
    for key,rec in sorted(out["per_item"].items()):
        print(f'{key:30} {rec["targets"]:7} '
              f'{rec.get("WAITING_FOR_DEPARTURE",0):7} '
              f'{rec.get("HYPOTHETICALLY_IN_FLIGHT",0):7} '
              f'{rec.get("AWAITING_POST_ARRIVAL_BUFFER",0):7} '
              f'{rec.get("MATURED_FOR_OUTCOME_AUDIT",0):7} '
              f'{out["targets_with_wait_over_1_hour_per_item"].get(key,0):8}')
    print("===== NOT INDEPENDENT RESTOCKS =====")
    print("15m-nearby target groups (heuristic only):",
          out["nearby_15min_target_groups_heuristic_total"])
    print("No stock was scored. No live services or data changed.")


if __name__=="__main__":
    main()
