"""V121 historical-as-of Nessie selector replay against V88 forward arrival evidence.

Do NOT introduce a new untested departure heuristic. Reuse:
  V103 the exact incumbent TemplatePlanner arrival score curve,
  V106 predeclared risk budgets .03/.08/.15, floor .55, 2 contiguous points,
  V106 five-minute dynamic expiry/withdrawal logic,
  V88 heartbeat-bracketed arrival proxy (unknown stays unknown).

Start at the first VALID research issue per item UTC hour in frozen V75.
Select departures using independent recomputation from historical stock
context only, allowing five-minute updating over the original 8h horizon.
The template planner's q-based reference dates (q-1 day +/-1h)
must remain BEFORE q. Historical collector DB includes later rows only
to score AFTER the policy has finished choosing its departures. Reject
inadequate starting-history warmup and unknown stock before issue.

This is NOT actually as-issued FROZEN V75 model output. V75 records one
candidate/issue, not full alternative score curves. This reconstructs
the earlier proposals *after the fact* using an expanded historical
change-only database. Backfilled items, source switches and collector
gaps can create differences. Comparison is exploratory, not a new
prospective lockbox; optional initial-V75-plan drift diagnostic is shown
without treating reconstructed times as exactly identical.

Per-start and paired metrics must retain the 25 started decisions,
abstentions, proxy unknowns, misses, and wait distribution. We do not
promote a policy from conditional hit rate alone.

Two SQLite sources opened read-only; no API, game automation, website,
collector, production model, or service changes. Raw score is NOT a
calibrated success probability or exact restock/depletion timestamp.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import (
    ResearchContext,TemplatePlanner,TRAVEL_SECONDS,
    MAX_WAIT,STEP,DAY
)
from research.v103_champion_score_curves import score_curve
from research.v104_real_champion_earliest_replay import (
    NESS_CONFIG,PILOTS
)
from research.v106_risk_budget_earliest_replay import (
    simulate_one,DELTA_BUDGETS,ABSOLUTE_FLOOR,CONTIGUOUS_POINTS
)
from research.v88_poll_state_forward_report import (
    SOURCE,observation
)
from research.v76_forward_research_report import V75,ro,MAX_PROXY_EVENTS
from research.v116_attributed_hourly_forward_audit import (
    select_candidates,first_per_item_hour
)
from research.v115_targeted_v88_forward_evidence import ITEMS
from research.v60_private_snapshot_probe import approved_collector_source

ITEM_KEY=ITEMS["nessie"]
LABELS=(
    "champion",
    "nearpeak_0.03",
    "nearpeak_0.08",
    "nearpeak_0.15",
    "floor_0.55",
    "now",
)
EVALUATION_MATURITY_SECONDS=190
WARMUP_SECONDS=8*DAY
MAX_STARTS=30


def _past_only_template(planner,q):
    """The champion's reference lookups must not depend on future states.

    As-of q, a reference to the previous day shifted by +/-1h is
    strictly older than q, even for arrival horizon MAX_WAIT+travel.
    """
    latest_reference = (
        q + TRAVEL_SECONDS["uni"] + MAX_WAIT
        - DAY + NESS_CONFIG["shift_h"] * 3600
    )
    return latest_reference<q


def _new_template(ctx):
    country,item=PILOTS["nessie"]
    return TemplatePlanner(
        ctx,country,item,
        lags=NESS_CONFIG["lags"],
        lookback=NESS_CONFIG["lookback_h"]*3600,
        shift_range=NESS_CONFIG["shift_h"]*3600,
        minfit=NESS_CONFIG["minfit"],
    )


def choose_all(start,planner,*,curve_fn=score_curve):
    """Causal policy choices first; no stock outcomes accessed here."""
    if not _past_only_template(planner,int(start)):
        raise AssertionError("template lookback can reach into asof future")
    cache={}
    def curve(q):
        if not _past_only_template(planner,int(q)):
            raise AssertionError("future asof reference date")
        if q not in cache:
            cache[q]=curve_fn(planner,q)
        return cache[q]
    departures,ticks=simulate_one(
        start,planner,curve,LABELS)
    if ticks>MAX_WAIT//STEP+1:
        raise AssertionError("unbounded five-minute replay")
    for label,dep in departures.items():
        if dep is not None and not start<=dep<=start+MAX_WAIT:
            raise AssertionError("departure beyond initial eight-hour horizon")
    return departures,ticks,len(cache)


def evidence_only_after_selection(conn,*,country,item,asof,departures,
                                  scorer=observation):
    """No proxy read before ALL policies have selected departures."""
    result={}
    arrival_cache={}
    for label,dep in departures.items():
        if dep is None:
            result[label]={
                "departure":None,"proxy_status":"NO_DEPARTURE",
                "stocked":None,
            }
        else:
            arrival=int(dep)+TRAVEL_SECONDS[country]
            if arrival+EVALUATION_MATURITY_SECONDS>asof:
                status,hit="PENDING_ARRIVAL",None
            else:
                if arrival not in arrival_cache:
                    status,hit,_=scorer(conn,country,item,arrival,asof)
                    arrival_cache[arrival]=(status,hit)
                status,hit=arrival_cache[arrival]
            result[label]={
                "departure":int(dep),
                "arrival":arrival,
                "proxy_status":status,
                "stocked":hit,
            }
    return result


def paired(recs,left,right):
    c=Counter()
    for r in recs:
        a=r["results"][left]
        b=r["results"][right]
        c["starts"]+=1
        if a["departure"] is None or b["departure"] is None:
            c["no_departure_in_pair"]+=1
            continue
        if a["departure"]==b["departure"]:
            c["identical_departure"]+=1
            if a["stocked"]!=b["stocked"]:
                raise AssertionError("same arrival has contradictory outcome")
        if a["stocked"] is None or b["stocked"] is None:
            c["unknown_stock_in_pair"]+=1
            continue
        c["both_scorable"]+=1
        if a["stocked"] and b["stocked"]:
            c["both_hit"]+=1
        elif a["stocked"]:
            c["left_only_hit"]+=1
        elif b["stocked"]:
            c["right_only_hit"]+=1
        else:
            c["both_miss"]+=1
    return {
        "starts":c["starts"],
        "both_scorable":c["both_scorable"],
        "no_departure_in_pair":c["no_departure_in_pair"],
        "unknown_stock_in_pair":c["unknown_stock_in_pair"],
        "same_departure":c["identical_departure"],
        "both_hit":c["both_hit"],"both_miss":c["both_miss"],
        "left_only_hit":c["left_only_hit"],
        "right_only_hit":c["right_only_hit"],
        "left_minus_right_known_discordant":(
            c["left_only_hit"]-c["right_only_hit"]
        ),
    }


def summarize(recs,label):
    c=Counter()
    waits=[]
    for r in recs:
        c["starts"]+=1
        rec=r["results"][label]
        dep=rec["departure"]
        if dep is None:
            c["no_departure"]+=1
            continue
        c["departures"]+=1
        waits.append((dep-r["start"])/60)
        if rec["stocked"] is True:c["scorable_hits"]+=1
        elif rec["stocked"] is False:c["scorable_misses"]+=1
        else:c["unscorable_departures"]+=1
        if rec["proxy_status"]=="PENDING_ARRIVAL":
            c["arrivals_pending"]+=1
    n=c["starts"]
    known=c["scorable_hits"]+c["scorable_misses"]
    return {
        "starts":n,"departures":c["departures"],
        "no_departure":c["no_departure"],
        "scorable_hits":c["scorable_hits"],
        "scorable_misses":c["scorable_misses"],
        "unscorable_departures":c["unscorable_departures"],
        "arrivals_pending":c["arrivals_pending"],
        "coverage":round(c["departures"]/n,4) if n else None,
        "proxy_hits_per_all_starts_lower_bound":round(
            c["scorable_hits"]/n,4) if n else None,
        "proxy_hit_rate_when_scorable":round(
            c["scorable_hits"]/known,4) if known else None,
        "mean_wait_minutes":round(statistics.mean(waits),2)
                           if waits else None,
        "median_wait_minutes":round(statistics.median(waits),2)
                           if waits else None,
    }


def report(records):
    items={label:summarize(records,label) for label in LABELS}
    comparisons={
        f"{label}_vs_champion":paired(records,label,"champion")
        for label in LABELS if label!="champion"
    }
    comparisons.update({
        f"{label}_vs_now":paired(records,label,"now")
        for label in LABELS if label not in ("now","champion")
    })
    return {"policy_outcomes":items,"paired":comparisons}


def audit(*,ledger=V75,stock=SOURCE,now=None,hours=24,
          max_starts=25,scorer=observation,
          model=None,choose=choose_all):
    if (not 1<=hours<=24 or not 1<=max_starts<=MAX_STARTS
        or Path(ledger).resolve(strict=True)==Path(stock).resolve(strict=True)):
        raise ValueError("invalid audit request")
    asof=int(time.time() if now is None else now)
    if asof>time.time()+300:
        raise ValueError("cannot inspect future observations")
    start_window=asof-hours*3600
    with closing(ro(ledger)) as records:
        candidates,raw,invalid=select_candidates(
            records,start=start_window,end=asof,
            keys=(ITEM_KEY,),limit=MAX_PROXY_EVENTS)
        cohort=first_per_item_hour(candidates)
        if len(cohort)>max_starts:
            raise ValueError("too many first-per-hour starts for replay")
        # We cannot simulate a 5-minute update that had not yet occurred
        # by frozen asof. Evaluate ONLY starts with a complete 8h decision
        # horizon and 106m arrival/maturity window. Everything else is
        # reported as pending, not counted as zero-hit abstentions.
        complete=[
            row for row in cohort
            if int(row["computed_at"]) + MAX_WAIT
               + TRAVEL_SECONDS["uni"]
               + EVALUATION_MATURITY_SECONDS <= asof
        ]
        pending=len(cohort)-len(complete)
    with closing(ro(stock)) as source:
        # Source chronology is full history for scoring; only past
        # reference dates enter actual TemplatePlanner.plan/score_curve.
        if model is None:
            ctx=ResearchContext.build(
                stock,targets=[PILOTS["nessie"]],readonly=True)
            owns_context=True
            planner=_new_template(ctx)
        else:
            ctx=None
            owns_context=False
            planner=model
        try:
            out=[]
            count_queries=0
            for initial in complete:
                start=int(initial["computed_at"])
                if model is None:
                    first_history=int(ctx.timelines[PILOTS["nessie"]].ts[0])
                    if start-first_history<WARMUP_SECONDS:
                        raise ValueError("start lacks eight days of stock warmup")
                selected,ticks,queries=choose(start,planner)
                count_queries+=queries
                stock_evidence=evidence_only_after_selection(
                    source,country="uni",item="Nessie Plushie",
                    asof=asof,departures=selected,scorer=scorer)
                out.append({
                    "start":start,"item_key":ITEM_KEY,
                    "frozen_v75_family":initial["model_family"],
                    "original_v75_candidate":int(initial["departure"]),
                    "recomputed_native_first_plan":(
                        selected.get("champion")
                    ),
                    "model_tick_queries":ticks,
                    "results":stock_evidence,
                })
        finally:
            if owns_context:ctx.con.close()
    result=report(out)
    drifts=[
        (r["recomputed_native_first_plan"]-r["original_v75_candidate"])/60
        for r in out if r["recomputed_native_first_plan"] is not None
    ]
    return {
        "status":"V121_NESSIE_NATIVE_EARLIEST_SCORE_FORWARD_PROXY_REPLAY",
        "read_only":True,
        "target_item_key":ITEM_KEY,
        "cutoff_epoch":asof,
        "issued_window_hours":hours,
        "frozen_v75_hourly_start_cohort":len(cohort),
        "complete_eight_hour_replay_starts":len(out),
        "starts_pending_complete_eight_hour_horizon":pending,
        "original_v75_model_family_counts":dict(Counter(
            r["frozen_v75_family"] for r in out)),
        "raw_v75_rows":raw,
        "valid_unique_v75_arrival_targets":len(candidates),
        "recomputed_not_frozen_original_v75_predictions":True,
        "reconstruction_original_v75_candidate_vs_dynamic_native_NOT_PARITY":True,
        "recomputed_native_dynamic_minus_initial_frozen_v75_departure_median_minutes":(
            round(statistics.median(drifts),2) if drifts else None),
        "stock_observations_only_after_selection":True,
        "future_reference_stock_access_for_selection":False,
        "total_dynamic_tick_iterations":sum(r["model_tick_queries"] for r in out),
        "total_unique_model_score_queries":count_queries,
        "score_floors_uncalibrated":True,
        "champion_source_unchanged":True,
        "stock_source_provider_country_age_verified":False,
        "actual_game_flights_or_purchases_verified":False,
        "historical_holdout_previously_inspected":True,
        "independent_restock_events_claimed":False,
        "predeclared_budget_variants":list(DELTA_BUDGETS),
        "absolute_raw_score_floor":ABSOLUTE_FLOOR,
        "minimum_contiguous_score_points":CONTIGUOUS_POINTS,
        **result,
        "sample":[{
            "asof":r["start"],
            "original_v75_watch_departure":r["original_v75_candidate"],
            "dynamic_recomputed_champion_departure":r["recomputed_native_first_plan"],
            "decisions":{label:{
                "departure":entry["departure"],
                "stock_proxy":entry["proxy_status"],
            } for label,entry in r["results"].items()}
        } for r in out[:3]],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asof",type=int,default=None)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--max-starts",type=int,default=25)
    p.add_argument("--json",action="store_true")
    a=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved historical stock source")
    result=audit(now=a.asof,hours=a.hours,max_starts=a.max_starts)
    if a.json:
        print(json.dumps(result,sort_keys=True))
        return
    print("===== V121 NESSIE NATIVE MIDPOINT VS EARLIEST-NEARPEAK SELECTOR =====")
    print("Research reconstruction from historical asof; NOT frozen V75 alternatives")
    print("cohort:",result["frozen_v75_hourly_start_cohort"],
          "matured:",result["complete_eight_hour_replay_starts"],
          "pending_horizon:",result["starts_pending_complete_eight_hour_horizon"],
          "curve queries:",result["total_unique_model_score_queries"],
          "valid initial V75 arrivals:",result["valid_unique_v75_arrival_targets"])
    for name,data in result["policy_outcomes"].items():
        print(" ",name,json.dumps(data,sort_keys=True))
    for name,data in result["paired"].items():
        print(" ",name,json.dumps(data,sort_keys=True))
    print("initial V75 vs replay dynamic drift:",
          result["recomputed_native_dynamic_minus_initial_frozen_v75_departure_median_minutes"])
    print("example:",json.dumps(result["sample"][:1],sort_keys=True))
    print("CAUTION: overlapping restocks, previously inspected window,"
          " incomplete upstream country freshness, no player confirmations.")


if __name__=="__main__":
    main()
