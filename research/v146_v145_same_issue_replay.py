"""V146: bounded read-only V128-vs-V145 SAME-ISSUE replay on real collector data.

Original V128 sidecar identifies issued item/hour opportunities and the
original snapshot evidence; V145 is replayed against persisted collector
changes whose EVENT timestamps <= that same issued time. No lookahead in
model input. If the collector's reconstructed as-of item state disagrees
with what the V128 issue recorded, the cohort is excluded.

IMPORTANT: collector stock-history rows may have been backfilled after an
issue; the full original source snapshot is not frozen. Therefore this
is a HISTORICAL AS-OF REPLAY, not independently certified prospective
forward accuracy. The V88 outcome proxy uses later poll snapshots ONLY
after each departure's arrival is mature. Record pending/unknown separately.

Both DBs opened mode=ro. No service writes, no site updates, no API calls.
Only FIRST issue per item/UTC hour is studied to avoid counting nearby
five-minute emissions as independent trials.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from research.v128_full24_earliest_shadow import (
    COLLECTOR, SIDECAR, MAX_ITEM_ROWS, MIN_PHASES,
    exact_roster, fast_phases, empirical_arrival_scores,
    earliest_credible_for_country,
)
from research.v145_provider_continuous_phases import (
    provider_continuous_phases, observed_cycle_evidence_tier,
)
from research.v148_observed_earliest_stock_cycle import first_reachable_stock_cycles
from research.v150_stock_window_failure_diagnostic import diagnose_window_failure
from research.v151_stable_earliest_departure import stable_earliest_departure
from research.v152_first_restock_timing_evidence import evaluate_next_completed_restock
from research.v153_recent_completed_restock_baseline import recent_restock_forecasts
from research.v156_item_cycle_profile_router import (
    item_cycle_profile, route_issued_prediction,
)
from research.v157_prequential_stock_survival_router import prequential_item_route
from research.v158_flight_horizon_router import flight_horizon_item_route
from research.v159_issue_phase_episode_audit import episode_audit
from research.v88_poll_state_forward_report import observation

DAY=86400
MAX_DAYS=2
MAX_ISSUES=16000
MAX_MODEL_EVALS=180
GRACE=10
PENDING_BUFFER=180


def read_only(path):
    actual=Path(path).resolve(strict=True)
    if not actual.is_file():
        raise ValueError("missing SQLite source")
    con=sqlite3.connect(actual.as_uri()+"?mode=ro",uri=True,timeout=12)
    con.execute("PRAGMA query_only=ON")
    return con


def select_issued(ledger, *, earliest, asof):
    """Earliest issue per item and UTC hour, not a shuffled/survivor subset."""
    selected={}
    count=0
    for key,issued,status,decision,body in ledger.execute(
        """SELECT item_key,issued_epoch,source_status,decision_status,
                  payload_json
           FROM v128_issued WHERE issued_epoch>=? AND issued_epoch<=?
           ORDER BY issued_epoch,item_key LIMIT ?""",
        (earliest,asof,MAX_ISSUES+1),
    ):
        count+=1
        if count>MAX_ISSUES:
            raise ValueError("too many shadow issue records")
        slot=(key,int(issued)//3600)
        if slot in selected:
            continue
        data=json.loads(body)
        if not isinstance(data,dict):
            raise ValueError("invalid historical issue payload")
        selected[slot]={
            "item_key":key,"issued_epoch":int(issued),
            "source_status":status,"decision_status":decision,
            "payload":data,
        }
    return list(selected.values())


def _old_record_matches_asof(issued, old, observed):
    """Strong item/issue check; full past DB snapshot cannot be reconstructed."""
    body=issued["payload"]
    last=old["last_observation"]
    if (body.get("item_key")!=issued["item_key"] or
        body.get("issued_epoch")!=issued["issued_epoch"] or
        last is None or
        int(last.epoch)!=body.get("last_stock_change_epoch") or
        int(last.quantity)!=body.get("last_stock_quantity") or
        str(last.source)!=body.get("collector_source")):
        return False
    if body.get("phase")!=old["phase"] or (
            body.get("phase_onset") != old["phase_onset"]):
        return False
    if body.get("source_status") not in (
        "ISSUED_EMPIRICAL_TWO_PHASE_CURVE",
        "CURRENT_PHASE_ONSET_UNKNOWN",
        "INSUFFICIENT_COMPLETED_CYCLES",
        "NO_SURVIVING_PHASE_ANALOGS",
        "STOCK_CHANGE_TOO_OLD",
        "NO_ITEM_STOCK_HISTORY",
    ):
        return False
    return True


def _pair_score(db, country, item, arrival, now):
    if type(arrival) is not int:
        return "NOT_PROPOSED"
    label,success,_=observation(db,country,item,arrival,now)
    if label in ("POLL_STATE_PROXY_SUCCESS","POLL_STATE_PROXY_MISS"):
        return "HIT" if success else "MISS"
    if label=="PENDING":
        return "PENDING"
    return "UNKNOWN_"+label


def _score_counts(counter, label):
    counter["scorable" if label in ("HIT","MISS") else
            "pending" if label=="PENDING" else
            "unknown_or_no_proposal"]+=1
    counter[label]+=1


def _aggregate(rows):
    counters=Counter()
    out={}
    wait_seconds=defaultdict(list)
    explicit_wait_seconds=defaultdict(list)
    stable_wait_seconds=defaultdict(list)
    fine60_wait_seconds=defaultdict(list)
    paired_wait_seconds=defaultdict(list)
    first_restock_errors=defaultdict(list)
    for r in rows:
        c=r["comparison"]
        counters.update([c])
        if r["recovered"]:
            counters["recovered"]+=1
        key=r["item_key"]
        if key not in out:
            out[key]=Counter()
        item=out[key]
        item["issued_hourly_samples"]+=1
        if r.get("item_profile_stocked") is not None:
            item["profile_high_seconds_sum"]+=r["item_profile_stocked"]
            item["profile_high_seconds_n"]+=1
        if r.get("item_profile_depleted") is not None:
            item["profile_low_seconds_sum"]+=r["item_profile_depleted"]
            item["profile_low_seconds_n"]+=1
        if r.get("item_stock_regime"):
            item["stock_regime:"+r["item_stock_regime"]]+=1
        if r.get("item_depletion_regime"):
            item["depletion_regime:"+r["item_depletion_regime"]]+=1
        if r.get("routing_predeclared"):
            item["route_original:"+r["routing_predeclared"]]+=1
            item["route_reason:"+r["routing_reason"]]+=1
        if r.get("flight_horizon_selection"):
            item["flight_horizon_reason:"+r["flight_horizon_reason"]]+=1
            item["flight_horizon_chose:"+r["flight_horizon_selection"]]+=1
            item["flight_horizon_valid_origins"]+=r.get(
                "flight_horizon_valid_origins",0)
        if r.get("flight_horizon_departure") is not None:
            item["flight_horizon_proposals"]+=1
            item["flight_horizon_selected_paired"]+=int(
                r["flight_horizon_actual"]=="paired_complete")
            item["flight_horizon_selected_independent"]+=int(
                r["flight_horizon_actual"]=="independent")
            outcome=r.get("flight_horizon_outcome")
            item["flight_horizon_proxy_hit"]+=int(outcome=="HIT")
            item["flight_horizon_proxy_miss"]+=int(outcome=="MISS")
            item["flight_horizon_proxy_pending"]+=int(outcome=="PENDING")
            item["flight_horizon_proxy_unknown"]+=int(
                isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))
            if outcome in ("HIT","MISS") and (
                r.get("stable_outcome") in ("HIT","MISS")):
                if (r["flight_horizon_departure"]==r["stable_departure"] and
                    outcome!=r["stable_outcome"]):
                    raise AssertionError("flight router same-departure outcome mismatch")
                item["flight_horizon_vs_independent_matched"]+=1
                item["flight_horizon_only_vs_independent"]+=int(
                    outcome=="HIT" and r["stable_outcome"]=="MISS")
                item["independent_only_vs_flight_horizon"]+=int(
                    outcome=="MISS" and r["stable_outcome"]=="HIT")
            if outcome in ("HIT","MISS") and (
                r.get("leave_now_outcome") in ("HIT","MISS")):
                item["flight_horizon_vs_now_matched"]+=1
                item["flight_horizon_only_vs_now"]+=int(
                    outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                item["now_only_vs_flight_horizon"]+=int(
                    outcome=="MISS" and r["leave_now_outcome"]=="HIT")
        if r.get("prequential_selection"):
            item["prequential_reason:"+r["prequential_reason"]]+=1
            item["prequential_chose:"+r["prequential_selection"]]+=1
            if r.get("prequential_heldout_episodes"):
                item["prequential_scored_issue_hours"]+=1
        if r.get("prequential_departure") is not None:
            item["prequential_proposals"]+=1
            item["prequential_paired_selected"]+=int(
                r["prequential_actual"]=="paired_complete")
            item["prequential_independent_selected"]+=int(
                r["prequential_actual"]=="independent")
            outcome=r.get("prequential_outcome")
            item["prequential_proxy_hit"]+=int(outcome=="HIT")
            item["prequential_proxy_miss"]+=int(outcome=="MISS")
            item["prequential_proxy_pending"]+=int(outcome=="PENDING")
            item["prequential_proxy_unknown"]+=int(
                isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))
            if (outcome in ("HIT","MISS") and
                r.get("stable_outcome") in ("HIT","MISS")):
                if (r["prequential_departure"]==r["stable_departure"] and
                    outcome!=r["stable_outcome"]):
                    raise AssertionError("prequential same departure proxy contradiction")
                item["prequential_vs_independent_matched"]+=1
                item["prequential_only_vs_independent"]+=int(
                    outcome=="HIT" and r["stable_outcome"]=="MISS")
                item["independent_only_vs_prequential"]+=int(
                    outcome=="MISS" and r["stable_outcome"]=="HIT")
            if (outcome in ("HIT","MISS") and
                r.get("leave_now_outcome") in ("HIT","MISS")):
                item["prequential_vs_now_matched"]+=1
                item["prequential_only_vs_now"]+=int(
                    outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                item["now_only_vs_prequential"]+=int(
                    outcome=="MISS" and r["leave_now_outcome"]=="HIT")
        if r.get("routed_departure") is not None:
            item["routed_proposals"]+=1
            if r["routing_actual"]=="paired_complete":
                item["routed_selected_paired"]+=1
            else:
                item["routed_selected_independent"]+=1
            outcome=r.get("routed_outcome")
            item["routed_proxy_hit"]+=int(outcome=="HIT")
            item["routed_proxy_miss"]+=int(outcome=="MISS")
            item["routed_proxy_pending"]+=int(outcome=="PENDING")
            item["routed_proxy_unknown"]+=int(
                isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))
            if (outcome in ("HIT","MISS") and
                r.get("stable_outcome") in ("HIT","MISS")):
                if (r["routed_departure"]==r["stable_departure"] and
                    outcome!=r["stable_outcome"]):
                    raise AssertionError("routed same-departure outcome mismatch")
                item["routed_vs_independent_matched"]+=1
                item["routed_only_vs_independent"]+=int(
                    outcome=="HIT" and r["stable_outcome"]=="MISS")
                item["independent_only_vs_routed"]+=int(
                    outcome=="MISS" and r["stable_outcome"]=="HIT")
            if (outcome in ("HIT","MISS") and
                r.get("leave_now_outcome") in ("HIT","MISS")):
                item["routed_vs_leave_now_matched"]+=1
                item["routed_only_vs_now"]+=int(
                    outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                item["now_only_vs_routed"]+=int(
                    outcome=="MISS" and r["leave_now_outcome"]=="HIT")
        item[c]+=1
        if r.get("original_source_status"):
            item["original_source:"+r["original_source_status"]]+=1
        if r.get("new_status"):
            item["new_decision:"+r["new_status"]]+=1
        if r["recovered"]:
            item["recovered"]+=1
        if r.get("explicit_status"):
            item["explicit_status:"+r["explicit_status"]]+=1
        if r.get("explicit_diagnostic_reason"):
            item["diagnosis:"+r["explicit_diagnostic_reason"]]+=1
        if r.get("median_only_scenario_available") is True:
            item["median_only_nonactionable_scenario"]+=1
        if r.get("stable_status"):
            item["stable_status:"+r["stable_status"]]+=1
        if r.get("next_restock_status"):
            item["restock:"+r["next_restock_status"]]+=1
        if r.get("recent_restock_status"):
            item["recency_status:"+r["recent_restock_status"]]+=1
        for name,status in r.get("recent_variant_statuses",{}).items():
            item["recency_status:"+name+":"+status]+=1
        errors=r.get("recent_restocks_abs_errors_seconds",{})
        for name,error in errors.items():
            if type(error) is not int or error<0:
                raise ValueError("invalid restock error")
            prefix="recent_"+name
            item[prefix+"_scored"]+=1
            item[prefix+"_abs_total_seconds"]+=error
            item[prefix+"_within_5m"]+=int(error<=300)
            baseline_error=r.get("next_restock_abs_error_seconds")
            if type(baseline_error) is int:
                item[prefix+"_paired"]+=1
                item[prefix+"_beats_v151"]+=int(error<baseline_error)
                item["v151_beats_"+prefix]+=int(baseline_error<error)
                item[prefix+"_ties"]+=int(error==baseline_error)
                item[prefix+"_paired_baseline_sum"]+=baseline_error
        if r.get("next_restock_abs_error_seconds") is not None:
            first_restock_errors[key].append(r["next_restock_abs_error_seconds"])
        if r.get("stable_peak_scenario_stock_fraction") is not None:
            peak=r["stable_peak_scenario_stock_fraction"]
            if peak<0.6:
                item["stable_peak_under_60pct_scenario_gate"]+=1
            elif r.get("stable_supported_adjacent_pairs",0)==0:
                item["stable_single_supported_bin_only"]+=1
        # One-minute departure RESOLUTION challenger reuses the same
        # scenarios and the five-minute future support requirement.
        # Score only aligned mature outcomes; no survivor bias.
        # Paired-cycle challenger uses only directly completed adjacent
        # depletion -> stocked intervals. Never count abstention as a miss.
        if r.get("paired_status"):
            item["paired_status:"+r["paired_status"]]+=1
        if r.get("paired_next_restock_abs_error_seconds") is not None:
            error=r["paired_next_restock_abs_error_seconds"]
            item["paired_restock_scored"]+=1
            item["paired_restock_abs_sum_seconds"]+=error
            old_error=r.get("next_restock_abs_error_seconds")
            if type(old_error) is int:
                item["paired_restock_mature_comparisons"]+=1
                item["paired_restock_better"]+=int(error<old_error)
                item["paired_restock_worse"]+=int(error>old_error)
                item["paired_restock_tie"]+=int(error==old_error)
        if r.get("paired_departure") is not None:
            item["paired_proposals"]+=1
            paired_wait_seconds[key].append(
                r["paired_departure"]-r["issued_epoch"])
            outcome=r.get("paired_outcome")
            item["paired_proxy_hit"]+=int(outcome=="HIT")
            item["paired_proxy_miss"]+=int(outcome=="MISS")
            item["paired_proxy_pending"]+=int(outcome=="PENDING")
            item["paired_proxy_unknown"]+=int(
                isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))
            if outcome in ("HIT","MISS") and (
                r.get("stable_outcome") in ("HIT","MISS")
            ):
                if (r["paired_departure"]==r["stable_departure"] and
                    outcome!=r["stable_outcome"]):
                    raise AssertionError("same departure produced conflicting outcomes")
                item["paired_vs_independent_matched"]+=1
                item["paired_only_vs_independent"]+=int(
                    outcome=="HIT" and r["stable_outcome"]=="MISS")
                item["independent_only_vs_paired"]+=int(
                    outcome=="MISS" and r["stable_outcome"]=="HIT")
            if outcome in ("HIT","MISS") and (
                r.get("leave_now_outcome") in ("HIT","MISS")
            ):
                item["paired_vs_leave_now_matched"]+=1
                item["paired_only_vs_leave_now"]+=int(
                    outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                item["leave_now_only_vs_paired"]+=int(
                    outcome=="MISS" and r["leave_now_outcome"]=="HIT")
        if r.get("fine60_status"):
            item["fine60_status:"+r["fine60_status"]]+=1
        if r.get("fine60_departure") is not None:
            item["fine60_proposals"]+=1
            fine60_wait_seconds[key].append(
                r["fine60_departure"]-r["issued_epoch"])
            outcome=r.get("fine60_outcome")
            item["fine60_proxy_hit"]+=int(outcome=="HIT")
            item["fine60_proxy_miss"]+=int(outcome=="MISS")
            item["fine60_proxy_pending"]+=int(outcome=="PENDING")
            item["fine60_proxy_unknown"]+=int(
                isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))
            if r.get("stable_departure") is None:
                item["fine60_new_from_coarse_abstention"]+=1
            else:
                if r["fine60_departure"]>r["stable_departure"]:
                    raise AssertionError("fine 60s scan departed later than coarse 5min")
                item["fine60_earlier_than_coarse"]+=int(
                    r["fine60_departure"]<r["stable_departure"])
                if outcome in ("HIT","MISS") and r.get(
                    "stable_outcome") in ("HIT","MISS"):
                    if (r["fine60_departure"]==r["stable_departure"]
                        and outcome!=r["stable_outcome"]):
                        raise AssertionError("same 60s/300s departure scored differently")
                    item["fine60_vs_coarse_matched"]+=1
                    item["fine60_only_vs_coarse"]+=int(
                        outcome=="HIT" and r["stable_outcome"]=="MISS")
                    item["coarse_only_vs_fine60"]+=int(
                        outcome=="MISS" and r["stable_outcome"]=="HIT")
            if outcome in ("HIT","MISS") and r.get(
                "leave_now_outcome") in ("HIT","MISS"):
                item["fine60_vs_now_matched"]+=1
                item["fine60_only_vs_now"]+=int(
                    outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                item["now_only_vs_fine60"]+=int(
                    outcome=="MISS" and r["leave_now_outcome"]=="HIT")
        if r.get("stable_departure") is not None:
            if r["stable_departure"] < r["issued_epoch"]:
                raise ValueError("V151 proposed a past departure")
            if r["stable_departure"] == r["issued_epoch"]:
                item["stable_depart_now_proposals"]+=1
            else:
                item["stable_depart_future_proposals"]+=1
            item["stable_proposals"]+=1
            stable_wait_seconds[key].append(
                r["stable_departure"]-r["issued_epoch"])
            outcome=r.get("stable_outcome")
            item["stable_proxy_hit"]+=int(outcome=="HIT")
            item["stable_proxy_miss"]+=int(outcome=="MISS")
            item["stable_proxy_pending"]+=int(outcome=="PENDING")
            item["stable_proxy_unknown"]+=int(
                isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))
            if outcome in ("HIT","MISS") and (
                r.get("leave_now_outcome") in ("HIT","MISS")
            ):
                item["matched_stable_vs_now"]+=1
                item["stable_only_vs_now"]+=int(
                    outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                item["now_only_vs_stable"]+=int(
                    outcome=="MISS" and r["leave_now_outcome"]=="HIT")
                if r["stable_departure"]==r["issued_epoch"] and (
                    outcome!=r["leave_now_outcome"]
                ):
                    raise AssertionError(
                        "same departure epoch gave different arrival proxy outcome")
                if r["stable_departure"]>r["issued_epoch"]:
                    item["matched_stable_delayed_vs_now"]+=1
                    item["delayed_stable_only_vs_now"]+=int(
                        outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                    item["delayed_now_only_vs_stable"]+=int(
                        outcome=="MISS" and r["leave_now_outcome"]=="HIT")
            if r.get("stable_long_wait") is True:
                item["stable_long_wait_flags"]+=1
        if r.get("explicit_departure") is not None:
            item["explicit_proposals"]+=1
            explicit_wait_seconds[key].append(
                r["explicit_departure"]-r["issued_epoch"])
            outcome=r.get("explicit_outcome")
            item["explicit_proxy_hit"]+=int(outcome=="HIT")
            item["explicit_proxy_miss"]+=int(outcome=="MISS")
            item["explicit_proxy_pending"]+=int(outcome=="PENDING")
            item["explicit_proxy_unknown"]+=int(
                isinstance(outcome,str) and outcome.startswith("UNKNOWN_"))
            if (outcome in ("HIT","MISS") and
                r.get("leave_now_outcome") in ("HIT","MISS")):
                item["matched_explicit_vs_now"]+=1
                item["explicit_only_vs_now"]+=int(
                    outcome=="HIT" and r["leave_now_outcome"]=="MISS")
                item["now_only_vs_explicit"]+=int(
                    outcome=="MISS" and r["leave_now_outcome"]=="HIT")
        # Direct V151 vs V148 head-to-head: exact same item/issue cohort
        # and both arrivals mature/observable. An unconditional V151 rate
        # cannot answer this paired question.
        if (r.get("stable_departure") is not None
            and r.get("explicit_departure") is not None
            and r.get("stable_outcome") in ("HIT","MISS")
            and r.get("explicit_outcome") in ("HIT","MISS")):
            if (r["stable_departure"]==r["explicit_departure"]
                and r["stable_outcome"]!=r["explicit_outcome"]):
                raise AssertionError(
                    "two models targeting the same departure have incompatible outcomes")
            item["matched_stable_vs_explicit"]+=1
            item["stable_only_vs_explicit"]+=int(
                r["stable_outcome"]=="HIT" and r["explicit_outcome"]=="MISS")
            item["explicit_only_vs_stable"]+=int(
                r["stable_outcome"]=="MISS" and r["explicit_outcome"]=="HIT")
            item["matched_different_departures"]+=int(
                r["stable_departure"]!=r["explicit_departure"])
        if r["old_departure"] is not None:
            item["original_proposals"]+=1
            item["old_proxy_hit"]+=int(r["old_outcome"]=="HIT")
            item["old_proxy_miss"]+=int(r["old_outcome"]=="MISS")
            item["old_proxy_pending"]+=int(r["old_outcome"]=="PENDING")
            item["old_proxy_unknown"]+=int(
                r["old_outcome"].startswith("UNKNOWN_"))
        if r["new_departure"] is not None:
            item["new_proposals"]+=1
            if type(r.get("issued_epoch")) is int:
                wait_seconds[key].append(
                    r["new_departure"]-r["issued_epoch"])
            _score_counts(item,r["new_outcome"])
            if r["new_outcome"] in ("HIT","MISS") and (
                r["leave_now_outcome"] in ("HIT","MISS")
            ):
                item["matched_new_vs_now"]+=1
                item["new_hits_in_matched"]+=int(r["new_outcome"]=="HIT")
                item["now_hits_in_matched"]+=int(
                    r["leave_now_outcome"]=="HIT")
                item["new_only"]+=int(r["new_outcome"]=="HIT" and
                                     r["leave_now_outcome"]=="MISS")
                item["now_only"]+=int(r["new_outcome"]=="MISS" and
                                     r["leave_now_outcome"]=="HIT")
        if r["old_departure"] is not None and r["new_departure"] is not None and (
            r["old_outcome"] in ("HIT","MISS") and
            r["new_outcome"] in ("HIT","MISS")):
            item["matched_new_vs_old"]+=1
            item["new_only_vs_old"]+=int(
                r["new_outcome"]=="HIT" and r["old_outcome"]=="MISS")
            item["old_only_vs_new"]+=int(
                r["old_outcome"]=="HIT" and r["new_outcome"]=="MISS")
        if r["long_wait_vs_cadence"]:
            item["long_wait_needs_explanation"]+=1
    for v in out.values():
        # Convert Counter into plain JSON-friendly dict, including zero
        # denominators for sparse items; never hide absent model proposals.
        for k in ("flight_horizon_proposals","flight_horizon_selected_paired",
                  "flight_horizon_selected_independent",
                  "flight_horizon_proxy_hit","flight_horizon_proxy_miss",
                  "flight_horizon_proxy_pending","flight_horizon_proxy_unknown",
                  "flight_horizon_vs_independent_matched",
                  "flight_horizon_only_vs_independent",
                  "independent_only_vs_flight_horizon",
                  "flight_horizon_vs_now_matched",
                  "flight_horizon_only_vs_now","now_only_vs_flight_horizon",
                  "flight_horizon_valid_origins",
                  "prequential_proposals","prequential_paired_selected",
                  "prequential_independent_selected","prequential_scored_issue_hours",
                  "prequential_proxy_hit","prequential_proxy_miss",
                  "prequential_proxy_pending","prequential_proxy_unknown",
                  "prequential_vs_independent_matched",
                  "prequential_only_vs_independent",
                  "independent_only_vs_prequential",
                  "prequential_vs_now_matched","prequential_only_vs_now",
                  "now_only_vs_prequential",
                  "routed_proposals","routed_selected_paired",
                  "routed_selected_independent",
                  "routed_proxy_hit","routed_proxy_miss","routed_proxy_pending",
                  "routed_proxy_unknown","routed_vs_independent_matched",
                  "routed_only_vs_independent","independent_only_vs_routed",
                  "routed_vs_leave_now_matched","routed_only_vs_now",
                  "now_only_vs_routed",
                  "paired_proposals","paired_proxy_hit","paired_proxy_miss",
                  "paired_proxy_pending","paired_proxy_unknown",
                  "paired_vs_independent_matched",
                  "paired_only_vs_independent","independent_only_vs_paired",
                  "paired_vs_leave_now_matched",
                  "paired_only_vs_leave_now","leave_now_only_vs_paired",
                  "fine60_proposals","fine60_proxy_hit",
                  "fine60_proxy_miss","fine60_proxy_pending",
                  "fine60_proxy_unknown","fine60_vs_coarse_matched",
                  "fine60_only_vs_coarse","coarse_only_vs_fine60",
                  "fine60_earlier_than_coarse","fine60_new_from_coarse_abstention",
                  "fine60_vs_now_matched","fine60_only_vs_now",
                  "now_only_vs_fine60",
                  "stable_peak_under_60pct_scenario_gate",
                  "stable_single_supported_bin_only",
                  "stable_depart_now_proposals",
                  "stable_depart_future_proposals",
                  "matched_stable_delayed_vs_now",
                  "delayed_stable_only_vs_now",
                  "delayed_now_only_vs_stable",
                  "matched_stable_vs_explicit",
                  "stable_only_vs_explicit","explicit_only_vs_stable",
                  "matched_different_departures",
                  "stable_proposals","stable_proxy_hit",
                  "stable_proxy_miss","stable_proxy_pending",
                  "stable_proxy_unknown","matched_stable_vs_now",
                  "stable_only_vs_now","now_only_vs_stable",
                  "stable_long_wait_flags",
                  "explicit_proposals","explicit_proxy_hit",
                  "explicit_proxy_miss","explicit_proxy_pending",
                  "explicit_proxy_unknown","matched_explicit_vs_now",
                  "explicit_only_vs_now","now_only_vs_explicit",
                  "original_proposals","old_proxy_hit","old_proxy_miss",
                  "old_proxy_pending","old_proxy_unknown",
                  "matched_new_vs_old","new_only_vs_old","old_only_vs_new",
                  "new_proposals","matched_new_vs_now","new_only",
                  "now_only","new_hits_in_matched","now_hits_in_matched",
                  "recovered","long_wait_needs_explanation","HIT","MISS",
                  "PENDING","scorable","unknown_or_no_proposal"):
            v[k]+=0
    for key, v in out.items():
        waits=wait_seconds[key]
        v["new_departure_mean_wait_seconds"]=(
            round(statistics.mean(waits),1) if waits else None
        )
        v["new_departure_median_wait_seconds"]=(
            round(statistics.median(waits),1) if waits else None
        )
        vals=first_restock_errors[key]
        v["next_restock_scored"]=len(vals)
        v["next_restock_abs_error_total_seconds"]=sum(vals)
        v["next_restock_mean_abs_error_seconds"]=(round(statistics.mean(vals),1) if vals else None)
        v["next_restock_within_1m"]=sum(x<=60 for x in vals)
        v["next_restock_within_5m"]=sum(x<=300 for x in vals)
        v["next_restock_within_15m"]=sum(x<=900 for x in vals)
        paired_waits=paired_wait_seconds[key]
        v["paired_median_wait_seconds"]=(
            round(statistics.median(paired_waits),1)
            if paired_waits else None)
        fine_waits=fine60_wait_seconds[key]
        v["fine60_departure_median_wait_seconds"]=(
            round(statistics.median(fine_waits),1) if fine_waits else None)
        stable_waits=stable_wait_seconds[key]
        v["stable_departure_median_wait_seconds"]=(
            round(statistics.median(stable_waits),1)
            if stable_waits else None
        )
        explicit_waits=explicit_wait_seconds[key]
        v["explicit_departure_median_wait_seconds"]=(
            round(statistics.median(explicit_waits),1)
            if explicit_waits else None
        )
    for key,v in out.items():
        if v["stable_depart_now_proposals"]+v["stable_depart_future_proposals"] != v["stable_proposals"]:
            raise AssertionError("V151 now/future coverage does not balance")
        if (v["matched_stable_vs_explicit"] <
            v["stable_only_vs_explicit"]+v["explicit_only_vs_stable"]):
            raise AssertionError("V151/V148 paired contradictions exceed scorable pairs")
    return dict(counters),{k:dict(v) for k,v in sorted(out.items())}


def replay(*,collector=COLLECTOR, sidecar=SIDECAR, now=None,
           days=1, max_model_evals=MAX_MODEL_EVALS):
    if (type(days) is not int or not 1<=days<=MAX_DAYS or
        type(max_model_evals) is not int or
        not 1<=max_model_evals<=MAX_MODEL_EVALS):
        raise ValueError("unbounded replay request")
    current=int(time.time()) if now is None else now
    if type(current) is not int or current<DAY:
        raise ValueError("invalid now")
    if Path(collector).resolve(strict=True)==Path(sidecar).resolve(strict=True):
        raise ValueError("source and sidecar must differ")
    roster=exact_roster()
    with closing(read_only(collector)) as stock, closing(read_only(sidecar)) as ledger:
        starts=select_issued(ledger,earliest=current-days*DAY,asof=current)
        eligible=[x for x in starts if x["item_key"] in roster]
        # Stable chronological order and objective cap by earliest issue;
        # evaluate no latest/high-score survivor-biased sampling.
        eligible.sort(key=lambda e:(e["issued_epoch"],e["item_key"]))
        if not eligible:
            raise ValueError("no V128 issued cohorts in requested period")
        gaps=[
            (int(a),None if b is None else int(b))
            for a,b in stock.execute(
                """SELECT start_timestamp,end_timestamp FROM collection_gaps
                   WHERE start_timestamp<=?""",(current,))
        ]
        issues_by_item=defaultdict(list)
        for entry in eligible:
            issues_by_item[entry["item_key"]].append(entry)
        results=[]
        total_model_evals=0
        per_item_budget=math.ceil(max_model_evals/len(roster))
        for key in sorted(roster):
            country,item=key.split(":",1)
            item_model_evals=0
            item_issues=issues_by_item[key]
            if not item_issues:
                continue
            top_issue=item_issues[-1]["issued_epoch"]
            raw=stock.execute(
                """SELECT timestamp,quantity,source FROM stock_history
                   WHERE country=? AND lower(item_name)=lower(?)
                    AND timestamp<=?
                   ORDER BY timestamp DESC,id DESC LIMIT ?""",
                (country,item,top_issue,MAX_ITEM_ROWS+1)
            ).fetchall()
            if len(raw)>MAX_ITEM_ROWS:
                results.extend({
                    "item_key":key,"comparison":"SOURCE_HISTORY_LIMIT",
                    "recovered":False,"new_departure":None,
                    "old_departure":None,"old_outcome":"NOT_PROPOSED",
                    "next_restock_status":None,"next_restock_abs_error_seconds":None,
                    "recent_restocks_abs_errors_seconds":{},
                    "issue_phase":None,"issue_phase_onset":None,
                    "item_profile_stocked":None,
                    "item_profile_depleted":None,
                    "item_stock_regime":None,
                    "item_depletion_regime":None,
                    "routing_predeclared":None,
                    "routing_reason":None,"routing_actual":None,
                    "routed_departure":None,"routed_outcome":"NOT_PROPOSED",
                    "prequential_selection":None,"prequential_reason":None,
                    "prequential_heldout_episodes":0,
                    "prequential_actual":None,
                    "prequential_departure":None,
                    "prequential_outcome":"NOT_PROPOSED",
                    "flight_horizon_selection":None,
                    "flight_horizon_reason":None,
                    "flight_horizon_valid_origins":0,
                    "flight_horizon_actual":None,
                    "flight_horizon_departure":None,
                    "flight_horizon_outcome":"NOT_PROPOSED",
                    "paired_departure":None,"paired_status":None,
                    "paired_outcome":"NOT_PROPOSED",
                    "paired_next_restock_abs_error_seconds":None,
                    "fine60_departure":None,"fine60_status":None,
                    "fine60_outcome":"NOT_PROPOSED",
                    "stable_departure":None,"stable_status":None,
                    "stable_outcome":"NOT_PROPOSED","stable_long_wait":False,
                    "explicit_departure":None,"explicit_status":None,
                    "explicit_diagnostic_reason":None,
                    "median_only_scenario_available":False,
                    "explicit_outcome":"NOT_PROPOSED",
                    "new_outcome":"NOT_PROPOSED",
                    "leave_now_outcome":"NOT_PROPOSED",
                    "long_wait_vs_cadence":False,
                } for _ in item_issues)
                continue
            from research.v107_explicit_restock_cycle_baseline import StockObservation
            # Use last-ID state at duplicate timestamps, as current V128
            # fast_phases is sensitive to duplicate clock stamps.
            ordered = [
                StockObservation(int(t),int(q),str(source))
                for t,q,source in reversed(raw)
                if t is not None and q is not None and source is not None
            ]
            times=[r.epoch for r in ordered]
            if times != sorted(times):
                raise ValueError("unordered SQLite as-of evidence")
            # The ORIGINAL issue-time snapshot remains unchanged.
            # Later collector observations are only an outcome holdout.
            future_rows=stock.execute(
                """SELECT timestamp,quantity,source FROM stock_history
                   WHERE country=? AND lower(item_name)=lower(?)
                     AND timestamp>? AND timestamp<=?
                   ORDER BY timestamp ASC,id ASC LIMIT ?""",
                (country,item,top_issue,current,MAX_ITEM_ROWS+1)
            ).fetchall()
            if len(future_rows)<=MAX_ITEM_ROWS:
                outcome_obs=ordered+[
                    StockObservation(int(t),int(q),str(source))
                    for t,q,source in future_rows
                    if t is not None and q is not None and source is not None
                ]
                outcome_phases=provider_continuous_phases(
                    outcome_obs,asof=current,gaps=gaps)
            else:
                outcome_obs=outcome_phases=None
            for issue in item_issues:
                issued=issue["issued_epoch"]
                subset=ordered[:bisect.bisect_right(times,issued)]
                old=fast_phases(subset,asof=issued,gaps=gaps)
                new=provider_continuous_phases(subset,asof=issued,gaps=gaps)
                baseline=issue["payload"]
                record={
                    "item_key":key, "issued_epoch":issued,
                    "original_status":issue["decision_status"],
                    "original_source_status":issue["source_status"],
                    "previous_phase_onset":old["phase_onset"],
                    "recovered_phase_onset":new["phase_onset"],
                    "old_completed_high":len(old["stocked_durations"]),
                    "new_completed_high":len(new["stocked_durations"]),
                    "old_completed_low":len(old["depleted_durations"]),
                    "new_completed_low":len(new["depleted_durations"]),
                    "history_evidence_tier":observed_cycle_evidence_tier(new)["tier"],
                    "issue_phase":new["phase"],
                    "issue_phase_onset":new["phase_onset"],
                    "recovered":False,
                    "old_departure":baseline.get("earliest_departure"),
                    "old_arrival":baseline.get("earliest_arrival"),
                    "old_outcome":"NOT_PROPOSED",
                    "next_restock_status":None,"next_restock_abs_error_seconds":None,
                    "recent_restocks_abs_errors_seconds":{},
                    "item_profile_stocked":None,
                    "item_profile_depleted":None,
                    "item_stock_regime":None,
                    "item_depletion_regime":None,
                    "routing_predeclared":None,
                    "routing_reason":None,"routing_actual":None,
                    "routed_departure":None,"routed_outcome":"NOT_PROPOSED",
                    "prequential_selection":None,"prequential_reason":None,
                    "prequential_heldout_episodes":0,
                    "prequential_actual":None,
                    "prequential_departure":None,
                    "prequential_outcome":"NOT_PROPOSED",
                    "flight_horizon_selection":None,
                    "flight_horizon_reason":None,
                    "flight_horizon_valid_origins":0,
                    "flight_horizon_actual":None,
                    "flight_horizon_departure":None,
                    "flight_horizon_outcome":"NOT_PROPOSED",
                    "paired_departure":None,"paired_status":None,
                    "paired_outcome":"NOT_PROPOSED",
                    "paired_next_restock_abs_error_seconds":None,
                    "fine60_departure":None,"fine60_status":None,
                    "fine60_outcome":"NOT_PROPOSED",
                    "stable_departure":None,"stable_status":None,
                    "stable_outcome":"NOT_PROPOSED","stable_long_wait":False,
                    "explicit_departure":None,"explicit_status":None,
                    "explicit_diagnostic_reason":None,
                    "median_only_scenario_available":False,
                    "explicit_outcome":"NOT_PROPOSED",
                    "new_departure":None, "new_arrival":None,
                    "new_outcome":"NOT_PROPOSED",
                    "leave_now_outcome":"NOT_PROPOSED",
                    "comparison":"UNCLASSIFIED",
                    "median_observed_restock_spacing_seconds":None,
                    "long_wait_vs_cadence":False,
                    "actual_game_success_unverified":True,
                    "historical_collector_may_have_post_issue_backfills":True,
                }
                if not _old_record_matches_asof(issue,old,new):
                    record["comparison"]="ISSUED_SOURCE_SNAPSHOT_MISMATCH"
                    results.append(record)
                    continue
                if type(record["old_arrival"]) is int:
                    record["old_outcome"]=_pair_score(
                        stock,country,item,record["old_arrival"],current)
                # V151 is independent of V128's arbitrary 5 HIGH+LOW MC
                # eligibility and V148's potentially disjoint quantile bands.
                # Score the entire 5-minute grid from SAME saved issue-time
                # history, before looking at future poll-state outcomes.
                stable=stable_earliest_departure(
                    key,new,asof=issued,scenarios=64)
                fine=stable_earliest_departure(
                    key,new,asof=issued,scenarios=64,
                    departure_step_seconds=60)
                if ("score_bins" in stable and "score_bins" in fine
                    and stable["score_bins"]!=fine["score_bins"][::5]):
                    raise AssertionError("V151 60s and 300s scenario support diverged")
                if (("first_next_restock_onset_median_seconds" in stable and
                     "first_next_restock_onset_median_seconds" in fine)
                    and stable["first_next_restock_onset_median_seconds"]!=
                    fine["first_next_restock_onset_median_seconds"]):
                    raise AssertionError("V151 model scenario cohorts differ")
                paired=stable_earliest_departure(
                    key,new,asof=issued,scenarios=64,
                    cycle_sampling="paired_complete")
                profile=item_cycle_profile(key,new,asof=issued)
                heldout=prequential_item_route(key,new,asof=issued)
                flight_cv=flight_horizon_item_route(key,new,asof=issued)
                frozen_flight_profile={
                    "item_key":key,"issued_epoch":issued,
                    "predeclared_research_route":flight_cv["selected_sampling"],
                }
                chosen_flight=route_issued_prediction(
                    frozen_flight_profile,
                    {"item_key":key,"issued_epoch":issued,
                     "cycle_sampling":"independent",
                     "first_reachable":stable["first_reachable"]},
                    {"item_key":key,"issued_epoch":issued,
                     "cycle_sampling":"paired_complete",
                     "first_reachable":paired["first_reachable"]})
                record["flight_horizon_selection"]=flight_cv["selected_sampling"]
                record["flight_horizon_reason"]=flight_cv["reason"]
                record["flight_horizon_valid_origins"]=flight_cv[
                    "validation_origin_count"]
                record["flight_horizon_actual"]=chosen_flight["actual_model_used"]
                if chosen_flight["departure_epoch"] is not None:
                    record["flight_horizon_departure"]=chosen_flight[
                        "departure_epoch"]
                    record["flight_horizon_outcome"]=_pair_score(
                        stock,country,item,chosen_flight["arrival_epoch"],current)
                frozen_prequential_profile={
                    "item_key":key,"issued_epoch":issued,
                    "predeclared_research_route":heldout["selected_sampling"],
                }
                selected_prequential=route_issued_prediction(
                    frozen_prequential_profile,
                    {"item_key":key,"issued_epoch":issued,
                     "cycle_sampling":"independent",
                     "first_reachable":stable["first_reachable"]},
                    {"item_key":key,"issued_epoch":issued,
                     "cycle_sampling":"paired_complete",
                     "first_reachable":paired["first_reachable"]})
                record["prequential_selection"]=heldout["selected_sampling"]
                record["prequential_reason"]=heldout["reason"]
                record["prequential_heldout_episodes"]=heldout[
                    "heldout_episodes"]
                record["prequential_actual"]=selected_prequential["actual_model_used"]
                if selected_prequential["departure_epoch"] is not None:
                    record["prequential_departure"]=selected_prequential[
                        "departure_epoch"]
                    record["prequential_outcome"]=_pair_score(
                        stock,country,item,
                        selected_prequential["arrival_epoch"],current)
                chosen=route_issued_prediction(
                    profile,
                    {"item_key":key,"issued_epoch":issued,
                     "cycle_sampling":"independent",
                     "first_reachable":stable["first_reachable"]},
                    {"item_key":key,"issued_epoch":issued,
                     "cycle_sampling":"paired_complete",
                     "first_reachable":paired["first_reachable"]})
                record["item_profile_stocked"]=profile[
                    "stocked_median_seconds"]
                record["item_profile_depleted"]=profile[
                    "depleted_median_seconds"]
                record["item_stock_regime"]=profile["stock_duration_regime"]
                record["item_depletion_regime"]=profile[
                    "depletion_duration_regime"]
                record["routing_predeclared"]=profile[
                    "predeclared_research_route"]
                record["routing_reason"]=profile["selection_reason"]
                record["routing_actual"]=chosen["actual_model_used"]
                if chosen["departure_epoch"] is not None:
                    record["routed_departure"]=chosen["departure_epoch"]
                    record["routed_arrival"]=chosen["arrival_epoch"]
                    record["routed_outcome"]=_pair_score(
                        stock,country,item,chosen["arrival_epoch"],current)
                record["paired_status"]=paired["status"]
                record["paired_completed_cycles"]=paired.get("completed_paired_cycles")
                record["paired_peak_fraction"]=paired.get(
                    "peak_scenario_stock_fraction")
                pair_depart=paired["first_reachable"]
                if pair_depart is not None:
                    record["paired_departure"]=pair_depart["departure_epoch"]
                    record["paired_arrival"]=pair_depart["arrival_epoch"]
                    record["paired_outcome"]=_pair_score(
                        stock,country,item,pair_depart["arrival_epoch"],current)
                record["fine60_status"]=fine["status"]
                fine_depart=fine["first_reachable"]
                if fine_depart is not None:
                    record["fine60_departure"]=fine_depart["departure_epoch"]
                    record["fine60_arrival"]=fine_depart["arrival_epoch"]
                    record["fine60_outcome"]=_pair_score(
                        stock,country,item,fine_depart["arrival_epoch"],current)
                record["stable_status"]=stable["status"]
                record["stable_scenario_score_now"]=stable["score_now"]
                record["stable_peak_scenario_stock_fraction"]=stable.get(
                    "peak_scenario_stock_fraction")
                record["stable_supported_adjacent_pairs"]=stable.get(
                    "adjacent_supported_bin_count")
                recent=recent_restock_forecasts(
                    key,new,asof=issued)
                record["recent_restock_status"]=recent["status"]
                record["recent_variant_statuses"]={
                    name:spec["status"] for name,spec in recent["forecasts"].items()}
                if outcome_phases is not None:
                    time_to_restock=stable.get(
                        "first_next_restock_onset_median_seconds")
                    forecast=(issued+time_to_restock
                              if type(time_to_restock) is int else None)
                    result_next=evaluate_next_completed_restock(
                        outcome_obs,outcome_phases,issued=issued,
                        predicted_onset_epoch=forecast,
                        asof=current,gaps=gaps)
                    record["next_restock_status"]=result_next["status"]
                    record["next_restock_abs_error_seconds"]=result_next[
                        "absolute_forecast_error_seconds"]
                    verified_start=result_next[
                        "next_observed_complete_start_epoch"]
                    paired_ttr=paired.get(
                        "first_next_restock_onset_median_seconds")
                    if type(verified_start) is int and type(paired_ttr) is int:
                        record["paired_next_restock_abs_error_seconds"]=abs(
                            issued+paired_ttr-verified_start)
                    if type(verified_start) is int:
                        for name,variant in recent["forecasts"].items():
                            predicted=variant["forecast_epoch"]
                            if type(predicted) is int:
                                record["recent_restocks_abs_errors_seconds"][name]=abs(
                                    predicted-verified_start)
                if stable["first_reachable"] is not None:
                    cand=stable["first_reachable"]
                    record["stable_departure"]=cand["departure_epoch"]
                    record["stable_arrival"]=cand["arrival_epoch"]
                    record["stable_scenario_fraction"]=cand[
                        "scenario_stock_fraction"]
                    record["stable_long_wait"]=(
                        cand["cadence_warning"] is not None)
                    record["stable_outcome"]=_pair_score(
                        stock,country,item,cand["arrival_epoch"],current)
                    record["leave_now_outcome"]=_pair_score(
                        stock,country,item,
                        issued+baseline["travel_seconds"],current)
                if (record["fine60_departure"] is not None and
                    record["leave_now_outcome"]=="NOT_PROPOSED"):
                    record["leave_now_outcome"]=_pair_score(
                        stock,country,item,
                        issued+baseline["travel_seconds"],current)
                if (record["paired_departure"] is not None and
                    record["leave_now_outcome"]=="NOT_PROPOSED"):
                    record["leave_now_outcome"]=_pair_score(
                        stock,country,item,
                        issued+baseline["travel_seconds"],current)
                if (record["routed_departure"] is not None and
                    record["leave_now_outcome"]=="NOT_PROPOSED"):
                    record["leave_now_outcome"]=_pair_score(
                        stock,country,item,
                        issued+baseline["travel_seconds"],current)
                if (record["prequential_departure"] is not None and
                    record["leave_now_outcome"]=="NOT_PROPOSED"):
                    record["leave_now_outcome"]=_pair_score(
                        stock,country,item,
                        issued+baseline["travel_seconds"],current)
                if (record["flight_horizon_departure"] is not None and
                    record["leave_now_outcome"]=="NOT_PROPOSED"):
                    record["leave_now_outcome"]=_pair_score(
                        stock,country,item,
                        issued+baseline["travel_seconds"],current)
                # Independent explicit-restock/depletion baseline from
                # observed V145 periods, including sparse bounded history.
                # It forecasts next stock P1..P16, not V128's arrival score.
                explicit=first_reachable_stock_cycles(key,new,asof=issued)
                record["explicit_status"]=explicit["status"]
                diagnosis=diagnose_window_failure(explicit)
                record["explicit_diagnostic_reason"]=diagnosis[
                    "reason_classification"]
                record["median_only_scenario_available"]=(
                    diagnosis["first_research_only_median_scenario"] is not None
                    and explicit["first_reachable"] is None)
                proposed=explicit["first_reachable"]
                if proposed is not None:
                    record["explicit_departure"]=proposed[
                        "earliest_departure_epoch"]
                    record["explicit_arrival"]=proposed["arrival_epoch"]
                    record["explicit_cycle_number"]=proposed["cycle_number"]
                    record["explicit_outcome"]=_pair_score(
                        stock,country,item,record["explicit_arrival"],current)
                    # Compare all three against the same leave-now timestamp.
                    record["leave_now_outcome"]=_pair_score(
                        stock,country,item,
                        issued+baseline["travel_seconds"],current)
                old_eligible=(
                    old["phase_onset"] is not None and
                    min(len(old["stocked_durations"]),
                        len(old["depleted_durations"]))>=MIN_PHASES
                )
                new_eligible=(
                    new["phase_onset"] is not None and
                    min(len(new["stocked_durations"]),
                        len(new["depleted_durations"]))>=MIN_PHASES
                )
                if not new_eligible:
                    record["comparison"]=(
                        "OBSERVED_HISTORY_SPARSE_OR_ONSET_UNKNOWN")
                    results.append(record)
                    continue
                record["recovered"]=not old_eligible
                if total_model_evals>=max_model_evals or item_model_evals>=per_item_budget:
                    record["comparison"]="NEW_ELIGIBLE_BUT_RESOURCE_LIMIT"
                    results.append(record)
                    continue
                total_model_evals+=1
                item_model_evals+=1
                curve=empirical_arrival_scores(new,key,asof=issued)
                choice=earliest_credible_for_country(curve,key)
                record["comparison"]=(
                    "RECOVERED_NEW_SCORING" if record["recovered"]
                    else "BOTH_MODEL_ELIGIBLE"
                )
                record["new_status"]=choice["status"]
                record["new_score"]=choice["score"]
                if choice["departure"] is not None:
                    record["new_departure"]=choice["departure"]
                    record["new_arrival"]=choice["arrival"]
                    onsets=new["observed_clean_restock_onsets"]
                    spacings=[b-a for a,b in zip(onsets,onsets[1:])]
                    if len(spacings)>=2:
                        cadence=int(statistics.median(spacings))
                        record["median_observed_restock_spacing_seconds"]=cadence
                        wait=choice["departure"]-issued
                        record["long_wait_vs_cadence"]=(
                            wait>max(900,2*cadence))
                    record["new_outcome"]=_pair_score(
                        stock,country,item,choice["arrival"],current)
                    if record["leave_now_outcome"]=="NOT_PROPOSED":
                        record["leave_now_outcome"]=_pair_score(
                            stock,country,item,
                            issued+baseline["travel_seconds"],current)
                results.append(record)
    episode_result=episode_audit(results)
    agg,by_item=_aggregate(results)
    total=sum(x["issued_hourly_samples"] for x in by_item.values())
    if total!=len(results):
        raise AssertionError("missing result cohort")
    return {
        "status":"READ_ONLY_ASOF_REPLAY_NOT_PROSPECTIVE_CERTIFICATION",
        "asof_epoch":current,
        "exact_item_roster":len(roster),
        "hourly_issued_cohorts":len(results),
        "monte_carlo_replayed":total_model_evals,
        "replay_cap":max_model_evals,
        "per_item_budget":per_item_budget,
        "summary":agg,
        "items":by_item,
        "issue_phase_episode_audit":episode_result,
        "no_writes":True,
        "orig_v128_site_or_worker_modified":False,
        "source_provider_freshness_certified":False,
        "backfill_provenance_frozen_at_original_issue":False,
        "real_player_trip_success_certified":False,
        "new_future_watch_freshly_reconfirmed":False,
    }


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--collector",type=Path,default=COLLECTOR)
    ap.add_argument("--sidecar",type=Path,default=SIDECAR)
    ap.add_argument("--days",type=int,default=1)
    ap.add_argument("--max-model-evals",type=int,default=MAX_MODEL_EVALS)
    args=ap.parse_args(argv)
    print(json.dumps(replay(collector=args.collector,sidecar=args.sidecar,
                            days=args.days,max_model_evals=args.max_model_evals),
                     indent=2,sort_keys=True))


if __name__=="__main__":
    main()
