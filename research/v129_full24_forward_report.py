"""V129: independent per-hour forward evidence for V128 full 24 roster.

Read only the actual previously-issued V128 sidecar and collector. Count a
first-issued snapshot per item UTC hour, so 12 adjacent five-minute replans
do not become 12 independent accuracy successes. Explicitly account for:
- 24 exact item keys, abstentions and late/budget skipped issuance;
- all starts as opposed to conditional successes only;
- future-watch reconfirmation in an AS-ISSUED tick near departure;
- no verified player flight, stock purchases or per-country feed freshness;
- pending / proxy unknown statuses, never silently converted to misses;
- matched immediate-departure counterfactual only when BOTH arrivals score.
Do not retrofit new predictions or fill missing ticks using future snapshots.
No writes to source, sidecar or public services.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.v60_private_snapshot_probe import approved_collector_source
from research.v88_poll_state_forward_report import observation
from research.v128_full24_earliest_shadow import (
    GENERATION,ROSTER,SIDECAR,COLLECTOR,MAX_ITEMS,exact_roster
)

MAX_DAYS=3
MAX_ROWS=40000
MIN_RECONFIRM_AGE=600
MAX_CLOCK_TOLERANCE=300


def ro(path):
    resolved=Path(path).resolve(strict=True)
    con=sqlite3.connect(resolved.as_uri()+"?mode=ro",
                        uri=True,timeout=15)
    con.execute("PRAGMA query_only=ON")
    return con


def _parse(source,roster):
    valid=[]
    failures=Counter()
    for item,issued,raw in source:
        if item not in roster:
            failures["UNKNOWN_ROSTER_ITEM"]+=1
            continue
        try:
            data=json.loads(raw)
            dep=data.get("earliest_departure")
            arr=data.get("earliest_arrival")
            country=item.split(":",1)[0]
            from research.plushie_champions.common import TRAVEL_SECONDS,MAX_WAIT
            if (data.get("item_key")!=item
                or data.get("policy_id")!=GENERATION
                or data.get("issued_epoch")!=issued
                or data.get("travel_seconds")!=TRAVEL_SECONDS[country]
                or data.get("min_stock_at_arrival")!=30
                or data.get("research_only") is not True
                or data.get("published_to_website") is not False
                or (dep is None)!=(arr is None)
                or (dep is not None and (
                    type(dep) is not int or type(arr) is not int
                    or not issued<=dep<=issued+MAX_WAIT
                    or arr!=dep+TRAVEL_SECONDS[country]))
                or (dep is None and data.get("departure_state")!="ABSTAIN")):
                raise ValueError("unverified model decision")
            valid.append(data)
        except (json.JSONDecodeError,ValueError,TypeError,KeyError):
            failures["INVALID_RECORDED_FORECAST"]+=1
    return valid,failures


def choose_hourly_starts(records):
    first={}
    for r in sorted(records,key=lambda x:(x["issued_epoch"],x["item_key"])):
        bucket=(r["item_key"],r["issued_epoch"]//3600)
        first.setdefault(bucket,r)
    return sorted(first.values(),key=lambda x:(x["item_key"],x["issued_epoch"]))


def reconfirm(original,issued_item_rows):
    dep=original.get("earliest_departure")
    issue=original["issued_epoch"]
    if dep is None:
        return "ABSTAIN_NOT_EXECUTABLE"
    if dep-issue<=300:
        return "RESEARCH_NOW_OR_FRESH_5M"
    # Track the most recently ISSUED research score BEFORE planned departure.
    last=[
        r for r in issued_item_rows
        if issue < r["issued_epoch"]<=dep
        and r["issued_epoch"]>=dep-MIN_RECONFIRM_AGE
    ]
    if not last:
        return "FUTURE_WATCH_NOT_RECONFIRMED"
    latest=last[-1]
    next_dep=latest.get("earliest_departure")
    if next_dep is None:
        return "RECONFIRMED_MODEL_ABSTAINED"
    if next_dep<latest["issued_epoch"] or next_dep>latest["issued_epoch"]+300:
        return "LATEST_REPLAN_STILL_WATCH"
    if abs(next_dep-dep)<=MAX_CLOCK_TOLERANCE:
        return "RECONFIRMED_FRESH_NEAR_DEPARTURE"
    return "LATEST_REPLAN_REJECTED_OR_SHIFTED"


def one_item_summary(items):
    c=Counter()
    waits=[]
    pairs=Counter()
    for x in items:
        c["first_issue_UTC_item_hours"]+=1
        dep=x["earliest_departure"]
        if dep is None:
            c["abstained_hours"]+=1
            continue
        c["proposed_departure_hours"]+=1
        waits.append((dep-x["issued_epoch"])/60)
        c["recheck_"+x["reconfirmation"]]+=1
        scored=x["model_hit"]
        base=x["now_hit"]
        if scored is True:c["model_proxy_success"]+=1
        elif scored is False:c["model_proxy_miss"]+=1
        else:
            c["model_proxy_unknown"]+=1
            c["model_unknown_"+x["model_evidence"]]+=1
        if x["model_evidence"]=="PENDING":
            c["model_pending"]+=1
        if base is True:c["now_proxy_success"]+=1
        elif base is False:c["now_proxy_miss"]+=1
        else:c["now_proxy_unknown"]+=1
        if scored is not None and base is not None:
            pairs["both_scorable"]+=1
            if scored and base:pairs["both_hit"]+=1
            elif scored:pairs["model_only_hit"]+=1
            elif base:pairs["now_only_hit"]+=1
            else:pairs["both_miss"]+=1
    n=c["first_issue_UTC_item_hours"]
    result={key:c[key] for key in (
        "first_issue_UTC_item_hours","abstained_hours",
        "proposed_departure_hours","model_proxy_success",
        "model_proxy_miss","model_proxy_unknown","model_pending",
        "now_proxy_success","now_proxy_miss","now_proxy_unknown",
    )}
    result["recheck_status_counts"]={
        key.removeprefix("recheck_"):n for key,n in sorted(c.items())
        if key.startswith("recheck_")
    }
    result["unknown_status_counts"]={
        key.removeprefix("model_unknown_"):n for key,n in sorted(c.items())
        if key.startswith("model_unknown_")
    }
    result["matched_pair"]={key:pairs[key] for key in (
        "both_scorable","both_hit","model_only_hit",
        "now_only_hit","both_miss"
    )}
    result["matched_known_net_win"]=(
        pairs["model_only_hit"]-pairs["now_only_hit"])
    result["mean_wait_minutes"]=(
        round(sum(waits)/len(waits),2) if waits else None)
    result["lower_bound_hits_per_start"]=(
        round(c["model_proxy_success"]/n,4) if n else None)
    result["no_country_provider_update_freshness_proof"]=True
    result["no_actual_gameplay_trips_proven"]=True
    return result


def audit(*,ledger=SIDECAR,stock=COLLECTOR,roster=ROSTER,
          days=1,now=None,max_rows=MAX_ROWS,
          scorer=observation):
    if (not 1<=days<=MAX_DAYS
        or not 1<=max_rows<=MAX_ROWS):
        raise ValueError("invalid bounded report")
    cohort=exact_roster(roster)
    asof=int(time.time() if now is None else now)
    if Path(ledger).resolve(strict=True)==Path(stock).resolve(strict=True):
        raise ValueError("private sidecar cannot equal collector")
    with closing(ro(ledger)) as sidecar:
        raw=sidecar.execute("""SELECT item_key,issued_epoch,payload_json
            FROM v128_issued
            WHERE issued_epoch>=? AND issued_epoch<=? AND policy_id=?
            ORDER BY issued_epoch,item_key LIMIT ?""",
            (asof-days*86400,asof,GENERATION,max_rows+1)).fetchall()
    if len(raw)>max_rows:
        raise ValueError("too many raw 5m decisions, lower report days")
    records,invalid=_parse(raw,cohort)
    starts=choose_hourly_starts(records)
    by_key=defaultdict(list)
    for r in records:by_key[r["item_key"]].append(r)
    for data in by_key.values():data.sort(key=lambda r:r["issued_epoch"])
    per_item={key:[] for key in cohort}
    with closing(ro(stock)) as collector:
        for r in starts:
            key=r["item_key"]
            country,item=key.split(":",1)
            baseline=r["baseline_leave_now_arrival"]
            dep=r["earliest_departure"]
            model_status="NO_DEPARTURE"
            model_hit=None
            if dep is not None:
                model_status,model_hit,_=scorer(
                    collector,country,item,r["earliest_arrival"],asof)
            now_status,now_hit,_=scorer(
                collector,country,item,baseline,asof)
            per_item[key].append({
                **r,
                "reconfirmation":reconfirm(r,by_key[key]),
                "model_evidence":model_status,
                "model_hit":model_hit,
                "now_evidence":now_status,
                "now_hit":now_hit,
            })
    by_item={key:one_item_summary(v) for key,v in sorted(per_item.items())}
    all_rows=[r for rows in per_item.values() for r in rows]
    return {
        "status":"V129_AS_ISSUED_24_ITEM_HOURLY_FORWARD_COMPARISON",
        "research_only":True,
        "read_only":True,
        "roster":len(cohort),
        "asof_epoch":asof,"days":days,
        "raw_five_minute_issue_rows":len(raw),
        "valid_as_issued_rows":len(records),
        "invalid_record_reasons":dict(invalid),
        "first_item_UTC_hourly_cohorts":len(starts),
        "overall":one_item_summary(all_rows),
        "per_item":by_item,
        "country_specific_provider_update_freshness_verified":False,
        "real_player_gameplay_success_verified":False,
        "overlapping_item_hours_are_independent_events":False,
        "future_wait_is_executable_without_reconfirmation":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days",type=int,default=1)
    parser.add_argument("--limit",type=int,default=MAX_ROWS)
    a=parser.parse_args()
    if not approved_collector_source(COLLECTOR):
        raise SystemExit("STOP: unapproved collector")
    print(json.dumps(audit(days=a.days,max_rows=a.limit),sort_keys=True))


if __name__=="__main__":
    main()
