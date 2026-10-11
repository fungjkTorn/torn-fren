"""V116: model-family attribution and hourly-first forward flight audit.

V115 found 227 poll-state matched arrivals with more hits for departing
immediately (169) than following the V75 proposed departures (154).
V115 does NOT identify the producing model family and a distinct arrival
timestamp is NOT a distinct restock cycle. This diagnostic addresses both
limitations using the ORIGINAL frozen V75 v42_candidate_decisions.

Features:
- Read-only SQL filter for Red Fox and Nessie BEFORE loading predictions.
- Retain V76 as-issued validity contract and first item+arrival dedup.
- Attribute each candidate to the saved model_family; do not conflate
  private V75 shadow with established specialist/champion evaluations.
- Take the FIRST valid, deduped issuance per ITEM per UTC HOUR, before
  looking at the stock outcome. This is one time-bin representative, NOT
  claimed independent restock.
- Score forecast and immediate-departure arrivals using EXACTLY the same
  V88 poll-heartbeat state evaluator and 10s evaluation grace.
- Report model family, departure-delay bucket, matched discordances,
  censoring, and timestamp grouping. Never score unknown as a failure.
- Never conclude calibration/statistical significance from a single day.

Zero API calls, zero changes to production collectors, DB, timers, or
models. The country update age is not preserved in historical SQLite and
the presence of a successful global heartbeat does NOT verify freshness.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v60_private_snapshot_probe import approved_collector_source
from research.v76_forward_research_report import (
    V75,eligible,ro,MAX_CANDIDATE_ROWS,MAX_PROXY_EVENTS
)
from research.v88_poll_state_forward_report import observation
from research.v115_targeted_v88_forward_evidence import ITEMS

MAX_HOURS=24


def select_candidates(db,*,start,end,keys,limit=MAX_PROXY_EVENTS):
    if (not 1<=len(keys)<=len(ITEMS)
        or any(k not in ITEMS.values() for k in keys)
        or not 1<=limit<=MAX_PROXY_EVENTS):
        raise ValueError("invalid target item keys or cap")
    marks=",".join("?" for _ in keys)
    sql=(
        "FROM v42_candidate_decisions "
        "WHERE computed_at>=? AND computed_at<=? "
        f"AND item_key IN ({marks})"
    )
    params=(start,end,*keys)
    n=int(db.execute("SELECT count(*) "+sql,params).fetchone()[0])
    if n>MAX_CANDIDATE_ROWS:
        raise ValueError("too many raw matching candidates; narrow hours")
    rows=db.execute(
        "SELECT item_key,computed_at,stock_as_of,status,valid_until,"
        "departure,arrival,actual_player_departure,model_family,"
        "model_config "
        +sql+" ORDER BY computed_at ASC,id ASC",params
    ).fetchall()
    out={}
    invalid=Counter()
    for r in rows:
        if not eligible(r):
            invalid["INVALID_OR_ABSTAINED"]+=1
            continue
        family=r["model_family"]
        if not family or not isinstance(family,str):
            raise AssertionError("missing model family in valid frozen evidence")
        key=(r["item_key"],int(r["arrival"]))
        if key not in out:
            out[key]=r
            if len(out)>limit:
                raise ValueError("more than 1200 target arrivals: narrow hours")
    return list(out.values()),n,dict(invalid)


def first_per_item_hour(rows):
    """Pre-outcome representative; never select by scored performance."""
    slots={}
    for row in rows:
        key=(row["item_key"],int(row["computed_at"])//3600)
        if key not in slots:
            slots[key]=row
    return list(slots.values())


def delay_bucket(seconds):
    if seconds==0:return "immediate"
    if seconds<=300:return "delay_0_to_5m"
    if seconds<=900:return "delay_5_to_15m"
    if seconds<=3600:return "delay_15_to_60m"
    return "delay_over_60m"


def tally_rows(rows,conn,*,asof,score=observation):
    out=Counter()
    families=defaultdict(Counter)
    by_item=defaultdict(Counter)
    by_delay=defaultdict(Counter)
    example=[]
    for row in rows:
        country,item=row["item_key"].split(":",1)
        arrival=int(row["arrival"])
        immediate=int(row["computed_at"])+TRAVEL_SECONDS[country]
        seconds=int(row["departure"])-int(row["computed_at"])
        if not 0<=seconds<=28800:
            raise AssertionError("invalid departure lead time")
        delay=delay_bucket(seconds)
        status,hit,_=score(conn,country,item,arrival,asof)
        status0,hit0,_=score(conn,country,item,immediate,asof)
        for counts in (
            out,families[row["model_family"]],
            by_item[row["item_key"]],by_delay[delay]):
            counts["issued"]+=1
            counts[f"recommendation_{status}"]+=1
            counts[f"immediate_{status0}"]+=1
            counts["both_scorable"]+=int(hit is not None and hit0 is not None)
            if hit is not None and hit0 is not None:
                label=("both_hit" if hit and hit0 else
                       "recommendation_only" if hit else
                       "immediate_only" if hit0 else "both_miss")
                counts[label]+=1
            if seconds==0:counts["identical_departure"]+=1
            else:counts["delayed_departure"]+=1
        if len(example)<6:
            example.append({
                "item_key":row["item_key"],
                "issue_epoch":int(row["computed_at"]),
                "family":row["model_family"],
                "delay_minutes":round(seconds/60,2),
                "arrival":arrival,
                "forecast_outcome_status":status,
                "immediate_outcome_status":status0,
                "outcome_country_source_freshness_verified":False,
            })
    def conv(counter):
        d=dict(sorted(counter.items()))
        score_n=d.get("both_scorable",0)
        d["matched_proxy_net_recommendation_only_minus_immediate_only"]=(
            d.get("recommendation_only",0)-d.get("immediate_only",0))
        d["matched_recommendation_hit_fraction"]=(
            round((d.get("both_hit",0)+d.get("recommendation_only",0))
                  /score_n,4) if score_n else None)
        d["matched_immediate_hit_fraction"]=(
            round((d.get("both_hit",0)+d.get("immediate_only",0))
                  /score_n,4) if score_n else None)
        return d
    return {
        "all":conv(out),
        "per_family":{k:conv(v) for k,v in sorted(families.items())},
        "per_item":{k:conv(v) for k,v in sorted(by_item.items())},
        "per_departure_lead":{k:conv(v) for k,v in sorted(by_delay.items())},
        "examples":example,
    }


def audit(*,ledger=V75,stock=None,now=None,hours=24,
          keys=tuple(ITEMS.values()),limit=MAX_PROXY_EVENTS,
          score=observation):
    from research.v88_poll_state_forward_report import SOURCE as DEFAULT_STOCK
    stock=DEFAULT_STOCK if stock is None else stock
    if (not 1<=hours<=MAX_HOURS or not 1<=limit<=MAX_PROXY_EVENTS
        or len(set(keys))!=len(keys) or not set(keys)<=set(ITEMS.values())):
        raise ValueError("invalid item-scoped window")
    if Path(ledger).resolve(strict=True)==Path(stock).resolve(strict=True):
        raise ValueError("collector and prediction ledger must differ")
    to=int(time.time() if now is None else now)
    start=to-hours*3600
    with closing(ro(ledger)) as evidence:
        selected,raw,invalid=select_candidates(
            evidence,start=start,end=to,keys=keys,limit=limit)
    representative=first_per_item_hour(selected)
    with closing(ro(stock)) as observed:
        summary=tally_rows(representative,observed,asof=to,score=score)
        full_family_counts=Counter(r["model_family"] for r in selected)
    return {
        "status":"V116_FIRST_PER_ITEM_UTC_HOUR_FAMILY_ATTRIBUTED_FORWARD_AUDIT",
        "read_only":True,
        "targeted_items":list(keys),
        "window_hours":hours,
        "raw_targeted_candidate_rows":raw,
        "invalid_or_abstained_rows":invalid,
        "unique_item_arrival_targets":len(selected),
        "unique_arrival_targets_by_family":dict(sorted(full_family_counts.items())),
        "first_per_item_UTC_hour":len(representative),
        "one_per_item_per_hour_not_certified_independent_restocks":True,
        "representative_first_issued_before_outcome":True,
        "country_provider_freshness_verified":False,
        "actual_gameplay_success_verified":False,
        "hourly_representative_matched_poll_proxy":summary,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--items",nargs="+",choices=tuple(ITEMS),
                   default=["redfox","nessie"])
    p.add_argument("--limit",type=int,default=MAX_PROXY_EVENTS)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    from research.v88_poll_state_forward_report import SOURCE
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved collector source")
    out=audit(hours=args.hours,limit=args.limit,
              keys=tuple(ITEMS[name] for name in dict.fromkeys(args.items)))
    if args.json:
        print(json.dumps(out,sort_keys=True))
        return
    print("===== V116 ATTRIBUTED V75 FORWARD RESULTS / HOURLY-FIRST =====")
    print("window_hours:",out["window_hours"],
          "raw target rows:",out["raw_targeted_candidate_rows"],
          "valid unique arrivals:",out["unique_item_arrival_targets"])
    print("full-candidate family attribution:",
          json.dumps(out["unique_arrival_targets_by_family"],sort_keys=True))
    print("hourly-first representative events:",
          out["first_per_item_UTC_hour"])
    s=out["hourly_representative_matched_poll_proxy"]
    print("hourly-first overall:",json.dumps(s["all"],sort_keys=True))
    print("by item:",json.dumps(s["per_item"],sort_keys=True))
    print("by model family:",json.dumps(s["per_family"],sort_keys=True))
    print("by model departure delay:",json.dumps(
          s["per_departure_lead"],sort_keys=True))
    print("sample of as-issued model families:",json.dumps(
        s["examples"][:4],sort_keys=True))
    print("RESEARCH ONLY: global heartbeat is not fresh country stock.")
    print("UTC-hour representatives may share underlying restock cycles.")


if __name__=="__main__":
    main()
