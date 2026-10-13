"""V161 evaluate only truly recorded prospective V160 item/hour forecasts.

Never backfill forecast recommendations from collector history. Observation
uses V88 poll brackets after maturity; no real flight/purchase guarantee.
Unknown arrivals, pending and absent forecasts do not become misses.
Score independent, paired, and leave-now on identical issued snapshots.
The V128 roster's 'incumbent_model_family' is metadata, NOT an incumbent
prediction. Real specialist-issued forecasts require separate alignment.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v88_poll_state_forward_report import observation
from research.v128_full24_earliest_shadow import COLLECTOR,exact_roster
from research.v160_prospective_v151_shadow import DESTINATION,POLICY,MODEL_VARIANTS

MAX_ROWS=20000
MAX_DAYS=14
GRACE=10


def _ro(path):
    source=Path(path).resolve(strict=True)
    con=sqlite3.connect(source.as_uri()+"?mode=ro",uri=True,timeout=12)
    con.execute("PRAGMA query_only=ON")
    return con


def _valid(item,issued,payload):
    if (not isinstance(payload,dict) or payload.get("policy_id")!=POLICY
        or payload.get("item_key")!=item or
        payload.get("issued_epoch")!=issued or
        payload.get("research_only") is not True or
        payload.get("published_to_website") is not False or
        payload.get("incumbent_forecast_evaluated") is not False):
        raise ValueError("invalid, contaminated forward issue")
    country=item.split(":",1)[0]
    flight=TRAVEL_SECONDS[country]
    models=payload.get("models")
    if not isinstance(models,dict) or set(models)!=set(MODEL_VARIANTS):
        raise ValueError("missing model variants")
    for variant,forecast in models.items():
        if not isinstance(forecast,dict):
            raise ValueError("invalid model output")
        dep,arr=forecast.get("departure_epoch"),forecast.get("arrival_epoch")
        if dep is None:
            if arr is not None or forecast.get("wait_seconds") is not None:
                raise ValueError("abstaining model invented arrival")
            continue
        if (type(dep) is not int or type(arr) is not int or
            not issued<=dep<=issued+28800 or arr!=dep+flight or
            forecast.get("wait_seconds")!=dep-issued):
            raise ValueError("issued travel time or wait inconsistent")


def score(*, ledger=DESTINATION, collector=COLLECTOR,
          now=None,days=7,roster=None,max_rows=MAX_ROWS,
          scorer=observation):
    if (type(days) is not int or not 1<=days<=MAX_DAYS or
        type(max_rows) is not int or not 1<=max_rows<=MAX_ROWS):
        raise ValueError("invalid requested report range")
    asof=int(time.time()) if now is None else now
    roster=exact_roster() if roster is None else roster
    if len(roster)!=24 or set(TRAVEL_SECONDS).isdisjoint(
        x.split(":",1)[0] for x in roster):
        raise ValueError("unexpected 24-item roster")
    if Path(collector).resolve(strict=True)==Path(ledger).resolve(strict=True):
        raise ValueError("source and forward ledger cannot be same")
    with closing(_ro(ledger)) as db:
        raw=db.execute(
            """SELECT item_key,issued_epoch,payload_json FROM v160_issued
               WHERE issued_epoch BETWEEN ? AND ? AND policy_id=?
               ORDER BY issued_epoch,item_key LIMIT ?""",
            (asof-days*86400,asof,POLICY,max_rows+1),
        ).fetchall()
    if len(raw)>max_rows:
        raise ValueError("report query exceeded item-count bound")
    decoded=[]
    for item,issued,body in raw:
        if item not in roster:
            raise ValueError("unexpected item in live research roster")
        data=json.loads(body)
        _valid(item,issued,data)
        decoded.append(data)
    by_item=defaultdict(list)
    for row in decoded:
        by_item[row["item_key"]].append(row)
    for rows in by_item.values():
        rows.sort(key=lambda r:r["issued_epoch"])
    first={}
    for row in decoded:
        item=row["item_key"]
        slot=(item,row["issued_epoch"]//3600)
        first.setdefault(slot,row)

    per_item={item:Counter() for item in roster}
    distinct_phase={item:set() for item in roster}
    waits={item:defaultdict(list) for item in roster}
    compared=Counter()
    with closing(_ro(collector)) as db:
        for row in first.values():
            item=row["item_key"]
            issue=row["issued_epoch"]
            country,name=item.split(":",1)
            c=per_item[item]
            c["issued_item_hours"]+=1
            phase,onset=row.get("phase"),row.get("phase_onset")
            if phase in ("HIGH","LOW") and type(onset) is int and 0<onset<=issue:
                distinct_phase[item].add((phase,onset))
            now_status,now_hit,_=scorer(
                db,country,name,issue+TRAVEL_SECONDS[country],asof)
            if now_hit is None:
                c["leave_now_unknown"]+=1
            else:
                c["leave_now_hit" if now_hit else "leave_now_miss"]+=1
            outcomes={}
            for variant in MODEL_VARIANTS:
                candidate=row["models"][variant]
                dep=candidate["departure_epoch"]
                if dep is None:
                    c[variant+"_abstain"]+=1
                    outcomes[variant]=None
                    continue
                c[variant+"_proposals"]+=1
                waits[item][variant].append((dep-issue)/60)
                if dep>issue+300:
                    # A future forecast cannot be treated as an executable
                    # five-minute decision without an as-issued recheck.
                    updates=[r for r in by_item[item]
                             if issue<r["issued_epoch"]<=dep and
                             dep-600<=r["issued_epoch"]]
                    matching=[
                        r for r in updates if
                        r["models"][variant]["departure_epoch"] is not None and
                        abs(r["models"][variant]["departure_epoch"]-dep)<=300 and
                        r["models"][variant]["departure_epoch"]-r["issued_epoch"]<=300
                    ]
                    if not matching:
                        c[variant+"_future_unreconfirmed"]+=1
                    else:
                        c[variant+"_future_reconfirmed"]+=1
                _,hit,_=scorer(db,country,name,candidate["arrival_epoch"],asof)
                outcomes[variant]=hit
                c[variant+("_unknown" if hit is None else
                           "_hit" if hit else "_miss")]+=1
                if hit is not None and now_hit is not None:
                    c[variant+"_matched_now"]+=1
                    if hit and not now_hit:
                        c[variant+"_exclusive_vs_now"]+=1
                    if now_hit and not hit:
                        c["now_exclusive_vs_"+variant]+=1
            old=outcomes["independent"]
            new=outcomes["paired_complete"]
            if old is not None and new is not None:
                c["paired_matched_independent"]+=1
                compared["paired_matched_independent"]+=1
                if new and not old:
                    c["paired_only_hit"]+=1
                elif old and not new:
                    c["independent_only_hit"]+=1
    summary={}
    allcounts=Counter()
    for item in sorted(roster):
        c=per_item[item]
        allcounts.update(c)
        summary[item]={
            **{key:c[key] for key in (
                "issued_item_hours","leave_now_hit","leave_now_miss",
                "leave_now_unknown","independent_proposals",
                "independent_abstain","independent_hit",
                "independent_miss","independent_unknown",
                "paired_complete_proposals","paired_complete_abstain",
                "paired_complete_hit","paired_complete_miss",
                "paired_complete_unknown","paired_matched_independent",
                "paired_only_hit","independent_only_hit",
                "independent_future_reconfirmed",
                "independent_future_unreconfirmed",
                "paired_complete_future_reconfirmed",
                "paired_complete_future_unreconfirmed"
            )},
            "unique_issued_stock_phases":len(distinct_phase[item]),
            "independent_mean_wait_minutes":(
                round(sum(waits[item]["independent"])/len(waits[item]["independent"]),2)
                if waits[item]["independent"] else None),
            "paired_mean_wait_minutes":(
                round(sum(waits[item]["paired_complete"])/len(waits[item]["paired_complete"]),2)
                if waits[item]["paired_complete"] else None),
        }
    for key in (
        "issued_item_hours","paired_matched_independent",
        "paired_only_hit","independent_only_hit",
        "independent_hit","independent_miss","independent_unknown",
        "paired_complete_hit","paired_complete_miss",
        "paired_complete_unknown","leave_now_hit","leave_now_miss",
        "leave_now_unknown","independent_future_unreconfirmed",
        "paired_complete_future_unreconfirmed",
    ):
        allcounts.setdefault(key,0)
    return {
        "status":"V161_TRUE_PROSPECTIVE_V151_24_ITEM_SHADOW_REPORT",
        "policy_id":POLICY,"report_asof_epoch":asof,
        "issued_item_hours":len(first),
        "recorded_five_minute_item_rows":len(decoded),
        "roster_size":len(roster),
        "totals":dict(allcounts),
        "paired_minus_independent_matched_net":(
            allcounts["paired_only_hit"]-allcounts["independent_only_hit"]),
        "items":summary,
        "historically_reconstructed_issues":False,
        "actual_player_flights_verified":False,
        "per_country_freshness_verified":False,
        "specialist_predictions_scored":False,
        "website_or_collector_modified":False,
        "only_mature_observations_used_for_scoring":True,
        "stock_at_arrival_is_bracketed_poll_proxy":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=7)
    a=p.parse_args()
    print(json.dumps(score(days=a.days),sort_keys=True))


if __name__=="__main__":
    main()
