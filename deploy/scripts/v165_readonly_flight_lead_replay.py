#!/usr/bin/env python3
"""V165 read-only, RESTOCK-CONDITIONED flight-lead freeze-time audit.

The issue clock is the last 5-minute model checkpoint BEFORE an actual
restock's hypothetical latest exact departure time. This selects each
evaluation checkpoint USING the hindsight outcome, solely for backtesting.
All model inputs are <= issue time; no future database observations are used.

Important: This scores TIMING RECALL conditioned on a clean observed
restock, NOT precision, genuine 5-minute live issuance, departure success,
or stock observed at landing. Those require independent prospective and
all-issued-decision denominators and heartbeat-gated arrival validation.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from deploy.scripts import v163_readonly_event_first_preview as model

SOURCE=model.COLLECTOR
FLIGHT_LEAD_STEP=model.STEP
MIN_LEAD_TOLERANCE=600
MAX_LEAD_TOLERANCE=1800
HIST_DAYS_CAP=14
POLICIES=(("all_history",None),("recent_8",8),
          ("recent_16",16),("recent_32",32))


def select_restock_for_arrival(forecast,*,reference_arrival,max_deviation=MAX_LEAD_TOLERANCE):
    """A causal decision: choose closest forecast to flight arrival CLOCK.

    The reference is computed only from ISSUE+published flight duration,
    NEVER from a future actual restock timestamp. This is an event target
    proxy and may not be a profitable flight. No event is selected if
    all forecast times are more than 30m from reference arrival.
    """
    if not isinstance(forecast,dict) or type(reference_arrival) is not int or type(max_deviation) is not int:
        raise ValueError("invalid arrival candidate")
    if not 60<=max_deviation<=3600:
        raise ValueError("invalid arrival match radius")
    items=forecast.get("restock_events") or []
    options=[r for r in items
             if type(r.get("predicted_restock_epoch")) is int and
             abs(r["predicted_restock_epoch"]-reference_arrival)<=max_deviation]
    if not options:
        return None
    return min(options,key=lambda r:(
        abs(r["predicted_restock_epoch"]-reference_arrival),
        r["predicted_restock_epoch"]
    ))


def _rate(n,total):
    return round(n/total,4) if total else None


def score_flight_lead(*,source=SOURCE,roster=None,asof=None,days=7,
                      limit_items=24,progress=None):
    """Replay one frozen causal issue per observed true restock (not every issue).

    The frozen issue=FLOOR((true restock - flight seconds - 10s)/300)*300.
    This uses actual event time to CHOOSE audit checkpoints, not features or
    the candidate event. It MUST NOT be interpreted as live decision success.
    """
    if type(days) is not int or not 1<=days<=HIST_DAYS_CAP:
        raise ValueError("invalid history interval")
    if type(limit_items) is not int or not 1<=limit_items<=24:
        raise ValueError("invalid item count")
    now=int(time.time()) if asof is None else asof
    if type(now) is not int or now<=0:
        raise ValueError("invalid as-of")
    start=now-days*86400
    roster=model.exact_roster() if roster is None else roster
    if not isinstance(roster,dict) or len(roster)!=24:
        raise ValueError("unexpected research roster")
    results={}
    with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+
                                 "?mode=ro",uri=True,timeout=12)) as con:
        con.execute("PRAGMA query_only=ON")
        gaps=con.execute(
            """SELECT start_timestamp,end_timestamp FROM collection_gaps
               WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?""",
            (now,model.MAX_GAPS+1)
        ).fetchall()
        if len(gaps)>model.MAX_GAPS:
            raise ValueError("too many collector gaps")
        for key in sorted(roster)[:limit_items]:
            country,name=key.split(":",1)
            raw=con.execute(
                """SELECT timestamp,quantity,source FROM stock_history
                   WHERE country=? AND lower(item_name)=lower(?)
                     AND timestamp<=?
                   ORDER BY timestamp ASC,id ASC LIMIT ?""",
                (country,name,now,model.MAX_ITEM_CHANGE_ROWS+1)
            ).fetchall()
            if len(raw)>model.MAX_ITEM_CHANGE_ROWS:
                raise ValueError("collector item has too many changes")
            obs=[model.OBS(int(t),int(q),str(provider)) for t,q,provider in raw
                 if t is not None and q is not None and provider
                 and int(q)>=0]
            crosses,events,_=model._replay_restock_index(obs,gaps,now)
            truths=events[bisect.bisect_right(events,start):]
            states={name:Counter() for name,_ in POLICIES}
            status={name:Counter() for name,_ in POLICIES}
            phases=model._ReplayPhases(crosses)
            cursor=0
            flight=model.TRAVEL_SECONDS[country]
            for event_epoch in truths:
                issued=(event_epoch-flight-model.GRACE)//FLIGHT_LEAD_STEP*FLIGHT_LEAD_STEP
                # The hypothetical *departure* issue must exist before event.
                if issued>=event_epoch:
                    raise AssertionError("future event used as issue")
                while cursor<len(obs) and obs[cursor].epoch<=issued:
                    phases.add(obs[cursor])
                    cursor+=1
                state=phases.asof() if cursor else None
                arrival=issued+flight+model.GRACE
                assert issued<=arrival<=event_epoch
                # This is the known arrival clock at *issuance*, not a
                # matching target selected by looking at the actual event.
                for policy,window in POLICIES:
                    stats=states[policy]
                    stats["observed_clean_restocks"]+=1
                    if state is None:
                        status[policy]["NO_OBSERVATIONS_ASOF"]+=1
                        continue
                    output=model.predict_events(
                        key,state,asof=issued,
                        horizon=model.MAX_HORIZON,recent_cycles=window)
                    status[policy][output["status"]]+=1
                    candidate=select_restock_for_arrival(
                        output,reference_arrival=arrival)
                    if candidate is None:
                        continue
                    stats["candidate_available"]+=1
                    diff=abs(candidate["predicted_restock_epoch"]-event_epoch)
                    stats["sum_absolute_error_seconds"]+=diff
                    stats["matches_15s"]+=diff<=15
                    stats["matches_60s"]+=diff<=60
                    stats["matches_10m"]+=diff<=600
                    first=candidate.get("expected_departure_epoch")
                    last=candidate.get("expected_latest_departure_epoch")
                    if (type(first) is int and type(last) is int and
                        first<=issued<=last):
                        stats["would_depart_at_issue"]+=1
            results[key]={
                "flight_seconds":flight,
                "truth_event_count":len(truths),
                "policies":{
                    k:{
                        "observed_clean_restocks":v["observed_clean_restocks"],
                        "candidate_coverage":_rate(v["candidate_available"],len(truths)),
                        "candidate_count":v["candidate_available"],
                        "recall_at_15s":_rate(v["matches_15s"],len(truths)),
                        "recall_at_60s":_rate(v["matches_60s"],len(truths)),
                        "recall_at_10m":_rate(v["matches_10m"],len(truths)),
                        "would_depart_at_issue_count":v["would_depart_at_issue"],
                        "mean_absolute_error_when_candidate_seconds":_rate(
                            v["sum_absolute_error_seconds"],v["candidate_available"]),
                        "forecast_statuses":dict(status[k])
                    } for k,v in states.items()
                }
            }
            if progress is not None:
                progress(key,len(results),limit_items)
    totals={}
    for policy,_ in POLICIES:
        v=Counter()
        for item in results.values():
            r=item["policies"][policy]
            n=r["observed_clean_restocks"]
            v["observed"]+=n
            v["candidate"]+=r["candidate_count"]
            # Reconstruct exact matches from displayed per-item rounded rates
            # is lossy; preserve internal counts below instead.
        totals[policy]={
            "observed_restocks":v["observed"],
            "candidate_count":v["candidate"],
            "candidate_coverage":_rate(v["candidate"],v["observed"]),
            "recall_15s":None,
            "recall_60s":None,
            "recall_10m":None,
        }
    return {
        "status":"V165_HISTORICAL_RESTOCK_CONDITIONED_FLIGHT_LEAD_REPLAY",
        "asof_epoch":now,"days":days,
        "issue_step_seconds":FLIGHT_LEAD_STEP,
        "items_evaluated":len(results),
        "items":results,"policies":totals,
        "future_truth_chooses_evaluation_issue_only":True,
        "candidate_selection_uses_true_restock_timestamp":False,
        "genuine_live_issuance":False,
        "departure_success_measured":False,
        "arrival_stock_success_measured":False,
        "event_precision_measured":False,
        "source_written":False,
        "ledger_written":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=SOURCE)
    parser.add_argument("--days",type=int,default=7)
    parser.add_argument("--limit-items",type=int,default=24)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    def progress(item,n,total):
        print(f"V165 flight-lead processed {n}/{total}: {item}",file=__import__("sys").stderr,flush=True)
    result=score_flight_lead(
        source=args.source,days=args.days,limit_items=args.limit_items,
        progress=progress)
    if args.json:
        print(json.dumps(result,sort_keys=True))
    else:
        for policy,x in result["policies"].items():
            print(policy,x)
        for item in ("jap:Xanax","uni:Nessie Plushie"):
            print(item,result["items"][item]["policies"])


if __name__=="__main__":
    main()
