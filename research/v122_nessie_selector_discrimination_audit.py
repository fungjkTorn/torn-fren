"""V122 explain V121 nearpeak-vs-immediate collapse on the SAME frozen cohort.

No tuning, no new model; inspect the PREDECLARED V121 selectors.
For each mature first-V75-issue-per-UTC-hour Nessie start:
- recompute only existing V103 single-lag score curve / V106 decisions;
- prove which score values appear and whether alternatives depart together;
- only AFTER all decisions are fixed, classify UK stock-at-issue with
  V88 global poll-state proxy (not country-fresh) and arrival outcomes;
- separate cases where nearpeak departure == leave-now vs differs;
- enumerate ALL differing cases and paired outcome censoring;
- compare nearpeak and now separately when issue-time proxy says >=30,
  <30, or cannot be established.
One historical reference lag yields binary projected availability (0/1)
where known, NOT a calibrated posterior probability. Three risk budgets
may be mathematically redundant. Investigating a previously-inspected
holdout is NOT prospective confirmation.

No new predictions issued, no item purchases, no collector/API/service
actions, SQLite input read-only with original V75 candidate caps.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import (
    ResearchContext,TRAVEL_SECONDS,MAX_WAIT
)
from research.v103_champion_score_curves import score_curve
from research.v104_real_champion_earliest_replay import PILOTS,NESS_CONFIG
from research.v106_risk_budget_earliest_replay import DELTA_BUDGETS
from research.v121_nessie_native_vs_earliest_forward_proxy import (
    ITEM_KEY,_new_template,choose_all,evidence_only_after_selection,
    EVALUATION_MATURITY_SECONDS,WARMUP_SECONDS,
)
from research.v88_poll_state_forward_report import SOURCE,observation
from research.v76_forward_research_report import V75,ro,MAX_PROXY_EVENTS
from research.v116_attributed_hourly_forward_audit import (
    select_candidates,first_per_item_hour
)
from research.v60_private_snapshot_probe import approved_collector_source

REFERENCE_LAG_DAYS=tuple(NESS_CONFIG["lags"])
MAX_STARTS=30
LABELS=("nearpeak_0.03","nearpeak_0.08","nearpeak_0.15","floor_0.55")


def score_profile(curve):
    if curve is None:
        return {"sampled_points":0,"known_positive":0,"known_negative":0,
                "intermediate_probability_like_scores":0,
                "observed_score_values":[]}
    scores=[float(v) for v in curve["availability_score"]]
    if any(not 0<=v<=1 for v in scores):
        raise ValueError("nonsensical model score outside [0,1]")
    values=sorted(set(scores))
    return {
        "sampled_points":len(scores),
        "known_positive":sum(x==1 for x in scores),
        "known_negative":sum(x==0 for x in scores),
        "intermediate_probability_like_scores":
            sum(0<x<1 for x in scores),
        "observed_score_values":values[:20],
        "more_than_20_unique_scores":len(values)>20,
    }


def initial_status(proxy):
    if proxy=="POLL_STATE_PROXY_SUCCESS":return "STOCKED_AT_ISSUE_PROXY"
    if proxy=="POLL_STATE_PROXY_MISS":return "DEPLETED_AT_ISSUE_PROXY"
    return "UNKNOWN_AT_ISSUE_PROXY"


def summarize(records):
    c=Counter()
    for row in records:
        a=row["decisions"]["nearpeak_0.03"]
        b=row["decisions"]["now"]
        c["starts"]+=1
        c["nearpeak_departures"]+=int(a["departure"] is not None)
        c["immediate_departures"]+=int(b["departure"] is not None)
        if a["departure"] is None or b["departure"] is None:
            c["not_both_departing"]+=1
            continue
        if a["departure"]==b["departure"]:
            c["identical_departure"]+=1
        else:
            c["different_departure"]+=1
        if a["stocked"] is not None and b["stocked"] is not None:
            c["matched_scorable"]+=1
            if a["stocked"] and b["stocked"]:c["both_hit"]+=1
            elif a["stocked"]:c["nearpeak_only"]+=1
            elif b["stocked"]:c["immediate_only"]+=1
            else:c["both_miss"]+=1
        else:c["unknown_in_pair"]+=1
    return {name:c[name] for name in (
        "starts","nearpeak_departures","immediate_departures",
        "identical_departure","different_departure","not_both_departing",
        "matched_scorable","both_hit","both_miss",
        "nearpeak_only","immediate_only","unknown_in_pair"
    )}


def audit(*,ledger=V75,stock=SOURCE,now=None,hours=24,max_starts=25,
          model=None,choose=choose_all,scorer=observation,
          curve_at=score_curve):
    if (not 1<=hours<=24 or not 1<=max_starts<=MAX_STARTS
        or Path(ledger).resolve(strict=True)==Path(stock).resolve(strict=True)):
        raise ValueError("invalid bounded audit")
    asof=int(time.time() if now is None else now)
    if asof>time.time()+300:raise ValueError("future asof prohibited")
    with closing(ro(ledger)) as evidence:
        candidates,raw,invalid=select_candidates(
            evidence,start=asof-hours*3600,end=asof,
            keys=(ITEM_KEY,),limit=MAX_PROXY_EVENTS)
        cohort=first_per_item_hour(candidates)
        if len(cohort)>max_starts:
            raise ValueError("too many original hourly starts")
        mature=[
            r for r in cohort
            if int(r["computed_at"])+MAX_WAIT+TRAVEL_SECONDS["uni"]
            +EVALUATION_MATURITY_SECONDS<=asof
        ]
    ctx=None
    if model is None:
        ctx=ResearchContext.build(
            stock,targets=[PILOTS["nessie"]],readonly=True)
        planner=_new_template(ctx)
    else:planner=model
    rows=[]
    total=Counter()
    try:
        # All as-of scores and departure decisions must be collected
        # BEFORE any past/future observed stock is used for evaluation.
        choices=[]
        for r in mature:
            issue=int(r["computed_at"])
            if ctx is not None and issue-int(
                    ctx.timelines[PILOTS["nessie"]].ts[0])<WARMUP_SECONDS:
                raise ValueError("insufficient history warmup")
            profile=score_profile(curve_at(planner,issue))
            plans,ticks,queries=choose(issue,planner)
            choices.append((issue,profile,plans,ticks,queries))
            total["score_points"]+=profile["sampled_points"]
            total["score_positive"]+=profile["known_positive"]
            total["score_negative"]+=profile["known_negative"]
            total["score_intermediate"]+=profile[
                "intermediate_probability_like_scores"]
    finally:
        if ctx is not None:ctx.con.close()
    with closing(ro(stock)) as collector:
        for issue,profile,plans,ticks,queries in choices:
            outcomes=evidence_only_after_selection(
                collector,country="uni",item="Nessie Plushie",
                asof=asof,departures=plans,scorer=scorer)
            issue_label,_,_=scorer(
                collector,"uni","Nessie Plushie",issue,asof)
            rows.append({
                "issue_epoch":issue,
                "issue_proxy_status":issue_label,
                "initial_stock_proxy_category":initial_status(issue_label),
                "score_profile":profile,
                "replanning_ticks":ticks,
                "replanning_score_queries":queries,
                "all_three_nearpeak_departures_identical":len({
                    plans.get(label) for label in LABELS[:3]
                })==1,
                "decisions":outcomes,
            })
    strata=defaultdict(list)
    for r in rows:strata[r["initial_stock_proxy_category"]].append(r)
    differences=[r for r in rows
                 if r["decisions"]["nearpeak_0.03"]["departure"] !=
                    r["decisions"]["now"]["departure"]]
    return {
        "status":"V122_NESSIE_SELECTOR_DISCRIMINATION_VS_IMMEDIATE",
        "asof_epoch":asof,
        "read_only":True,
        "unchanged_v121_first_hour_starts":len(cohort),
        "mature_eight_hour_starts":len(mature),
        "pending_unmatured_starts":len(cohort)-len(mature),
        "original_v75_valid_unique_arrivals":len(candidates),
        "model_lag_days":list(REFERENCE_LAG_DAYS),
        "model_score_is_calibrated_probability":False,
        "score_curve_points":dict(total),
        "overall":summarize(rows),
        "by_stock_state_at_issue":{
            k:summarize(v) for k,v in sorted(strata.items())},
        "three_nearpeak_variants_identical_starts":sum(
            r["all_three_nearpeak_departures_identical"] for r in rows),
        "all_different_departure_examples":[{
            "issue_epoch":r["issue_epoch"],
            "issue_stock_proxy":r["issue_proxy_status"],
            "initial_score_values":
                r["score_profile"]["observed_score_values"],
            "champion_departure":r["decisions"]["champion"]["departure"],
            "nearpeak_departure":r["decisions"]["nearpeak_0.03"]["departure"],
            "immediate_departure":r["decisions"]["now"]["departure"],
            "nearpeak_outcome":r["decisions"]["nearpeak_0.03"]["proxy_status"],
            "immediate_outcome":r["decisions"]["now"]["proxy_status"],
        } for r in differences],
        "same_stock_source_country_update_epoch_verified":False,
        "actual_player_flight_success_verified":False,
        "known_prior_holdout_not_new_forward_validation":True,
        "candidate_choices_precede_any_outcome_reads":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--asof",type=int,default=None)
    p.add_argument("--hours",type=int,default=24)
    p.add_argument("--max-starts",type=int,default=25)
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("Unapproved collector source")
    r=audit(now=args.asof,hours=args.hours,max_starts=args.max_starts)
    if args.json:print(json.dumps(r,sort_keys=True));return
    print("===== V122 NESSIE SELECTOR DISCRIMINATION AUDIT =====")
    print("Cohort",r["unchanged_v121_first_hour_starts"],
          "mature",r["mature_eight_hour_starts"],
          "unmature",r["pending_unmatured_starts"])
    print("Score curve:",json.dumps(r["score_curve_points"],sort_keys=True))
    print("Overall:",json.dumps(r["overall"],sort_keys=True))
    print("Nearpeak identical across three thresholds:",
          r["three_nearpeak_variants_identical_starts"])
    print("Initial stock strata:")
    for k,v in r["by_stock_state_at_issue"].items():
        print(" ",k,json.dumps(v,sort_keys=True))
    print("EVERY different-from-immediate departure:",
          json.dumps(r["all_different_departure_examples"],sort_keys=True))
    print("NO MODEL OR LIVE SERVICE CHANGE; previously seen proxy only.")


if __name__=="__main__":
    main()
