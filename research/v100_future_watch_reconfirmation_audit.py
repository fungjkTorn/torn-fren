"""V100 read-only: did an as-issued distant watch survive to its departure?

V99 revealed apparently good 5m+ forecasts that were *not executable* while
their original five-minute snapshot expired. For each FIRST-AS-ISSUED item /
arrival target, inspect the last later research candidate whose snapshot was
valid at that original departure timestamp.

A late candidate confirming roughly the same departure is a useful *proxy
of recommendation persistence*, not proof a player saw the website, bought
items, or experienced fresh YATA state. Distinct arrival target records remain
correlated, so rates are NOT independently sampled restock success.

By default reads ONLY V75 private sidecar. Optional --stock-proxy also scores
the eventual arrival from the V88 read-only collector reconstruction; that
proxy is not verified country-level fresh stock or gameplay accuracy.

No writes or new forecasts. Bounded issue-time cohort, no list truncation.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing,nullcontext
from pathlib import Path

from research.v76_forward_research_report import V75,SOURCE,ro,eligible,select_unique
from research.v88_poll_state_forward_report import observation
from research.v89_pending_horizon_diagnostic import wait_bucket
from research.v60_private_snapshot_probe import approved_collector_source

MAX_DAYS=3
MAX_ROWS=50000
MAX_TARGETS=12000
RECHECK_SECONDS=300
NEAR_DEPARTURE_TOLERANCE=300
WATCH_THRESHOLD_SECONDS=300
SUCCESS="POLL_STATE_PROXY_SUCCESS"
MISS="POLL_STATE_PROXY_MISS"


def late_state(original, item_rows, issue_times, asof):
    """As-of-original-departure recheck only; no future-recommendation leakage."""
    dep=int(original["departure"])
    issued=int(original["computed_at"])
    if dep>asof:
        return "TARGET_DEPARTURE_NOT_REACHED",None
    pos=bisect.bisect_right(issue_times,dep)-1
    if pos<0:
        return "NO_RECENT_RECHECK",None
    row=item_rows[pos]
    new_issue=int(row["computed_at"])
    if new_issue<=issued:
        return "NO_LATER_RECHECK",None
    if dep-new_issue>RECHECK_SECONDS or int(row["valid_until"])<dep:
        return "NO_RECENT_RECHECK",None
    if not eligible(row):
        return "RECHECK_ABSTAINED_OR_INVALID",None
    new_dep=int(row["departure"])
    difference=new_dep-dep
    if difference==0:
        return "EXACT_DEPARTURE_RECONFIRMED",difference
    if (abs(difference)<=NEAR_DEPARTURE_TOLERANCE and
        new_dep>=new_issue):
        return "NEARBY_DEPARTURE_RECONFIRMED",difference
    return "DIFFERENT_DEPARTURE_AT_RECHECK",difference


def audit(*,sidecar=V75,source=SOURCE,days=1,asof=None,
          max_targets=MAX_TARGETS,with_stock_proxy=False):
    if not 1<=days<=MAX_DAYS or not 1<=max_targets<=MAX_TARGETS:
        raise ValueError("invalid bounded read-only audit")
    now=int(time.time() if asof is None else asof)
    start=now-days*86400
    with closing(ro(sidecar)) as db:
        events,raw,invalid=select_unique(db,start=start,end=now)
        # This is a bounded 1-3 day as-issued cohort; every candidate within
        # the cohort is needed to reconstruct the last recheck as-of departure.
        candidates=db.execute(
            """SELECT item_key,computed_at,stock_as_of,status,
                      valid_until,departure,arrival,actual_player_departure
               FROM v42_candidate_decisions
               WHERE computed_at>=? AND computed_at<=?
               ORDER BY computed_at ASC,id ASC LIMIT ?""",
            (start,now,MAX_ROWS+1)).fetchall()
    if len(events)>max_targets or len(candidates)>MAX_ROWS:
        raise ValueError("cohort exceeds safe limit: use shorter days")

    timeline=defaultdict(list)
    # Original sidecar may have identical computed_at timestamps; last row at
    # each issue epoch wins deterministically (matches stored decision order).
    for row in candidates:
        timeline[row["item_key"]].append(row)
    times={key:[int(r["computed_at"]) for r in records]
           for key,records in timeline.items()}

    outcomes=Counter()
    per_item=defaultdict(Counter)
    wait_hist=defaultdict(Counter)
    stock_cross=defaultdict(Counter)
    with (closing(ro(source)) if with_stock_proxy else nullcontext(None)) as stock:
        for row in events:
            key=row["item_key"]
            issued=int(row["computed_at"])
            delay=int(row["departure"])-issued
            if delay<=WATCH_THRESHOLD_SECONDS:
                continue
            status,diff=late_state(row,timeline.get(key,[]),
                                   times.get(key,[]),now)
            outcomes[status]+=1
            per_item[key][status]+=1
            wait_hist[wait_bucket(delay)][status]+=1
            if stock is not None:
                country,item=key.split(":",1)
                label,hit,_=observation(stock,country,item,
                                         int(row["arrival"]),now)
                marker=("HIT" if hit is True else "MISS" if hit is False
                        else "UNKNOWN")
                stock_cross[(status,marker)]+=1

    confirmed=outcomes["EXACT_DEPARTURE_RECONFIRMED"]+outcomes[
        "NEARBY_DEPARTURE_RECONFIRMED"]
    elapsed=sum(outcomes.values())-outcomes["TARGET_DEPARTURE_NOT_REACHED"]
    def pack(c):
        n=sum(c.values())
        return {"n":n,"exact":c["EXACT_DEPARTURE_RECONFIRMED"],
                "nearby":c["NEARBY_DEPARTURE_RECONFIRMED"],
                "shifted":c["DIFFERENT_DEPARTURE_AT_RECHECK"],
                "abstained":c["RECHECK_ABSTAINED_OR_INVALID"],
                "no_recent":c["NO_RECENT_RECHECK"]+c["NO_LATER_RECHECK"],
                "unreached":c["TARGET_DEPARTURE_NOT_REACHED"]}
    return {
        "status":"V100_AS_ISSUED_WATCH_RECONFIRMATION_AUDIT",
        "research_only":True,"sidecar_written":False,
        "collector_written":False,"live_service_changed":False,
        "asof_epoch":now,"issue_days":days,
        "raw_issued_candidates":raw,"excluded_invalid_or_abstained":invalid,
        "distinct_item_arrival_targets":len(events),
        "original_future_watch_targets":sum(outcomes.values()),
        "future_watch_departures_reached":elapsed,
        "future_watch_targets_reconfirmed":confirmed,
        "reconfirmation_fraction_among_reached":round(confirmed/elapsed,4)
                   if elapsed else None,
        "late_recheck_snapshot_seconds":RECHECK_SECONDS,
        "departure_match_tolerance_seconds":NEAR_DEPARTURE_TOLERANCE,
        "categories":dict(sorted(outcomes.items())),
        "per_item":{k:pack(v) for k,v in sorted(per_item.items())},
        "issue_wait_bucket_outcomes":{
            k:pack(v) for k,v in sorted(wait_hist.items())},
        "optional_stock_proxy":bool(with_stock_proxy),
        "stock_proxy_by_reconfirmation_status":{
            k:{z:c for (state,z),c in stock_cross.items() if state==k}
            for k in sorted({a for a,b in stock_cross})},
        "warnings":(
            "This is same-departure reconfirmation within 300 seconds, NOT "
            "an assertion that a user was given travel advice; missing "
            "rechecks can reflect worker gaps. Matching time windows could "
            "belong to correlated repeats of one restock. Proxy stock "
            "outcomes lack certified country-level update freshness."
        ),
    }


def pretty(r):
    print("===== V100: DID FUTURE WATCHES SURVIVE TO DEPARTURE? =====")
    for k in ("raw_issued_candidates","distinct_item_arrival_targets",
              "original_future_watch_targets","future_watch_departures_reached",
              "future_watch_targets_reconfirmed",
              "reconfirmation_fraction_among_reached"):
        print(f"{k}: {r[k]}")
    print("===== RECHECK CLASSIFICATIONS =====")
    for k,v in sorted(r["categories"].items()):
        print(f"{k}: {v}")
    print("===== RECONFIRMATION BY ORIGINAL WAIT =====")
    for name,c in r["issue_wait_bucket_outcomes"].items():
        print(f'{name}: total={c["n"]} exact={c["exact"]} nearby={c["nearby"]} '
              f'shifted={c["shifted"]} abstained={c["abstained"]} '
              f'no_recent={c["no_recent"]} unreached={c["unreached"]}')
    print("===== BY ITEM =====")
    for key,c in r["per_item"].items():
        print(f'{key:30} n={c["n"]:4} exact={c["exact"]:4} nearby={c["nearby"]:4} '
              f'shifted={c["shifted"]:4} abstained={c["abstained"]:4} '
              f'no_recent={c["no_recent"]:4} unreached={c["unreached"]:4}')
    if r["optional_stock_proxy"]:
        print("===== PROXY STOCK OUTCOMES BY RECONFIRMATION =====")
        for k,c in r["stock_proxy_by_reconfirmation_status"].items():
            print(k,json.dumps(c,sort_keys=True))
    print("===== IMPORTANT LIMITATIONS =====")
    print(r["warnings"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=1)
    p.add_argument("--with-stock-proxy",action="store_true")
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("Collector path not approved for read-only evaluation")
    report=audit(days=a.days,with_stock_proxy=a.with_stock_proxy)
    if a.json:
        print(json.dumps(report,sort_keys=True))
    else:
        pretty(report)


if __name__=="__main__":
    main()
