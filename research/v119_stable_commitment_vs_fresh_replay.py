"""V119 fixed-cohort forward replan vs 3-confirmation future commitment.

V118 found consecutive stable-looking future forecasts, especially for Nessie,
but zero 5-minute-valid departures. This tests a PREDECLARED alternative,
NOT a change or suggestion to execute game actions.

For exactly the first eligible frozen V75 candidate per item per UTC hour:
A. leave immediately at that issue (counterfactual baseline);
B. first fresh, actionable <=5m departure (V117 policy, parity checked);
C. first fresh actionable departure OR 3 consecutive VALID forecasts
   no more than 10m between issues, with candidate departure epochs
   mutually within +/-5m of the first. Once 3-confirmation is reached,
   freeze its latest proposed departure at that time; DO NOT shift the
   commitment even if future five-minute research updates change.

The committed future departure is hypothetical: current site snapshots expire
after five minutes, so this is NOT currently an executable website offer.
The experiment asks whether a possible commitment rule is worth researching.

IMPORTANT simulation chronology: select a candidate only from issued-at-or-
before commitment ticks, never choose based on future stock and never execute
a departure before the confirming issue. Stops waiting after 8h from start.
When commitment time lies in the future of the evaluation-asof mark PENDING,
not a success. Missing/non-executable candidate != stock miss.

Same stock evaluator for all 3 policies (V88 heartbeat-carried stock proxy,
NOT upstream UK country update freshness or actual player purchase truth).
The first-per-hour cohort is not independent restock events, and the 24h
window was previously investigated. Frozen --asof makes run reproducible.
No DB writes, API calls, production services, or automatic gameplay.
"""
from __future__ import annotations

import argparse
import bisect
import json
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing

from research.plushie_champions.common import MAX_WAIT,STEP,TRAVEL_SECONDS
from research.v76_forward_research_report import V75,eligible,ro,MAX_PROXY_EVENTS
from research.v88_poll_state_forward_report import (
    SOURCE,observation as poll_observation
)
from research.v115_targeted_v88_forward_evidence import ITEMS
from research.v116_attributed_hourly_forward_audit import (
    select_candidates,first_per_item_hour
)
from research.v117_first_executable_replan_audit import (
    future_candidate_timelines,first_actionable_tick
)
from research.v60_private_snapshot_probe import approved_collector_source

CONFIRMATIONS=3
MAX_CONFIRM_ISSUE_GAP=600
CONFIRM_TARGET_TOLERANCE=300
MAX_HOURS=24
LABELS=("depart_now","fresh_5m","fresh_or_3stable")


def frozen_policy(original,rows,times,*,asof):
    """Choose a departure causally, frozen no later than each as-issued tick.

    Prefer first actionable 5m recommendation. Otherwise commit to the
    exact latest projected epoch after three uninterrupted valid forecasts
    agreeing within +/-5m against the first of the sequence.
    """
    start=int(original["computed_at"])
    deadline=start+MAX_WAIT
    at=bisect.bisect_left(times,start)
    chain=[]
    seen=0
    skips=Counter()
    for row in rows[at:]:
        t=int(row["computed_at"])
        if t>min(deadline,asof):
            break
        seen+=1
        if row["model_family"]!=original["model_family"]:
            chain=[]
            skips["DIFFERENT_MODEL_FAMILY"]+=1
            continue
        if not eligible(row):
            chain=[]
            skips["INVALID_OR_ABSTAINED"]+=1
            continue
        proposed=int(row["departure"])
        if not t<=proposed<=deadline:
            chain=[]
            skips["OUTSIDE_ORIGINAL_8H_WINDOW"]+=1
            continue
        if proposed<=t+STEP and proposed<=int(row["valid_until"]):
            return {
                "status":"FRESH_5M_EXECUTABLE",
                "departure":proposed,
                "committed_issue":t,
                "confirmation_count":1,
                "basis":"fresh",
                "ticks_seen":seen,
                "rejected_counts":dict(skips),
            }
        if (chain and
            (t-chain[-1][0]>MAX_CONFIRM_ISSUE_GAP
             or abs(proposed-chain[0][1])>CONFIRM_TARGET_TOLERANCE)):
            chain=[]
        chain.append((t,proposed))
        if len(chain)>=CONFIRMATIONS:
            latest=t
            if proposed<latest:
                raise AssertionError("confirmed departure before commitment")
            return {
                "status":"STABLE_3_COMMITMENT",
                "departure":proposed,
                "committed_issue":t,
                "confirmation_count":CONFIRMATIONS,
                "basis":"three_as_issued",
                "ticks_seen":seen,
                "rejected_counts":dict(skips),
            }
        skips["WAITING_FOR_STABILITY_OR_FRESH_DEPARTURE"]+=1
    return {
        "status":("UNRESOLVED_HORIZON_NOT_MATURE"
                  if asof<deadline else "NO_CONFIRMED_DEPARTURE_WITHIN_8H"),
        "departure":None,
        "committed_issue":None,
        "confirmation_count":0,
        "basis":None,
        "ticks_seen":seen,
        "rejected_counts":dict(skips),
    }


def _proxy(scorer,con,country,item,arrival,asof):
    # Do not query stock outcomes for flights arriving beyond the audit-asof.
    if arrival is None:
        return None,"NO_TRIP"
    if arrival+190>asof:
        return None,"PENDING_ARRIVAL"
    status,hit,_=scorer(con,country,item,arrival,asof)
    return hit,status


def summarize(records,label):
    counts=Counter()
    waits=[]
    for r in records:
        outcome=r["results"][label]
        departure=outcome["departure"]
        counts["start_cohort"]+=1
        counts[outcome["status"]]+=1
        if departure is not None:
            counts["scheduled"]+=1
            waits.append((departure-r["start"])/60)
        hit=outcome["proxy_hit"]
        if hit is True:counts["proxy_hit"]+=1
        elif hit is False:counts["proxy_miss"]+=1
        else:counts["proxy_unknown_or_no_trip"]+=1
        if outcome["proxy_status"]=="PENDING_ARRIVAL":
            counts["scheduled_arrival_pending"]+=1
        if outcome["proxy_status"]=="NO_TRIP":
            counts["no_trip"]+=1
    # JSON fields must not disappear just because the count is zero.
    for field in (
        "scheduled","proxy_hit","proxy_miss","proxy_unknown_or_no_trip",
        "scheduled_arrival_pending","no_trip"
    ):
        counts.setdefault(field,0)
    n=counts["start_cohort"]
    return {**dict(sorted(counts.items())),
            "coverage_of_all_starts":round(counts["scheduled"]/n,4) if n else None,
            "proxy_hits_per_start_lower_bound":round(counts["proxy_hit"]/n,4) if n else None,
            "proxy_hits_per_scorable_departure":(
                round(counts["proxy_hit"]/(counts["proxy_hit"]+counts["proxy_miss"]),4)
                if counts["proxy_hit"]+counts["proxy_miss"] else None),
            "mean_scheduled_wait_minutes":(
                round(statistics.mean(waits),2) if waits else None),
            "median_scheduled_wait_minutes":(
                round(statistics.median(waits),2) if waits else None),
            }


def paired(records,a,b):
    c=Counter()
    for r in records:
        x=r["results"][a]
        y=r["results"][b]
        c["start_cohort"]+=1
        if x["departure"] is None or y["departure"] is None:
            c["no_trip_in_pair"]+=1
            continue
        if x["departure"]==y["departure"]:
            c["same_departure"]+=1
            if x["proxy_hit"]!=y["proxy_hit"]:
                raise AssertionError("identical arrivals with inconsistent outcome")
        if x["proxy_hit"] is None or y["proxy_hit"] is None:
            c["one_or_both_unknown"]+=1
            continue
        c["paired_scorable"]+=1
        tag=("both_hit" if x["proxy_hit"] and y["proxy_hit"] else
             "a_only" if x["proxy_hit"] else
             "b_only" if y["proxy_hit"] else "both_miss")
        c[tag]+=1
    for field in (
        "paired_scorable","both_hit","both_miss","a_only","b_only",
        "same_departure","one_or_both_unknown","no_trip_in_pair"
    ):
        c.setdefault(field,0)
    n=c["paired_scorable"]
    return {**dict(sorted(c.items())),
            "scorable_a_success_fraction":(
                round((c["both_hit"]+c["a_only"])/n,4) if n else None),
            "scorable_b_success_fraction":(
                round((c["both_hit"]+c["b_only"])/n,4) if n else None),
            "paired_net_a_only_minus_b_only":c["a_only"]-c["b_only"],
            }


def audit(*,ledger=V75,stock=SOURCE,now=None,hours=24,
          keys=tuple(ITEMS.values()),limit=MAX_PROXY_EVENTS,
          scorer=poll_observation):
    if (not 1<=hours<=MAX_HOURS
        or not 1<=limit<=MAX_PROXY_EVENTS
        or not 1<=len(keys)<=len(ITEMS)
        or len(set(keys))!=len(keys)
        or not set(keys)<=set(ITEMS.values())):
        raise ValueError("invalid bounded replay options")
    asof=int(time.time() if now is None else now)
    if not 0<asof<=int(time.time())+300:
        raise ValueError("asof beyond permitted current timestamp")
    if str(ledger)==str(stock):
        raise ValueError("source and research ledger must differ")
    start=asof-hours*3600
    with closing(ro(ledger)) as db:
        raw,raw_count,invalid=select_candidates(
            db,start=start,end=asof,keys=keys,limit=limit)
        cohort=first_per_item_hour(raw)
        timeline,times,total_ticks=future_candidate_timelines(
            db,start=start,end=asof,keys=keys)
        decisions=[]
        for original in cohort:
            item=original["item_key"]
            fresh=first_actionable_tick(
                original,timeline[item],times[item],now=asof)
            stable=frozen_policy(
                original,timeline[item],times[item],asof=asof)
            if fresh["departure"] is not None and stable["departure"] is None:
                raise AssertionError("fresh option missing from combined policy")
            if (fresh["departure"] is not None
                and stable["departure"] is not None
                and stable["departure"]>fresh["departure"]
                and stable["basis"]=="fresh"):
                raise AssertionError("combined first fresh later than fresh-only")
            decisions.append((original,fresh,stable))
    records=[]
    with closing(ro(stock)) as observed:
        for original,fresh,stable in decisions:
            key=original["item_key"]
            country,item=key.split(":",1)
            issued=int(original["computed_at"])
            plan={
                "depart_now":("DEPART_NOW",issued),
                "fresh_5m":(fresh["status"],fresh["departure"]),
                "fresh_or_3stable":(stable["status"],stable["departure"]),
            }
            results={}
            for label,(status,departure) in plan.items():
                if departure is not None and not issued<=departure<=issued+MAX_WAIT:
                    raise AssertionError("selected plan beyond eight hour horizon")
                arrival=(None if departure is None
                         else departure+TRAVEL_SECONDS[country])
                proxy,status_proxy=_proxy(
                    scorer,observed,country,item,arrival,asof)
                results[label]={
                    "status":status,"departure":departure,
                    "arrival":arrival,"proxy_status":status_proxy,
                    "proxy_hit":proxy}
            records.append({
                "item_key":key,"family":original["model_family"],
                "start":issued,"initial_watch":int(original["departure"]),
                "stable_basis":stable["basis"],"stable_committed":stable["committed_issue"],
                "results":results,
            })
    by_item=defaultdict(list)
    by_family=defaultdict(list)
    for r in records:
        by_item[r["item_key"]].append(r)
        by_family[r["family"]].append(r)
    def group(rs):
        return {
            "starts":len(rs),
            "strategies":{label:summarize(rs,label) for label in LABELS},
            "fresh_vs_now":paired(rs,"fresh_5m","depart_now"),
            "stable_vs_now":paired(rs,"fresh_or_3stable","depart_now"),
            "stable_vs_fresh":paired(rs,"fresh_or_3stable","fresh_5m"),
        }
    return {
        "status":"V119_FIXED_ASOF_STABLE_COMMITMENT_VS_FRESH_REPLAY",
        "read_only":True,
        "research_only":True,
        "audit_asof_epoch":asof,
        "issued_window_hours":hours,
        "asof_frozen":now is not None,
        "target_items":list(keys),
        "raw_cohort_candidate_rows":raw_count,
        "valid_unique_arrivals":len(raw),
        "hourly_starts":len(records),
        "future_ticks_scanned":total_ticks,
        "predeclared_confirmation_ticks":CONFIRMATIONS,
        "max_confirmation_issue_gap_seconds":MAX_CONFIRM_ISSUE_GAP,
        "target_agreement_tolerance_seconds":CONFIRM_TARGET_TOLERANCE,
        "comparison_no_future_stock_used_for_choice":True,
        "commitment_not_currently_valid_under_5m_snapshot":True,
        "country_specific_provider_freshness_verified":False,
        "in_game_player_flights_observed":False,
        "repeated_hourly_starts_not_independent_restocks":True,
        "overall":group(records),
        "by_item":{k:group(rs) for k,rs in sorted(by_item.items())},
        "by_family":{k:group(rs) for k,rs in sorted(by_family.items())},
        "examples":[{
            "item":r["item_key"],"start":r["start"],
            "initial_watch_min":round((r["initial_watch"]-r["start"])/60,2),
            "committed_issue":r["stable_committed"],
            "stable_basis":r["stable_basis"],
            "outcomes":{label:{
                "status":r["results"][label]["status"],
                "wait_min":(round((r["results"][label]["departure"]-r["start"])/60,2)
                            if r["results"][label]["departure"] is not None else None),
                "stock_proxy":r["results"][label]["proxy_status"],
            } for label in LABELS}
        } for r in records[:6]],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asof",type=int,default=None)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--items",nargs="+",choices=tuple(ITEMS),default=["redfox","nessie"])
    p.add_argument("--limit",type=int,default=MAX_PROXY_EVENTS)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved collector path")
    result=audit(
        now=a.asof,hours=a.hours,
        keys=tuple(ITEMS[k] for k in dict.fromkeys(a.items)),
        limit=a.limit)
    if a.json:
        print(json.dumps(result,sort_keys=True))
        return
    print("===== V119 FROZEN 5M REPLAN VS 3-CONFIRMATION COMMITMENT =====")
    print("Frozen asof:",result["audit_asof_epoch"],
          "24h hours:",result["issued_window_hours"],
          "hourly starts:",result["hourly_starts"],
          "raw issue rows:",result["raw_cohort_candidate_rows"])
    for name,group in [("ALL",result["overall"]),*result["by_item"].items()]:
        print("==",name,"starting points",group["starts"],"==")
        for label,data in group["strategies"].items():
            print(" ",label,json.dumps(data,sort_keys=True))
        for pair in ("fresh_vs_now","stable_vs_now","stable_vs_fresh"):
            print(" ",pair,json.dumps(group[pair],sort_keys=True))
    print("Examples:",json.dumps(result["examples"][:3],sort_keys=True))
    print("UNCALIBRATED PROXY ONLY; DO NOT PROMOTE OR AUTOMATE.")


if __name__=="__main__":
    main()
