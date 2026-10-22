"""V164 evidence-routed 24-item earliest-reachable-restock audit.

Research only.  This does NOT publish to the website, change production
routing, write the collector, or claim calibrated forecast probability.

Purpose:
1. Route each of the 24 beta items to an evidence-backed frozen plan family.
2. Score the routed plan at arrival (>=30 stock, +10s contract).
3. On issues observed while stock is <30, identify from later truth the
   earliest *actually reachable* clean restock window and determine whether
   the frozen plan landed in that first reachable window or skipped it.

The route table is intentionally conservative.  Short Oct-19/20 forward
evidence is not enough to replace a strong incumbent specialist by itself.
Monkey and Chamois retain their exact original specialists because the
separate original-online PC benchmark has 283 opportunities each
(Monkey 211/283, Chamois 208/283). Japan Xanax remains abstain-only.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from research.japan_xanax.renewal_shadow import source_data
from research.plushie_champions.common import TRAVEL_SECONDS

WAIT=28800
GRACE=10
MIN_QTY=30
SPECIAL="specialist_control"

# Research routing decision after the 2026-10-19/20 all24 frozen capture.
# "primary" is evaluated only; it is NOT authorized for production.
ROUTES={
    "arg:Ceibo Flower":       dict(primary="rate_current_quarter", challenger=SPECIAL, rationale="rate 5/6 vs specialist 1/1; specialist evidence too sparse"),
    "arg:Monkey Plushie":     dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="retain exact checkpoint4 specialist; PC original benchmark 211/283"),
    "can:Crocus":             dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="specialist 6/6 and rate 6/6"),
    "can:Wolverine Plushie":  dict(primary=SPECIAL, challenger="paired_recent_peak", rationale="specialist 8/8"),
    "can:Xanax":              dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="specialist/rate 6/7; leave-now 1/9"),
    "cay:Banana Orchid":      dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="specialist/rate 9/9"),
    "cay:Stingray Plushie":   dict(primary=SPECIAL, challenger="quantity_blocks_peak", rationale="specialist 9/9; quantity peak 6/6 lower coverage"),
    "chi:Panda Plushie":      dict(primary=SPECIAL, challenger="paired_recent_peak", rationale="challenger 3/3 but too sparse to displace specialist"),
    "chi:Peony":              dict(primary=SPECIAL, challenger="leave_now_control", rationale="specialist 4/4"),
    "haw:Orchid":             dict(primary=SPECIAL, challenger="leave_now_control", rationale="specialist 7/7"),
    "jap:Cherry Blossom":     dict(primary="rate_current_quarter", challenger=SPECIAL, rationale="rate 7/7 with more known outcomes than specialist 3/3"),
    "jap:Xanax":              dict(primary=None, challenger="rate_current_quarter", rationale="NOT READY: specialist excluded; best challenger only 1/6"),
    "mex:Dahlia":             dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="specialist 9/9"),
    "mex:Jaguar Plushie":     dict(primary=SPECIAL, challenger="quantity_blocks_peak", rationale="specialist 9/9"),
    "sou:African Violet":     dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="specialist 4/4; retain incumbent pending more evidence"),
    "sou:Lion Plushie":       dict(primary="rate_current_quarter", challenger=SPECIAL, rationale="rate 5/5; specialist 1/2"),
    "swi:Chamois Plushie":    dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="retain exact checkpoint4 specialist; PC original benchmark 208/283"),
    "swi:Edelweiss":          dict(primary="rate_current_quarter", challenger=SPECIAL, rationale="rate 6/6; leave-now 7/7"),
    "uae:Camel Plushie":      dict(primary="paired_recent_60", challenger=SPECIAL, rationale="paired60 4/4 vs specialist 3/5; research challenger only"),
    "uae:Tribulus Omanense":  dict(primary="rate_current_quarter", challenger=SPECIAL, rationale="rate 4/4"),
    "uni:Heather":            dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="specialist 7/7"),
    "uni:Nessie Plushie":     dict(primary=SPECIAL, challenger="paired_recent_60", rationale="specialist 6/7 vs leave-now 3/6"),
    "uni:Red Fox Plushie":    dict(primary="sequence_blocks_60", challenger=SPECIAL, rationale="sequence60 4/5 vs specialist 5/7; research challenger only"),
    "uni:Xanax":              dict(primary=SPECIAL, challenger="rate_current_quarter", rationale="specialist 7/7"),
}


def _ro(path):
    p=Path(path).expanduser().resolve(strict=True)
    db=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=12)
    db.execute("PRAGMA query_only=ON")
    return db


def _load_first_hourly(journal,model_sha):
    with closing(_ro(journal)) as db:
        meta=db.execute("SELECT value FROM metadata WHERE key='model_sha'").fetchone()
        if not meta or meta[0]!=model_sha:
            raise ValueError("journal model identity mismatch")
        raw=db.execute(
            "SELECT issued,item_key,mode,record FROM plans ORDER BY issued,item_key,mode LIMIT 100001"
        ).fetchall()
    if len(raw)>100000:
        raise ValueError("journal row cap exceeded")
    first={}
    modes=defaultdict(set)
    for issued,key,mode,encoded in raw:
        r=json.loads(encoded)
        if (r.get("issued"),r.get("item_key"),r.get("mode"),r.get("model_sha"))!=(issued,key,mode,model_sha):
            raise ValueError("record identity mismatch")
        first.setdefault((key,mode,issued//3600),r)
        modes[key].add(mode)
    if set(modes)!=set(ROUTES):
        raise ValueError("journal roster differs from V164 route table")
    for key,route in ROUTES.items():
        for field in ("primary","challenger"):
            mode=route[field]
            if mode is not None and mode not in modes[key]:
                raise ValueError(f"{key} missing routed mode {mode}")
    return first


def _truth_rows(source,key,cutoff):
    country,item=key.split(":",1)
    with closing(_ro(source)) as db:
        rows=db.execute(
            """SELECT timestamp,quantity,source FROM stock_history
               WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=?
               ORDER BY timestamp,id LIMIT 50001""",
            (country,item,cutoff),
        ).fetchall()
        gaps=db.execute(
            """SELECT start_timestamp,end_timestamp FROM collection_gaps
               WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT 15001""",
            (cutoff,),
        ).fetchall()
    if len(rows)>50000 or len(gaps)>15000:
        raise ValueError("truth evidence cap exceeded")
    return rows,gaps


def _crosses(gaps,a,b):
    for start,end in gaps:
        if start>b:
            break
        if start<=b and (end is None or end>=a):
            return True
    return False


def _clean_windows(rows,gaps,cutoff):
    """Return clean observed >=30 windows as (start,end,provider).

    A window with end=None is right-censored by truth_cutoff. Provider
    changes or collection gaps invalidate a threshold transition instead
    of inventing a restock/depletion.
    """
    windows=[]
    prev=None
    active=None
    for t,q,provider in rows:
        if t>cutoff:
            break
        high=q>=MIN_QTY
        if prev is not None:
            pt,pq,pp=prev
            broken=(provider!=pp or _crosses(gaps,pt,t))
            if broken:
                active=None
            elif pq<MIN_QTY<=q:
                active=[t,None,provider]
                windows.append(active)
            elif pq>=MIN_QTY>q and active is not None:
                active[1]=t
                active=None
        # If history begins high, this is a censored existing window, not a
        # confirmed restock; do not add it as a restock event.
        prev=(t,q,provider)
    return [tuple(x) for x in windows]


def _state_at(rows,issued):
    times=[r[0] for r in rows]
    i=bisect.bisect_right(times,issued)-1
    return rows[i] if i>=0 else None


def _earliest_reachable_window(rows,gaps,issued,flight,truth_cutoff):
    state=_state_at(rows,issued)
    if state is None or issued-state[0]>86400:
        return dict(status="UNKNOWN_ISSUE_STATE")
    if state[1]>=MIN_QTY:
        return dict(status="CURRENT_STOCK_ALREADY_GE30")
    for start,end,provider in _clean_windows(rows,gaps,truth_cutoff):
        if start<=issued:
            continue
        earliest_depart=max(issued,start-flight)
        arrival=earliest_depart+flight
        # Arrival must be >= restock.  A known depletion boundary must be
        # strictly after the scored arrival+grace. A censored window is only
        # mature if truth extends past arrival+grace.
        if arrival<start:
            continue
        if end is not None:
            if arrival+GRACE<end:
                return dict(status="EARLIEST_REACHABLE_FOUND",restock=start,depletion=end,
                            oracle_earliest_departure=earliest_depart,
                            oracle_earliest_arrival=arrival)
        elif truth_cutoff>=arrival+GRACE:
            return dict(status="EARLIEST_REACHABLE_FOUND",restock=start,depletion=None,
                        oracle_earliest_departure=earliest_depart,
                        oracle_earliest_arrival=arrival)
    return dict(status="NO_MATURE_REACHABLE_RESTOCK_IN_TRUTH")


def _score_route(source,key,records,truth_cutoff,evidence):
    route=ROUTES[key]
    primary=route["primary"]
    result=Counter()
    waits=[]
    event_lags=[]
    if primary is None:
        result["route_abstain_only"]+=len(records)
        return result,waits,event_lags
    rows,gaps=_truth_rows(source,key,truth_cutoff)
    flight=TRAVEL_SECONDS[key.split(":",1)[0]]
    for r in records:
        result["hourly_opportunities"]+=1
        dep=r.get("departure")
        arr=r.get("arrival")
        if dep is None or arr is None:
            result["abstain"]+=1
            continue
        result["proposals"]+=1
        waits.append((dep-r["issued"])/60)
        # Existing canonical poll-bracket arrival scorer. Evidence is loaded
        # once per item by score(), not once per proposal.
        arrival_state=evidence.score(arr)[0]
        result["arrival_"+arrival_state.lower()]+=1

        target=_earliest_reachable_window(rows,gaps,r["issued"],flight,truth_cutoff)
        status=target["status"]
        result["target_"+status.lower()]+=1
        if status!="EARLIEST_REACHABLE_FOUND":
            continue
        if truth_cutoff<arr+GRACE:
            result["earliest_pending"]+=1
            continue
        start,end=target["restock"],target["depletion"]
        if arr+GRACE<start:
            result["earliest_too_early"]+=1
        elif end is not None and arr+GRACE>=end:
            # Determine whether it actually landed in a later clean window.
            later=next((w for w in _clean_windows(rows,gaps,truth_cutoff)
                        if w[0]>start and w[0]<=arr+GRACE and
                        (w[1] is None or arr+GRACE<w[1])),None)
            result["earliest_skipped_to_later_window" if later else "earliest_too_late"]+=1
        else:
            result["earliest_reachable_hit"]+=1
            event_lags.append(arr-start)
            result["earliest_departure_delay_le_5m" if dep-target["oracle_earliest_departure"]<=300
                   else "earliest_departure_delay_gt_5m"]+=1
    return result,waits,event_lags


def score(*,source,journal,model_sha):
    first=_load_first_hourly(journal,model_sha)
    # Freeze one truth clock for every item exactly as the existing scorer does.
    truth_cutoff=None
    evidence_by_item={}
    for key in sorted(ROUTES):
        data=source_data(source,now=truth_cutoff,item_key=key)
        cutoff=data[4]
        truth_cutoff=cutoff if truth_cutoff is None else truth_cutoff
        if cutoff!=truth_cutoff:
            raise ValueError("truth cutoff mismatch")
        evidence_by_item[key]=data[3]

    items={}
    totals=Counter()
    for key in sorted(ROUTES):
        primary=ROUTES[key]["primary"]
        recs=[]
        if primary is not None:
            recs=[r for (k,m,h),r in sorted(first.items(),key=lambda x:(x[0][2],x[0][0],x[0][1]))
                  if k==key and m==primary]
        else:
            # Use union of observed hours from any mode for abstain-only Japan.
            hours=sorted({h for (k,m,h) in first if k==key})
            recs=[dict(issued=h*3600) for h in hours]
        c,waits,lags=_score_route(source,key,recs,truth_cutoff,evidence_by_item[key])
        totals.update(c)
        known=c["arrival_success"]+c["arrival_failure"]
        event_known=(c["earliest_reachable_hit"]+c["earliest_too_early"]+
                     c["earliest_too_late"]+c["earliest_skipped_to_later_window"])
        items[key]={
            **ROUTES[key],
            "counts":dict(c),
            "arrival_known":known,
            "arrival_success_fraction":c["arrival_success"]/known if known else None,
            "proposal_coverage":c["proposals"]/c["hourly_opportunities"] if c["hourly_opportunities"] else 0.0,
            "earliest_restock_scored":event_known,
            "earliest_restock_hit_fraction":c["earliest_reachable_hit"]/event_known if event_known else None,
            "mean_wait_minutes":sum(waits)/len(waits) if waits else None,
            "mean_arrival_after_target_restock_seconds":sum(lags)/len(lags) if lags else None,
        }
    known=totals["arrival_success"]+totals["arrival_failure"]
    event_known=(totals["earliest_reachable_hit"]+totals["earliest_too_early"]+
                 totals["earliest_too_late"]+totals["earliest_skipped_to_later_window"])
    return {
        "status":"V164_EVIDENCE_ROUTED_EARLIEST_RESTOCK_AUDIT",
        "model_sha":model_sha,
        "truth_cutoff":truth_cutoff,
        "items":items,
        "totals":dict(totals),
        "portfolio_arrival_success_fraction":totals["arrival_success"]/known if known else None,
        "portfolio_earliest_restock_hit_fraction":totals["earliest_reachable_hit"]/event_known if event_known else None,
        "actual_flights":False,
        "historical_truth_used_only_for_scoring":True,
        "automatic_promotion":False,
        "production_routing_modified":False,
        "website_modified":False,
        "japan_xanax_production_ready":False,
        "warning":"Small forward window. Earliest-reachable truth is an oracle scoring label, never an input to frozen recommendations.",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--journal",required=True)
    p.add_argument("--model-sha",required=True)
    p.add_argument("--compact",action="store_true")
    a=p.parse_args()
    result=score(source=a.source,journal=a.journal,model_sha=a.model_sha)
    if not a.compact:
        print(json.dumps(result,sort_keys=True,indent=2))
        return
    print("V164 evidence-routed earliest reachable restock audit")
    print("Item | route | arrival success/known | proposal coverage | earliest-restock hit/scored")
    for key,v in result["items"].items():
        c=v["counts"]
        print(f"{key} | {v['primary'] or 'ABSTAIN'} | "
              f"{c.get('arrival_success',0)}/{v['arrival_known']} | "
              f"{c.get('proposals',0)}/{c.get('hourly_opportunities',0)} | "
              f"{c.get('earliest_reachable_hit',0)}/{v['earliest_restock_scored']}")
    print(json.dumps({k:result[k] for k in (
        "portfolio_arrival_success_fraction","portfolio_earliest_restock_hit_fraction",
        "truth_cutoff","model_sha")},sort_keys=True))


if __name__=="__main__":
    main()
