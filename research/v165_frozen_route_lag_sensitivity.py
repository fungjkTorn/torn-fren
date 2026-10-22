"""V165 frozen-plan landing-buffer sensitivity for routed/specialist forecasts.

Research only.  Reuses the genuinely recorded all24 frozen plans; it does not
reconstruct recommendations with future truth.  For each recorded hourly
proposal, delay departure+arrival by an explicit safety buffer and score:
  * stock >=30 at shifted arrival (+10s contract)
  * whether shifted arrival still lands in the earliest actually reachable
    clean restock window determined only as a scoring label.

This directly tests whether the 30-day generic-clock lag finding transfers to
the actual routed/specialist forecasts.  It never changes production routing.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from statistics import mean

from research.japan_xanax.renewal_shadow import source_data
from research.v164_evidence_routed_earliest_restock import (
    ROUTES, SPECIAL, WAIT, GRACE,
    _load_first_hourly, _truth_rows, _earliest_reachable_window,
    _clean_windows,
)
from research.plushie_champions.common import TRAVEL_SECONDS

LAGS=(0,60,180,300,600)


def _modes_for(key):
    route=ROUTES[key]
    modes=[]
    for mode in (route.get("primary"),route.get("challenger"),SPECIAL):
        if mode is not None and mode not in modes:
            modes.append(mode)
    return tuple(modes)


def _score_shifted(*,record,lag,evidence,rows,gaps,flight,truth_cutoff):
    c=Counter()
    dep=record.get("departure")
    arr=record.get("arrival")
    c["opportunities"]=1
    if dep is None or arr is None:
        c["abstain"]=1
        return c,None,None
    shifted_dep=dep+lag
    shifted_arr=arr+lag
    if shifted_dep>record["issued"]+WAIT:
        c["outside_horizon"]=1
        return c,None,None
    c["proposals"]=1
    state=evidence.score(shifted_arr)[0]
    c["arrival_"+state.lower()]=1

    target=_earliest_reachable_window(rows,gaps,record["issued"],flight,truth_cutoff)
    status=target["status"]
    c["target_"+status.lower()]=1
    if status!="EARLIEST_REACHABLE_FOUND":
        return c,shifted_dep-record["issued"],None
    if truth_cutoff<shifted_arr+GRACE:
        c["earliest_pending"]=1
        return c,shifted_dep-record["issued"],None

    start,end=target["restock"],target["depletion"]
    scored=shifted_arr+GRACE
    if scored<start:
        c["earliest_too_early"]=1
    elif end is not None and scored>=end:
        later=next((w for w in _clean_windows(rows,gaps,truth_cutoff)
                    if w[0]>start and w[0]<=scored and
                    (w[1] is None or scored<w[1])),None)
        c["earliest_skipped_to_later_window" if later else "earliest_too_late"]=1
    else:
        c["earliest_reachable_hit"]=1
        c["earliest_departure_delay_le_5m" if shifted_dep-target["oracle_earliest_departure"]<=300
          else "earliest_departure_delay_gt_5m"]=1
    return c,shifted_dep-record["issued"],shifted_arr-start


def score(*,source,journal,model_sha,lags=LAGS):
    if (not isinstance(lags,tuple) or not lags or len(set(lags))!=len(lags)
        or 0 not in lags or any(type(x) is not int or not 0<=x<=900 for x in lags)):
        raise ValueError("lags must be unique integer seconds 0..900 and include 0")

    first=_load_first_hourly(journal,model_sha)
    truth_cutoff=None
    evidence_by_item={}
    truth_by_item={}
    for key in sorted(ROUTES):
        data=source_data(source,now=truth_cutoff,item_key=key)
        cutoff=data[4]
        truth_cutoff=cutoff if truth_cutoff is None else truth_cutoff
        if cutoff!=truth_cutoff:
            raise ValueError("truth cutoff mismatch")
        evidence_by_item[key]=data[3]
        truth_by_item[key]=_truth_rows(source,key,truth_cutoff)

    rows_out=[]
    for key in sorted(ROUTES):
        flight=TRAVEL_SECONDS[key.split(":",1)[0]]
        rows,gaps=truth_by_item[key]
        for mode in _modes_for(key):
            records=[r for (k,m,h),r in sorted(first.items(),key=lambda x:x[0][2])
                     if k==key and m==mode]
            if not records:
                continue
            for lag in lags:
                counts=Counter();waits=[];event_lags=[]
                for record in records:
                    c,wait,event_lag=_score_shifted(
                        record=record,lag=lag,evidence=evidence_by_item[key],
                        rows=rows,gaps=gaps,flight=flight,truth_cutoff=truth_cutoff)
                    counts.update(c)
                    if wait is not None: waits.append(wait/60)
                    if event_lag is not None: event_lags.append(event_lag)
                known=counts["arrival_success"]+counts["arrival_failure"]
                event_known=(counts["earliest_reachable_hit"]+
                             counts["earliest_too_early"]+
                             counts["earliest_too_late"]+
                             counts["earliest_skipped_to_later_window"])
                rows_out.append({
                    "item_key":key,
                    "mode":mode,
                    "is_primary":mode==ROUTES[key].get("primary"),
                    "is_challenger":mode==ROUTES[key].get("challenger"),
                    "lag_seconds":lag,
                    "counts":dict(counts),
                    "arrival_known":known,
                    "arrival_success_fraction":counts["arrival_success"]/known if known else None,
                    "proposal_coverage":counts["proposals"]/counts["opportunities"] if counts["opportunities"] else 0.0,
                    "earliest_restock_scored":event_known,
                    "earliest_restock_hit_fraction":counts["earliest_reachable_hit"]/event_known if event_known else None,
                    "mean_wait_minutes":mean(waits) if waits else None,
                    "mean_arrival_after_target_restock_seconds":mean(event_lags) if event_lags else None,
                })

    # Primary-route portfolio by lag.
    portfolio={}
    for lag in lags:
        selected=[r for r in rows_out if r["lag_seconds"]==lag and r["is_primary"]]
        total=Counter()
        for row in selected: total.update(row["counts"])
        known=total["arrival_success"]+total["arrival_failure"]
        event_known=(total["earliest_reachable_hit"]+total["earliest_too_early"]+
                     total["earliest_too_late"]+total["earliest_skipped_to_later_window"])
        portfolio[str(lag)]={
            "arrival_success_fraction":total["arrival_success"]/known if known else None,
            "arrival_known":known,
            "proposals":total["proposals"],
            "opportunities":total["opportunities"],
            "proposal_coverage":total["proposals"]/total["opportunities"] if total["opportunities"] else 0.0,
            "earliest_restock_hit_fraction":total["earliest_reachable_hit"]/event_known if event_known else None,
            "earliest_restock_scored":event_known,
            "counts":dict(total),
        }

    return {
        "status":"V165_FROZEN_ROUTE_LAG_SENSITIVITY",
        "model_sha":model_sha,
        "truth_cutoff":truth_cutoff,
        "lags_seconds":list(lags),
        "rows":rows_out,
        "primary_portfolio":portfolio,
        "actual_flights":False,
        "production_modified":False,
        "website_modified":False,
        "recommendation":"Use only as lag-sensitivity evidence; small forward window does not authorize promotion.",
    }


def _pct(x):
    return "---" if x is None else f"{100*x:.1f}%"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--journal",required=True)
    p.add_argument("--model-sha",required=True)
    p.add_argument("--lag",type=int,action="append")
    p.add_argument("--compact",action="store_true")
    a=p.parse_args()
    lags=tuple(a.lag) if a.lag else LAGS
    result=score(source=a.source,journal=a.journal,model_sha=a.model_sha,lags=lags)
    if not a.compact:
        print(json.dumps(result,sort_keys=True,indent=2))
        return
    print("V165 FROZEN ROUTE LAG SENSITIVITY")
    print("Primary portfolio:")
    for lag in lags:
        r=result["primary_portfolio"][str(lag)]
        print(f"  +{lag:>3}s | arrival {_pct(r['arrival_success_fraction'])} "
              f"({r['arrival_known']} known) | coverage {r['proposals']}/{r['opportunities']} | "
              f"earliest {_pct(r['earliest_restock_hit_fraction'])} "
              f"({r['earliest_restock_scored']} scored)")
    print("\nPer-item primary route:")
    print("item | mode | lag | arrival S/known | earliest hit/scored | coverage")
    for row in result["rows"]:
        if not row["is_primary"]: continue
        c=row["counts"]
        print(f"{row['item_key']} | {row['mode']} | +{row['lag_seconds']} | "
              f"{c.get('arrival_success',0)}/{row['arrival_known']} | "
              f"{c.get('earliest_reachable_hit',0)}/{row['earliest_restock_scored']} | "
              f"{c.get('proposals',0)}/{c.get('opportunities',0)}")


if __name__=="__main__":
    main()
