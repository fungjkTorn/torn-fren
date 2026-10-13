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
from research.v76_forward_research_report import V75,eligible as valid_v75_proposal

MAX_ROWS=120000
MAX_DAYS=14
GRACE=10
MAX_V75_ROWS=120000
MAX_BENCHMARK_AGE=180


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


def _load_v75(v75, start, end):
    """Only independently RECORDED V75 private decisions, never roster labels.

    V75 is an existing 21-item private specialist research ledger. Its
    issuance may be 0-180s before our new research snapshot; alignment
    therefore is labeled near-issue, not EXACT simultaneous issuance.
    """
    if v75 is None:
        return None,"DISABLED"
    path=Path(v75)
    if not path.is_file():
        return None,"ABSENT"
    with closing(_ro(path)) as conn:
        conn.row_factory=sqlite3.Row
        records=conn.execute(
            """SELECT item_key,computed_at,stock_as_of,status,valid_until,
                      departure,arrival,actual_player_departure
               FROM v42_candidate_decisions
               WHERE computed_at BETWEEN ? AND ?
               ORDER BY computed_at,item_key LIMIT ?""",
            (start-MAX_BENCHMARK_AGE,end,MAX_V75_ROWS+1),
        ).fetchall()
    if len(records)>MAX_V75_ROWS:
        raise ValueError("unbounded V75 specialist candidate history")
    by_key=defaultdict(list)
    for row in records:
        if valid_v75_proposal(row):
            by_key[row["item_key"]].append({
                "computed_at":row["computed_at"],
                "valid_until":row["valid_until"],
                "departure":row["departure"],
                "arrival":row["arrival"],
            })
    return by_key,"READ_ONLY_V75_PRIVATE_CANDIDATE_LEDGER"


def score(*, ledger=DESTINATION, collector=COLLECTOR,
          now=None,days=2,roster=None,max_rows=MAX_ROWS,
          v75=V75,scorer=observation):
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
    v75_by_item,v75_status=_load_v75(
        v75,asof-days*86400,asof)
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
            if now_status=="PENDING":
                c["leave_now_pending"]+=1
            elif now_hit is None:
                c["leave_now_unknown"]+=1
            else:
                c["leave_now_hit" if now_hit else "leave_now_miss"]+=1
            # Optional specialist comparison is based on the actual V75
            # private issued ledger. Reject any later-issued prediction,
            # stale alignment, or proposal whose original validity expired.
            specialist=None
            if v75_by_item is not None:
                candidates=v75_by_item.get(item,[])
                for c0 in reversed(candidates):
                    t0=c0["computed_at"]
                    if t0>issue:
                        continue
                    if issue-t0>MAX_BENCHMARK_AGE:
                        break
                    if issue<=c0["valid_until"]:
                        specialist=c0
                        break
            if specialist is not None:
                c["v75_near_issued_proposals"]+=1
                v75_state,v75_hit,_=scorer(
                    db,country,name,specialist["arrival"],asof)
                if v75_state=="PENDING":
                    c["v75_pending"]+=1
                elif v75_hit is None:
                    c["v75_unknown"]+=1
                else:
                    c["v75_hit" if v75_hit else "v75_miss"]+=1
            else:
                v75_hit=None
                c["v75_unmatched_or_no_proposal"]+=1
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
                    # A future WATCH is not a proven actionable decision.
                    # Do not call it unreconfirmed before its departure time.
                    if asof<dep:
                        c[variant+"_future_reconfirmation_pending"]+=1
                    else:
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
                proxy_status,hit,_=scorer(
                    db,country,name,candidate["arrival_epoch"],asof)
                outcomes[variant]=hit
                if v75_hit is not None and hit is not None:
                    c[variant+"_matched_v75"]+=1
                    if hit and not v75_hit:
                        c[variant+"_only_vs_v75"]+=1
                    elif v75_hit and not hit:
                        c["v75_only_vs_"+variant]+=1
                c[variant+("_pending" if proxy_status=="PENDING" else
                           "_unknown" if hit is None else
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
                "leave_now_pending","leave_now_unknown","independent_proposals",
                "independent_abstain","independent_hit",
                "independent_miss","independent_pending","independent_unknown",
                "paired_complete_proposals","paired_complete_abstain",
                "paired_complete_hit","paired_complete_miss",
                "paired_complete_pending","paired_complete_unknown","paired_matched_independent",
                "paired_only_hit","independent_only_hit",
                "independent_future_reconfirmed",
                "independent_future_unreconfirmed",
                "independent_future_reconfirmation_pending",
                "paired_complete_future_reconfirmed",
                "paired_complete_future_unreconfirmed",
                "paired_complete_future_reconfirmation_pending",
                "v75_near_issued_proposals","v75_unmatched_or_no_proposal",
                "v75_hit","v75_miss","v75_pending","v75_unknown",
                "independent_matched_v75","independent_only_vs_v75",
                "v75_only_vs_independent",
                "paired_complete_matched_v75",
                "paired_complete_only_vs_v75","v75_only_vs_paired_complete"
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
        "independent_hit","independent_miss","independent_pending",
        "independent_unknown","paired_complete_hit","paired_complete_miss",
        "paired_complete_pending","paired_complete_unknown",
        "leave_now_hit","leave_now_miss","leave_now_pending",
        "leave_now_unknown","independent_future_reconfirmation_pending",
        "paired_complete_future_reconfirmation_pending",
        "independent_future_unreconfirmed",
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
        "v75_private_specialist_source_status":v75_status,
        "v75_alignment":"actual privately issued V75 proposal <=180s prior, not simultaneous",
        "v75_matched_pair_net_paired_minus_v75":(
            allcounts["paired_complete_only_vs_v75"]-
            allcounts["v75_only_vs_paired_complete"]),
        "specialist_predictions_scored":bool(
            allcounts["v75_near_issued_proposals"]),
        "website_or_collector_modified":False,
        "only_mature_observations_used_for_scoring":True,
        "stock_at_arrival_is_bracketed_poll_proxy":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=2)
    a=p.parse_args()
    print(json.dumps(score(days=a.days),sort_keys=True))


if __name__=="__main__":
    main()
