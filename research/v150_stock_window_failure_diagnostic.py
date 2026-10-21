"""V150: Diagnose V148 'NO_CONSERVATIVE_REACHABLE_WINDOW' without
turning missing or uncertain stock confidence into actionable departures.

An item may have numerous fully observed restocks, yet low quartile of
stocked lifetime (Q25) can end *before* the high quartile of the next
restock-onset error (Q75) starts. This conservative-cross-quantile gate
sometimes rejects every window, particularly on a long flight (Japan).

Preserve all 16 future expected restock/depletion opportunities and show
what MEDIAN-only scenario might be reachable for research comparison, clearly
flagged NOT SAFE TO FLY. No fabricated actual stock guarantee or new user
recommendation. Pure and read-only; may be run on past-only V148 output.
"""
from __future__ import annotations

from collections import Counter
from research.v148_observed_earliest_stock_cycle import (
    GRACE_SECONDS, MAX_WAIT_SECONDS,
)


def diagnose_window_failure(v148):
    if (type(v148) is not dict or
        type(v148.get("issued_epoch")) is not int or
        type(v148.get("travel_seconds")) is not int or
        not isinstance(v148.get("projected_windows"), list) or
        len(v148["projected_windows"])>17):
        raise ValueError("invalid V148 window output")
    issue=v148["issued_epoch"]
    travel=v148["travel_seconds"]
    if issue<=0 or travel<=0:
        raise ValueError("invalid issue/flight")
    counts=Counter()
    exploratory=None
    examined=0
    for window in v148["projected_windows"]:
        examined+=1
        if any(type(window.get(field)) is not int for field in (
            "cycle_number","expected_start_epoch","late_start_epoch",
            "expected_end_epoch","early_end_epoch")):
            raise ValueError("untyped predicted window")
        if (window["expected_end_epoch"]<=window["expected_start_epoch"] or
            window["late_start_epoch"]<window["expected_start_epoch"] or
            window["early_end_epoch"]>window["expected_end_epoch"]):
            raise ValueError("internally inconsistent predicted window")
        conservative_open=(
            window["early_end_epoch"]-window["late_start_epoch"]>GRACE_SECONDS)
        if not conservative_open:
            counts["Q25_STOCK_LIFETIME_VS_Q75_RESTOCK_BANDS_DO_NOT_OVERLAP"]+=1
        else:
            counts["CONSERVATIVE_BANDS_OVERLAP"]+=1
        # This is an exploratory baseline for diagnosing overconservative
        # restock bands. It is NOT a forecast success probability.
        depart=max(issue,window["expected_start_epoch"]-travel)
        arrival=depart+travel
        median_possible=(
            arrival+GRACE_SECONDS<window["expected_end_epoch"] and
            depart<=issue+MAX_WAIT_SECONDS)
        if not median_possible:
            counts["MEDIAN_WINDOW_UNREACHABLE_BY_FLIGHT_OR_HORIZON"]+=1
            continue
        counts["MEDIAN_WINDOW_REACHABLE_NOT_CERTIFIED"]+=1
        if exploratory is None:
            exploratory={
                "cycle_number":window["cycle_number"],
                "window_type":window.get("type"),
                "research_only_departure_epoch":depart,
                "research_only_arrival_epoch":arrival,
                "research_only_wait_seconds":depart-issue,
                "early_stock_end_epoch":window["early_end_epoch"],
                "expected_stock_end_epoch":window["expected_end_epoch"],
                "late_restock_epoch":window["late_start_epoch"],
                "cross_quantile_bands_overlap":conservative_open,
                "not_actionable":True,
                "arrival_stock30_certified":False,
                "calibrated_probability":None,
                "why":"Median scenario only; stocked lifetime/restock uncertainty "
                      "may make this flight miss.",
            }
    if v148.get("first_reachable") is not None:
        classification="V148_ALREADY_HAS_CONSERVATIVE_PROPOSAL"
    elif not examined:
        classification="NO_PROJECTED_WINDOWS"
    elif exploratory is None:
        classification="NEITHER_CONSERVATIVE_NOR_MEDIAN_WINDOW_REACHABLE"
    elif counts["Q25_STOCK_LIFETIME_VS_Q75_RESTOCK_BANDS_DO_NOT_OVERLAP"]:
        classification="CONSERVATIVE_CROSS_QUANTILE_BANDS_EXCLUDE_MEDIAN_WINDOW"
    else:
        classification="MEDIAN_ONLY_WINDOW_BUT_OTHER_CONSERVATIVE_GATE"
    return {
        "item_key":v148.get("item_key"),
        "issued_epoch":issue,
        "model_status":v148.get("status"),
        "reason_classification":classification,
        "evaluated_window_count":examined,
        "quantile_gate_counts":dict(sorted(counts.items())),
        "first_research_only_median_scenario":exploratory,
        "conservative_model_actionable":False,
        "exploratory_scenario_actionable":False,
        "observed_game_stock_restock_proof":False,
        "forward_arrival_accuracy_proof":False,
    }
