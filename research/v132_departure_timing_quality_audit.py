"""V132: WHAT DOES 'TIME TO LEAVE' ACTUALLY MEAN for frozen V128?

A frozen, read-only, evidence-quality report. Evaluate 24-item V128 decisions
at issuance and the critical operational question: did distant *watch* times
converge into a fresh 5-minute ready departure at their planned time?
Report real choice coverage, abstentions, time-to-depart, last observed-source
transitions, recommendation churn, and whether near-departure confirmation
exists. Never call a mere future watch an executed or successful flight.

This does NOT replace the original website's prediction_v2_live output.
Prediction V2 offers next restock / lifetime / departure window, while V128
offers *earliest simulated stocked ARRIVAL*, not an inferred specific restock
window or independently calibrated probability. Do not convert 0.6
simulation threshold into an actual 60% success rate.

A GLOBAL poll heartbeat cannot prove that each country's provider stock is
fresh. No stock-buys or player-travel logs are available in this research DB.
V129 separately scores observed arrival stock >=30 after predicted landings.
No DB writes, API calls, gameplay actions, timer or website changes.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

from research.v128_full24_earliest_shadow import (
    GENERATION,SIDECAR,ROSTER,exact_roster
)
from research.v129_full24_forward_report import (
    ro,_parse,choose_hourly_starts,reconfirm
)

MAX_DAYS=3
MAX_ROWS=40000
MAX_SHIFTS=5
VALID_SECONDS=300
FAR_WATCH_SECONDS=300
NO_NEW_OBS_MAX_SECONDS=600


def shifted_departure(a,b):
    """Absolute forecast drift beyond the five-minute snapshot interval."""
    x=a.get("earliest_departure")
    y=b.get("earliest_departure")
    return abs(int(y)-int(x)) if x is not None and y is not None else None


def same_observed_stock(a,b):
    """Equal latest change-only collector evidence, NOT certified live truth."""
    return (
        a.get("last_stock_change_epoch") is not None
        and a.get("last_stock_change_epoch")==b.get("last_stock_change_epoch")
        and a.get("collector_source")==b.get("collector_source")
        and a.get("phase_onset")==b.get("phase_onset")
        and a.get("phase")==b.get("phase")
        and a.get("last_stock_quantity")==b.get("last_stock_quantity")
    )


def one_item(rows,*,asof):
    counts=Counter()
    status=Counter()
    recent=[]
    rows=sorted(rows,key=lambda r:r["issued_epoch"])
    for r in rows:
        counts["issued_snapshots"]+=1
        dep=r.get("earliest_departure")
        status[r["decision_status"]]+=1
        if dep is None:
            counts["abstention_or_no_supported_window"]+=1
            continue
        wait=dep-r["issued_epoch"]
        if wait<0 or wait>28800:
            raise ValueError("invalid departure delay")
        counts["issued_with_departure"]+=1
        if wait==0:counts["leave_now"]+=1
        elif wait<=FAR_WATCH_SECONDS:counts["ready_within_5min"]+=1
        else:counts["future_watch_more_than_5min"]+=1
        recent.append(wait/60)
    pairs=0
    unchanged=0
    same_model_both=0
    shifted5=0
    shifted15=0
    abs_moves=[]
    examples=[]
    for a,b in zip(rows,rows[1:]):
        if not 0<b["issued_epoch"]-a["issued_epoch"]<=NO_NEW_OBS_MAX_SECONDS:
            continue
        pairs+=1
        if not same_observed_stock(a,b):
            continue
        unchanged+=1
        shift=shifted_departure(a,b)
        if shift is None:continue
        same_model_both+=1
        abs_moves.append(shift/60)
        if shift>300:shifted5+=1
        if shift>900:
            shifted15+=1
            if len(examples)<MAX_SHIFTS:
                examples.append({
                    "first_issue":a["issued_epoch"],
                    "next_issue":b["issued_epoch"],
                    "same_observed_stock_change_epoch":
                        a["last_stock_change_epoch"],
                    "old_departure":a["earliest_departure"],
                    "new_departure":b["earliest_departure"],
                    "absolute_shift_minutes":round(shift/60,2),
                    "country_provider_update_freshness_verified":False,
                })
    starts=choose_hourly_starts(rows)
    check=Counter()
    matured=Counter()
    for start in starts:
        dep=start["earliest_departure"]
        if dep is None:
            check["hourly_start_abstained"]+=1
            continue
        label=reconfirm(start,rows)
        check[label]+=1
        if start["earliest_arrival"]+190<=asof:
            matured["matured_issued_arrivals"]+=1
            matured["matured_original_watch_needing_reconfirm"]+=int(
                dep-start["issued_epoch"]>300)
            if (dep-start["issued_epoch"]>300 and
                label=="RECONFIRMED_FRESH_NEAR_DEPARTURE"):
                matured["matured_watch_properly_reconfirmed"]+=1
        else:
            matured["arrival_not_yet_matured"]+=1

    result={
        "issued_five_minute_snapshots":counts["issued_snapshots"],
        "issued_proposals":counts["issued_with_departure"],
        "issued_leave_now":counts["leave_now"],
        "issued_ready_in_5min":counts["ready_within_5min"],
        "issued_future_watches_not_executable":counts[
            "future_watch_more_than_5min"],
        "issued_abstentions_or_no_supported_window":counts[
            "abstention_or_no_supported_window"],
        "issued_proposal_rate":round(
            counts["issued_with_departure"]/counts["issued_snapshots"],4)
            if counts["issued_snapshots"] else None,
        "mean_proposed_wait_minutes":round(
            statistics.mean(recent),2) if recent else None,
        "median_proposed_wait_minutes":round(
            statistics.median(recent),2) if recent else None,
        "status_counts":dict(sorted(status.items())),
        "adjacent_issued_pairs_within_10min":pairs,
        "unchanged_collector_observed_state_pairs":unchanged,
        "unchanged_collector_state_pairs_with_two_departures":same_model_both,
        "same_observed_state_absolute_departure_shift_gt_5min":shifted5,
        "same_observed_state_absolute_departure_shift_gt_15min":shifted15,
        "median_absolute_departure_shift_same_obs_minutes":round(
            statistics.median(abs_moves),2) if abs_moves else None,
        "examples_of_shift_over_15min_same_collector_state":examples,
        "first_issued_item_UTC_hours":len(starts),
        "reconfirmation_counts_for_first_hour_proposals":
            dict(sorted(check.items())),
        "maturity_counts_for_first_hour_proposals":
            dict(sorted(matured.items())),
    }
    return result


def audit(*,ledger=SIDECAR,roster=ROSTER,now=None,days=2,
          limit=MAX_ROWS):
    if not (1<=days<=MAX_DAYS and 1<=limit<=MAX_ROWS):
        raise ValueError("invalid bounded time-to-leave study")
    original=exact_roster(roster)
    asof=int(time.time() if now is None else now)
    with closing(ro(ledger)) as db:
        raw=db.execute(
            """SELECT item_key,issued_epoch,payload_json FROM v128_issued
               WHERE issued_epoch>=? AND issued_epoch<=?
                 AND policy_id=?
               ORDER BY issued_epoch,item_key LIMIT ?""",
            (asof-days*86400,asof,GENERATION,limit+1)).fetchall()
    if len(raw)>limit:
        raise ValueError("too many raw as-issued model decisions")
    valid,invalid=_parse(raw,original)
    bykey=defaultdict(list)
    for r in valid:bykey[r["item_key"]].append(r)
    byitem={key:one_item(bykey[key],asof=asof) for key in original}
    allrecs=sorted(valid,key=lambda r:(r["issued_epoch"],r["item_key"]))
    total=one_item(allrecs,asof=asof)
    # Adjacent comparisons in total across different items are NOT valid.
    total.update({
        "adjacent_issued_pairs_within_10min":sum(
            x["adjacent_issued_pairs_within_10min"] for x in byitem.values()),
        "unchanged_collector_observed_state_pairs":sum(
            x["unchanged_collector_observed_state_pairs"] for x in byitem.values()),
        "unchanged_collector_state_pairs_with_two_departures":sum(
            x["unchanged_collector_state_pairs_with_two_departures"] for x in byitem.values()),
        "same_observed_state_absolute_departure_shift_gt_5min":sum(
            x["same_observed_state_absolute_departure_shift_gt_5min"] for x in byitem.values()),
        "same_observed_state_absolute_departure_shift_gt_15min":sum(
            x["same_observed_state_absolute_departure_shift_gt_15min"] for x in byitem.values()),
        "first_issued_item_UTC_hours":sum(
            x["first_issued_item_UTC_hours"] for x in byitem.values()),
        "reconfirmation_counts_for_first_hour_proposals":dict(sum(
            (Counter(x["reconfirmation_counts_for_first_hour_proposals"])
             for x in byitem.values()),Counter())),
        "maturity_counts_for_first_hour_proposals":dict(sum(
            (Counter(x["maturity_counts_for_first_hour_proposals"])
             for x in byitem.values()),Counter())),
    })
    # Do not report any cross-item wait-shift median, since the aggregate
    # preceding row is not a consecutive decision for the same item.
    total["median_absolute_departure_shift_same_obs_minutes"]=None
    total["examples_of_shift_over_15min_same_collector_state"]=[]
    return {
        "status":"V132_TIMING_QUALITY_AND_WATCH_RECONFIRMATION_AUDIT",
        "asof_epoch":asof,"days":days,
        "read_only":True,
        "all_24_items":len(original),
        "original_graph_contract":"Prediction V2 shows predicted restock window and flight departure window; this v128 has no standalone restock timestamp",
        "new_model_contract":"earliest simulated arrival >=30 stock, two consecutive five-minute bins with scenario fraction >=0.60, 8h departure limit",
        "raw_issue_rows":len(raw),
        "valid_as_issued_rows":len(valid),
        "invalid_as_issued_rows":dict(invalid),
        "overall":total,"per_item":byitem,
        "no_verified_live_uk_or_other_country_provider_age":True,
        "no_real_player_flights_or_stock_purchase_proof":True,
        "scenario_fraction_is_not_calibrated_probability":True,
        "scores_may_change_with_monte_carlo_random_seed":True,
        "watch_not_equivalent_to_go":True,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days",type=int,choices=(1,2,3),default=2)
    parser.add_argument("--json",action="store_true")
    a=parser.parse_args()
    result=audit(days=a.days)
    if a.json:
        print(json.dumps(result,sort_keys=True))
        return
    print("===== V132 24-ITEM TIME-TO-LEAVE QUALITY AUDIT =====")
    print("ASOF:",result["asof_epoch"],"days",a.days,
          "issue rows",result["raw_issue_rows"],
          "valid",result["valid_as_issued_rows"])
    print("ALL ITEMS:",json.dumps(result["overall"],sort_keys=True))
    for item,row in result["per_item"].items():
        if row["issued_five_minute_snapshots"]:
            compact={key:val for key,val in row.items()
                     if key not in ("status_counts",
                          "examples_of_shift_over_15min_same_collector_state")}
            print(item,json.dumps(compact,sort_keys=True))
    print("NOT ACTIONABLE: long-term watches need fresh replan confirmation.")
    print("NOT CERTIFIED: arrival truth, per-country feed freshness, probabilities.")


if __name__=="__main__":
    main()
