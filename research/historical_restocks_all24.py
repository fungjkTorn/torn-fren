"""Bounded all-24 chronological physical-restock and departure historical replay.

Per-item as-issued forecasts are computed with observations <= each 5min tick.
The source is opened read-only, and the scorer sees future history ONLY after
the full forecast tape is frozen. Restock identity is chronological 0->positive,
while travel requires >=30 through landing +10s. All outputs are observational
proxies, NOT actual flights and NOT automatic model promotions.
"""
from __future__ import annotations

import argparse
import bisect
from collections import Counter
import json
import re
from pathlib import Path
import time

from research.departure_reconfirmation import evaluate_utc, compare_cohorts
from research.japan_xanax.renewal_shadow import source_data
from research.restock_event_clock import continuous_source
from research.true_zero_cycles import ZeroCycles, model
from research.physical_restock_identity import match
from services.travel_decision_contract_v166 import (
    STATUS_ACTIVE, STATUS_WAIT, build_item_travel_decision)

STEP=300
WAIT=28800
GRACE=10
MAX_DAYS=3
MODE="true_zero_all_expected_first_reachable_v1"
SOURCE_AGE=180
MATURITY=190


def _metric(values):
    return round(sum(values)/len(values),2) if values else None


def replay_item(source,key,*,days=1,asof=None):
    """One causally generated five-minute tape; score only after tape closes."""
    if type(days) is not int or not 1<=days<=MAX_DAYS:
        raise ValueError("bounded historical evaluation days required")
    if key not in model.exact_roster():
        raise ValueError("unexpected research roster item")
    raw,polls,gaps_crosses,evidence,cutoff=source_data(source,now=asof,item_key=key)
    observations=[model.OBS(*row) for row in raw]
    crosses=continuous_source(observations,gaps_crosses)
    tracker=ZeroCycles(crosses)
    flight=model.TRAVEL_SECONDS[key.split(":",1)[0]]
    end=((cutoff-flight-WAIT-MATURITY-STEP)//STEP)*STEP
    start=end-days*86400+STEP
    if not observations or start<observations[0].epoch:
        raise ValueError("insufficient warmup stock history for mature replay")
    plans=[];baseline=[];hourly=[];reason_counts=Counter()
    cursor=0
    for issued in range(start,end+WAIT+STEP,STEP):
        while cursor<len(observations) and observations[cursor].epoch<=issued:
            tracker.add(observations[cursor])
            cursor+=1
        pi=bisect.bisect_right(polls,issued)-1
        age=issued-polls[pi] if pi>=0 else None
        healthy=age is not None and 0<=age<=SOURCE_AGE and not crosses(issued,issued)
        forecast=tracker.forecast(key,asof=issued)
        decision=build_item_travel_decision(forecast,now=issued,
                          poll_age_seconds=age if age is not None and age>=0 else None)
        status=decision["status"]
        if issued<=end:reason_counts[status]+=1
        dep=(decision["estimated_departure_epoch"] if status in (STATUS_ACTIVE,STATUS_WAIT)
             and healthy else None)
        plans.append((issued, max(issued+15,dep) if dep is not None else None,age))
        baseline.append((issued,issued+15 if healthy else None,age))
        if issued<=end and issued%3600==0:
            first=decision["forecast_events"][0] if decision["forecast_events"] else None
            hourly.append(dict(issued=issued,healthy=healthy,
                model_status=forecast.get("status"),first_event=first,
                departure=dep,selected_index=decision.get("selected_restock_event_index"),
                initial_status=status))
    # From here onward the historical observations are truth, not input.
    def results(tape):
        cohorts=[]
        summary=evaluate_utc(tape,cutoff=cutoff,flight_seconds=flight,
                             score=evidence.score,start_before=end,cohorts=cohorts)
        return summary,cohorts
    planned,cohorts=results(plans)
    now_result,now_cohorts=results(baseline)
    paired=compare_cohorts(now_cohorts,cohorts)
    by_slice={}
    for label,pred in (
            ("earlier",lambda t:t<start+days*86400//2),
            ("later_untuned",lambda t:t>=start+days*86400//2)):
        a=[x for x in cohorts if pred(x["start"])]
        b=[x for x in now_cohorts if pred(x["start"])]
        c=Counter(x["outcome"] for x in a);sc=c["SUCCESS"]+c["FAILURE"]
        by_slice[label]=dict(starts=len(a),scored=sc,success=c["SUCCESS"],
            failure=c["FAILURE"],abstain=c["ABSTAIN"],unknown=c["UNKNOWN"],
            success_fraction=round(c["SUCCESS"]/sc,4) if sc else None,
            matched_vs_leave_now=compare_cohorts(b,a))
    # Strict ordinal restock physical event truth using the same existing
    # identity matcher as the forward ledger. No nearest-time relabeling.
    # Query only bounded poll/provider/gap metadata; per-item delta history
    # was loaded above with query_only set by source_data.
    import sqlite3
    from contextlib import closing
    uri=Path(source).resolve(strict=True).as_uri()+"?mode=ro"
    with closing(sqlite3.connect(uri,uri=True,timeout=12)) as db:
        db.execute("PRAGMA query_only=ON")
        t0=min(r["issued"] for r in hourly) if hourly else start
        # Older collectors and synthetic fixtures may lack poll-level
        # provider metadata. Such episodes are UNKNOWN for physical-event
        # identity, not scored as if the provider continuity were proven.
        columns={r[1] for r in db.execute("PRAGMA table_info(poll_heartbeats)")}
        provider_sql="source" if "source" in columns else "NULL AS source"
        polldata=db.execute(f"""SELECT timestamp,{provider_sql} FROM poll_heartbeats
            WHERE mode='poll-cycle' AND success=1 AND timestamp>=?
              AND timestamp<=? ORDER BY timestamp,id LIMIT 400001""",
            (t0-180,cutoff)).fetchall()
        gapdata=db.execute("""SELECT start_timestamp,end_timestamp FROM collection_gaps
            WHERE start_timestamp<=? AND COALESCE(end_timestamp,9223372036854775807)>=?""",
            (cutoff,t0)).fetchall()
    if len(polldata)>400000:
        raise ValueError("poll evidence exceeds bounded source limit")
    timings=Counter();minerr=[];maxerr=[];distinct=set();all_issues=[]
    for issue in hourly:
        if not issue["healthy"] or issue["first_event"] is None:
            timings["abstained_or_unhealthy"]+=1
            continue
        when=issue["first_event"]["predicted_restock_epoch"]
        truth=match(raw,[t for t,s in polldata],gapdata,
                    issued=issue["issued"],ordinal=1,cutoff=cutoff,estimate=when)
        if truth["status"]=="RESOLVED":
            end_event=truth["restock_by_epoch"]
            # Reject provider changes within the issue->event span.
            sources={source for t,source in polldata
                     if issue["issued"]-180<=t<=end_event}
            state=next((r[2] for r in reversed(raw) if r[0]<=issue["issued"]),None)
            if len(sources)!=1 or state not in sources or None in sources:
                truth=dict(status="UNKNOWN",reason="POLL_PROVIDER_DISCONTINUITY")
        timings[truth["status"].lower()]+=1
        if truth["status"]!="RESOLVED":
            continue
        distinct.add(truth["restock_by_epoch"])
        mn=truth["minimum_absolute_error_seconds"]
        mx=truth["maximum_absolute_error_seconds"]
        minerr.append(mn);maxerr.append(mx)
        for seconds in (15,60,300,600):
            timings["possible_within_"+str(seconds)+"s"]+=mn<=seconds
            timings["certain_within_"+str(seconds)+"s"]+=mx<=seconds
        all_issues.append((issue["issued"],mn,mx,truth["restock_by_epoch"]))
    train=[r for r in all_issues if r[0]<start+days*86400//2]
    later=[r for r in all_issues if r[0]>=start+days*86400//2]
    def restock_slice(records):
        return dict(hourly_known=len(records),distinct_physical_restocks=len(
            {r[3] for r in records}),mean_min_error_min=_metric([r[1]/60 for r in records]),
            mean_max_error_min=_metric([r[2]/60 for r in records]),
            certainly_within_10m=sum(r[2]<=600 for r in records))
    return dict(item_key=key,days=days,source_cutoff=cutoff,first_issue=start,
        last_first_issue=end,model=MODE,physical_zero_anchor=True,threshold=30,
        arrival_plus_10_seconds=True,issued_every_seconds=STEP,
        issue_reconfirmation=True,physical=dict(timings,
            first_hourly_issues=len(hourly),scored=len(all_issues),
            distinct_physical_restocks=len(distinct),
            mean_min_error_minutes=_metric([v/60 for v in minerr]),
            mean_max_error_minutes=_metric([v/60 for v in maxerr]),
            earlier=restock_slice(train),later_untuned=restock_slice(later)),
        departure=planned,leave_now=now_result,matched_vs_now=paired,
        chronological_slices=by_slice,issue_statuses=dict(reason_counts),
        no_future_training=True,actual_player_flights=False,
        provider_certified=False,auto_promoted=False,
        warning="Historical observed change/poll stock proxy, not true event seconds; "
            "UTC-hour cohorts are correlated. Later slice was not used to select the policy.")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--model-sha",required=True)
    p.add_argument("--days",type=int,default=1)
    p.add_argument("--asof",type=int)
    p.add_argument("--item-key",action="append")
    args=p.parse_args()
    if type(args.days) is not int or not 1<=args.days<=MAX_DAYS:
        raise ValueError("historical days must be 1..3")
    if re.fullmatch(r"[0-9a-f]{40}",args.model_sha) is None:
        raise ValueError("must pin immutable model source")
    keys=sorted(args.item_key or model.exact_roster())
    if len(set(keys))!=len(keys) or not set(keys)<=set(model.exact_roster()):
        raise ValueError("unrecognized or duplicate roster")
    output=Path(args.output)
    if output.suffix!=".json" or output.is_symlink() or output.resolve()==Path(args.source).resolve():
        raise ValueError("output must be separate research JSON")
    if not output.parent.is_dir():
        raise ValueError("existing output directory required")
    reports={};failed={};began=time.monotonic()
    for key in keys:
        started=time.monotonic()
        try:
            reports[key]=replay_item(args.source,key,days=args.days,asof=args.asof)
            # Every completed item survives a bounded runner timeout. The
            # partial output NEVER claims a full-roster result or promotion.
            checkpoint=output.with_name(output.stem+".partial.json")
            checkpoint.write_text(json.dumps(dict(kind="HISTORICAL_PARTIAL",
                model_sha=args.model_sha,days=args.days,requested_items=keys,
                completed_items=len(reports),items=reports,
                roster_complete=False,production_modified=False),
                sort_keys=True)+"\n")
            print("HISTORICAL_ITEM",key,round(time.monotonic()-started,2),
                  reports[key]["departure"]["scored"],flush=True)
        except (ValueError,RuntimeError,sqlite3.DatabaseError) as exc:
            failed[key]=type(exc).__name__+":"+str(exc)[:180]
            print("HISTORICAL_ITEM_INCOMPLETE",key,failed[key],flush=True)
    result=dict(kind="TRUE_ZERO_FIRST_REACHABLE_ALL24_HISTORICAL",
                run_status="COMPLETE" if not failed and len(reports)==len(keys)
                    else "PARTIAL_NO_PROMOTION",
                model_sha=args.model_sha,days=args.days,requested_items=keys,
                completed_items=len(reports),failed_items=failed,
                seconds=round(time.monotonic()-began,2),items=reports,
                baseline="leave_now_same_issued_hours",
                production_modified=False,raw_stock_data_published=False,
                exact_game_stock_certified=False,automatic_model_promotion=False)
    output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("HISTORICAL_SUMMARY",json.dumps(dict(status=result["run_status"],
        completed_items=result["completed_items"],failures=len(failed),
        output=str(output)),sort_keys=True),flush=True)


if __name__=="__main__":
    main()
