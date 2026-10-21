"""V113 event-offset research: find genuinely DIFFERENT restock-based flights.

V112 selected only the observed instant each item dropped below quantity 30.
On those depletion starts V107 always said leave NOW, so 25 model departures
and 25 immediate departures were IDENTICAL (zero added decision value).

Instead issue research forecasts at prespecified offsets after distinct raw
threshold transition events: 0, +5, +15, +30 minutes, for both STOCKED and
DEPLETED phases. Apply exactly the SAME forecast function as V112. At each
as-of, select one counterfactual departure and compare against NOW using the
same same-source two-sided 15m stock evidence. Both departure choices arise
from the SAME as-of; only future observations score the outcomes.

Group results by original event phase, fixed offset, observed issue stock,
and whether the model actually DELAYED departure. Report the changed-policy
subset separately: identical departures cannot add value. Each anchor is
reissued at several offsets, so cohorts are correlated, NOT independent
new restocks. This is a coverage/decision diagnostic on seen historical data,
not an out-of-sample validation or a player-flight accuracy estimate.

No production source, collector, website, key, job or database modifications.
Only approved stock_history SQLite accessed read-only; all other logic pure.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import MAX_WAIT,TRAVEL_SECONDS
from research.v107_explicit_restock_cycle_baseline import next_windows
from research.v109_raw_restock_transition_event_audit import (
    MIN_HISTORY_DAYS,HOLDOUT_FRACTION,TARGETS,SOURCE,
    read_collector_item,transition_episodes
)
from research.v111_arrival_proxy_evidence_audit import (
    arrival_evidence,known_gap
)
from research.v112_matched_immediate_vs_restock_flight_audit import (
    paired_summary,state
)
from research.v60_private_snapshot_probe import approved_collector_source

OFFSETS_MINUTES=(0,5,15,30)
MAX_ANCHORS_PER_PHASE=25
MAX_OBSERVATION_AGE=7200


def prespecified_anchors(obs,episodes,phase,max_per_phase):
    """No restock success, forecast, or model waits enter cohort selection."""
    if not obs or phase not in ("STOCKED","DEPLETED"):
        return []
    first=obs[0].epoch
    cutoff=first+int(
        (obs[-1].epoch-first)*(1-HOLDOUT_FRACTION))
    found=[e for e in episodes if e["phase"]==phase
           and e["issue"]>=cutoff
           and e["issue"]>=first+MIN_HISTORY_DAYS*86400]
    if len(found)>max_per_phase:
        idx=[int(i*(len(found)-1)/(max_per_phase-1))
             for i in range(max_per_phase)] if max_per_phase>1 else [
                len(found)//2]
        found=[found[i] for i in sorted(set(idx))]
    return found


def choose_departure(windows,issued_at):
    """Original research V107 earliest expected and 8h issue horizon."""
    options=[
        (int(w["earliest_expected_departure"]),i+1)
        for i,w in enumerate(windows)
        if w["earliest_expected_departure"] is not None
        and issued_at<=int(w["earliest_expected_departure"])
                         <=issued_at+MAX_WAIT
    ]
    return min(options) if options else None


def one_decision(obs,epochs,gaps,*,issued_at,item_key,
                 predictor=next_windows,scorer=arrival_evidence):
    at=bisect.bisect_right(epochs,issued_at)
    if not at:
        return None,"NO_PRIOR_ROW"
    known=obs[at-1]
    if issued_at-known.epoch>MAX_OBSERVATION_AGE:
        return None,"NO_RECENT_STOCK_OBSERVATION"
    if known_gap(gaps,known.epoch,issued_at):
        return None,"COLLECTOR_GAP_SINCE_OBSERVATION"
    history=obs[:at]
    if history[-1].epoch>issued_at:
        raise AssertionError("V113 model received future stock observations")
    prediction=predictor(
        item_key,history,asof=issued_at,collection_gaps=gaps)
    choice=choose_departure(prediction.get("windows",[]),issued_at)
    departure=None if choice is None else choice[0]
    flight=TRAVEL_SECONDS[item_key.split(":",1)[0]]
    now_ev=scorer(obs,epochs,gaps,issued_at+flight)
    model_ev=(None if departure is None else scorer(
        obs,epochs,gaps,departure+flight))
    record={
        "issue":issued_at,"departure":departure,
        "now_evidence":now_ev,"model_evidence":model_ev,
        "state_asof":"AT_LEAST_30" if known.quantity>=30 else "BELOW_30",
        "stock_row_age":issued_at-known.epoch,
        "plan_status":prediction.get("status","UNKNOWN"),
        "selected_hop":None if choice is None else choice[1],
    }
    return record,None


def analyze_item(obs,gaps,*,item_key,max_per_phase=12,
                 predictor=next_windows,scorer=arrival_evidence):
    if not 1<=max_per_phase<=MAX_ANCHORS_PER_PHASE:
        raise ValueError("invalid phase-anchored episode cap")
    episodes,rejected=transition_episodes(obs,gaps)
    epochs=[r.epoch for r in obs]
    output={}
    all_records=[]
    problems=Counter()
    for phase in ("DEPLETED","STOCKED"):
        anchors=prespecified_anchors(
            obs,episodes,phase,max_per_phase)
        groups={}
        for offset_m in OFFSETS_MINUTES:
            records=[]
            outcomes=Counter()
            for ep in anchors:
                issued_at=int(ep["issue"])+offset_m*60
                result,reason=one_decision(
                    obs,epochs,gaps,issued_at=issued_at,
                    item_key=item_key,predictor=predictor,scorer=scorer)
                if result is None:
                    outcomes[reason]+=1
                    problems[reason]+=1
                    continue
                result["anchor_phase"]=phase
                result["anchor_event_issue"]=ep["issue"]
                result["offset_minutes"]=offset_m
                records.append(result)
                all_records.append(result)

            changed=[r for r in records if r["departure"] is not None
                     and r["departure"]>r["issue"]]
            same=[r for r in records if r["departure"]==r["issue"]]
            absent=[r for r in records if r["departure"] is None]
            current={
                "AT_LEAST_30":sum(r["state_asof"]=="AT_LEAST_30"
                                 for r in records),
                "BELOW_30":sum(r["state_asof"]=="BELOW_30"
                              for r in records)
            }
            groups[str(offset_m)]={
                "selected_distinct_anchor_events":len(anchors),
                "eligible_decision_issues":len(records),
                "issue_state":current,
                "ineligible_issues":dict(outcomes),
                "same_as_now":len(same),
                "model_delayed":len(changed),
                "model_abstained":len(absent),
                "all_matched_proxy":paired_summary(records),
                "DELAYED_ONLY_matched_proxy":paired_summary(changed),
                "illustrative_different_choices":[{
                    "issue_epoch":r["issue"],
                    "model_wait_m":round(
                        (r["departure"]-r["issue"])/60,2),
                    "current_stock_state":r["state_asof"],
                    "target_restocks_ahead":r["selected_hop"],
                    "model_proxy":state(r["model_evidence"][
                        "strict_bracket_proxy"]),
                    "now_proxy":state(r["now_evidence"][
                        "strict_bracket_proxy"]),
                } for r in changed[:3]]
            }
        output[phase]=groups

    return {
        "item_key":item_key,
        "raw_stock_rows":len(obs),
        "completed_source_continuous_phase_records":len(episodes),
        "excluded_phase_records":dict(rejected),
        "fixed_issue_offsets_minutes":list(OFFSETS_MINUTES),
        "anchor_correlation_across_offsets":True,
        "all_offset_issue_counts_not_independent":len(all_records),
        "ineligible_issues":dict(problems),
        "phases":output,
        "raw_provider_freshness_verified":False,
        "real_player_flights_verified":False,
        "future_rows_used_for_prediction":False,
    }


def pretty(out):
    print("===== V113 FIXED-OFFSET EVENT-BASED DECISIONS: DELAY VS NOW =====")
    print("Each historical phase is sampled repeatedly at predeclared offsets.")
    for name,item in out["items"].items():
        print("==",name,item["item_key"],"==")
        for phase,groups in item["phases"].items():
            print("---- Original observed event:",phase,"----")
            for offset,group in groups.items():
                delay=group["DELAYED_ONLY_matched_proxy"]
                print(
                    f'offset=+{offset:>2}m anchors={group["selected_distinct_anchor_events"]}'
                    f' issues={group["eligible_decision_issues"]}'
                    f' known_above30={group["issue_state"]["AT_LEAST_30"]}'
                    f' same_as_now={group["same_as_now"]}'
                    f' DELAYED={group["model_delayed"]}'
                    f' abstained={group["model_abstained"]}')
                print("  delayed-policy two-sided evidence: model=",
                      json.dumps(delay["model"],sort_keys=True),
                      " now=",json.dumps(delay["depart_now"],sort_keys=True))
                print("  delayed-only matched difference bounds:",
                      json.dumps(delay[
                         "possible_delta_success_per_anchor_bounds"],sort_keys=True))
                if group["illustrative_different_choices"]:
                    print("  delayed example:",
                          json.dumps(
                              group["illustrative_different_choices"][:1],
                              sort_keys=True))
    print("Historical collector only: no verified player flights, no calibrations.")


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target",choices=["redfox","nessie","both"],
                    default="both")
    ap.add_argument("--events-per-phase",type=int,default=12)
    ap.add_argument("--json",action="store_true")
    a=ap.parse_args()
    if not 1<=a.events_per_phase<=MAX_ANCHORS_PER_PHASE:
        ap.error("events per phase must be 1..25")
    if not approved_collector_source(SOURCE):
        raise SystemExit("unapproved historical stock source")
    targets=(TARGETS if a.target=="both"
             else {a.target:TARGETS[a.target]})
    started=time.monotonic()
    with closing(sqlite3.connect(
        Path(SOURCE).resolve(strict=True).as_uri()+"?mode=ro",
        uri=True,timeout=15)) as con:
        con.execute("PRAGMA query_only=ON")
        result={}
        for name,(country,item) in targets.items():
            obs,gaps=read_collector_item(con,country,item)
            result[name]=analyze_item(
                obs,gaps,item_key=f"{country}:{item}",
                max_per_phase=a.events_per_phase)
    report={
        "status":"V113_PHASE_OFFSET_DELAY_DISCRIMINATION_AUDIT",
        "read_only":True,"live_changes":False,
        "predeclared_offsets_minutes":list(OFFSETS_MINUTES),
        "independent_restock_events_claimed":False,
        "holdout_unseen":False,
        "provider_freshness_verified":False,
        "elapsed_seconds":round(time.monotonic()-started,2),
        "items":result
    }
    if a.json:
        print(json.dumps(report,sort_keys=True))
    else:
        pretty(report)
        print("elapsed_seconds:",report["elapsed_seconds"])


if __name__=="__main__":
    main()
