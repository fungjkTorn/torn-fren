"""V99 READ ONLY: stock already available at issuance versus later opportunity.

For first-as-issued V75 item/arrival targets, inspect only stock-history rows
at or before the original stock_as_of time, not present/future data. Compare
that item state to reconstructed post-arrival proxy outcome and immediate
departure baseline. Research only. Never alters collector, VM, or website.

The existing collector does not preserve upstream per-country update epochs:
no result is certified exact in-game arrival availability or independent restock.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.v76_forward_research_report import V75,SOURCE,ro,select_unique
from research.v88_poll_state_forward_report import observation,MAX_STATE_AGE_SECONDS
from research.plushie_champions.common import TRAVEL_SECONDS
from research.v60_private_snapshot_probe import approved_collector_source

THRESHOLD=30
MAX_AGE=180
MAX_DAYS=3
MAX_TARGETS=12000


def issue_stock(conn,country,item,issued,stock_as_of):
    """Historical as-issued stock state, with no observation after issuance."""
    if (type(issued) is not int or type(stock_as_of) is not int or
        not 0<=issued-stock_as_of<=MAX_AGE):
        return "INVALID_ISSUED_WATERMARK",None
    hb=conn.execute(
        """SELECT timestamp,source FROM poll_heartbeats
           WHERE success=1 AND mode='poll-cycle' AND timestamp<=?
           ORDER BY timestamp DESC,id DESC LIMIT 1""",
        (stock_as_of,)).fetchone()
    if hb is None or stock_as_of-int(hb[0])>MAX_AGE:
        return "NO_FRESH_ISSUE_HEARTBEAT",None
    row=conn.execute(
        """SELECT timestamp,quantity,source FROM stock_history
           WHERE country=? AND item_name=? AND timestamp<=?
           ORDER BY timestamp DESC,id DESC LIMIT 1""",
        (country,item,int(hb[0]))).fetchone()
    if row is None:
        return "NO_ISSUE_STOCK_RECORD",None
    if int(hb[0])-int(row[0])>MAX_STATE_AGE_SECONDS:
        return "ISSUE_ITEM_STATE_TOO_OLD",None
    if row[2]!=hb[1]:
        return "ISSUE_PROVIDER_MISMATCH",None
    # Known gaps immediately preceding issue undermine the state claim.
    gap=conn.execute(
        """SELECT 1 FROM collection_gaps WHERE start_timestamp<=?
           AND COALESCE(end_timestamp,9223372036854775807)>=?
           LIMIT 1""",(int(hb[0]),max(int(row[0]),int(hb[0])-180))
    ).fetchone()
    if gap:
        return "ISSUE_COLLECTION_GAP",None
    quantity=int(row[1])
    return ("ALREADY_STOCKED" if quantity>=THRESHOLD
            else "BELOW_30_AT_ISSUE"),quantity


def audit(*,ledger=V75,source=SOURCE,days=1,now=None,max_targets=MAX_TARGETS):
    if not 1<=days<=MAX_DAYS or not 1<=max_targets<=MAX_TARGETS:
        raise ValueError("invalid audit horizon or target cap")
    asof=int(time.time() if now is None else now)
    if Path(ledger).resolve(strict=True)==Path(source).resolve(strict=True):
        raise ValueError("identical source/sidecar forbidden")
    with closing(ro(ledger)) as evidence:
        events,raw,invalid=select_unique(
            evidence,start=asof-days*86400,end=asof)
    if len(events)>max_targets:
        raise ValueError("too many target events; narrow --days")

    cohorts=defaultdict(Counter)
    per_item=defaultdict(lambda:defaultdict(Counter))
    states=Counter()
    with closing(ro(source)) as stock:
        for row in events:
            key=row["item_key"]
            country,item=key.split(":",1)
            issued=int(row["computed_at"])
            dep=int(row["departure"])
            arr=int(row["arrival"])
            kind="QUICK_0_TO_5M" if dep-issued<=300 else "WATCH_OVER_5M"
            issued_state,qty=issue_stock(
                stock,country,item,issued,int(row["stock_as_of"]))
            states[issued_state]+=1
            category=f"{kind}/{issued_state}"
            result,success,_=observation(stock,country,item,arr,asof)
            baseline,b_success,_=observation(
                stock,country,item,issued+TRAVEL_SECONDS[country],asof)
            for counter in (cohorts[category],per_item[key][category]):
                counter["targets"]+=1
                counter["arrival_success"]+=int(success is True)
                counter["arrival_miss"]+=int(success is False)
                counter["arrival_pending"]+=int(result=="PENDING")
                counter["arrival_unscorable_other"]+=int(
                    success is None and result!="PENDING")
                if success is not None and b_success is not None:
                    counter["paired"]+=1
                    pair=("both_success" if success and b_success else
                          "recommendation_only" if success else
                          "immediate_only" if b_success else "both_miss")
                    counter[pair]+=1
                elif success is not None:
                    counter["immediate_unscorable"]+=1
                elif b_success is not None:
                    counter["recommendation_unscorable"]+=1

    def pack(c):
        scored=c["arrival_success"]+c["arrival_miss"]
        paired=c["paired"]
        lift=c["recommendation_only"]-c["immediate_only"]
        return {
            **dict(c),"scorable":scored,
            "proxy_hit_fraction":round(c["arrival_success"]/scored,4)
                                  if scored else None,
            "matched_net_gain_count":lift,
            "matched_net_gain_fraction":round(lift/paired,4)
                                         if paired else None
        }
    result={
        "status":"V99_READONLY_ISSUED_STOCK_DIAGNOSTIC",
        "research_only":True,"collector_written":False,
        "sidecar_written":False,"country_freshness_certified":False,
        "independent_restock_events_certified":False,
        "exact_arrival_accuracy_certified":False,
        "asof_epoch":asof,"days":days,
        "raw_as_issued_rows":raw,"excluded_invalid_or_abstained":invalid,
        "distinct_item_arrival_targets":len(events),
        "issued_stock_states":dict(sorted(states.items())),
        "cohorts":{k:pack(v) for k,v in sorted(cohorts.items())},
        "per_item":{
            k:{name:pack(c) for name,c in sorted(groups.items())}
            for k,groups in sorted(per_item.items())},
        "note":"Stock present at issuance is not new forecasting skill. All results use proxy stock data; grouped targets are not independent restocks.",
    }
    if sum(c["targets"] for c in cohorts.values())!=len(events):
        raise AssertionError("cohort conservation violated")
    return result


def pretty(r):
    print("===== V99 ALREADY STOCKED VS PREDICTED NEW OPPORTUNITY =====")
    print("raw issued records:",r["raw_as_issued_rows"])
    print("distinct item/arrival targets:",r["distinct_item_arrival_targets"])
    print("issuance stock state:",json.dumps(r["issued_stock_states"]))
    print("===== COHORT RESULTS =====")
    for name,c in r["cohorts"].items():
        print(f"{name}: targets={c['targets']} scored={c['scorable']} "
              f"hits={c.get('arrival_success',0)} misses={c.get('arrival_miss',0)} "
              f"rate={c['proxy_hit_fraction']} paired={c.get('paired',0)} "
              f"rec_only={c.get('recommendation_only',0)} "
              f"immediate_only={c.get('immediate_only',0)} "
              f"net_gain_fraction={c['matched_net_gain_fraction']}")
    print("===== PER-ITEM COHORTS =====")
    for item,groups in r["per_item"].items():
        print(item)
        for name,c in groups.items():
            print(f"  {name:38} targets={c['targets']:4d} "
                  f"scored={c['scorable']:4d} hits={c.get('arrival_success',0):4d} "
                  f"misses={c.get('arrival_miss',0):3d} "
                  f"rec_only={c.get('recommendation_only',0):3d} "
                  f"imm_only={c.get('immediate_only',0):3d}")
    print("===== LIMITATION: NOT CERTIFIED GAME-WORLD ARRIVAL ACCURACY =====")
    print(r["note"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=1)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("Collector location does not match approved source")
    result=audit(days=args.days)
    if args.json:
        print(json.dumps(result,sort_keys=True))
    else:
        pretty(result)


if __name__=="__main__":
    main()
