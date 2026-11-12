"""V148: explicit next >=30 stock windows from VALID V145 observed periods.

Research-only transparent restock/depletion timing baseline for the V2 graph.
DOES NOT claim a calibrated player flight probability; does not install on
website or call Torn. Answers first forecast window the flight can reach, and
continues through frequent future cycles (up to 16), rather than incorrectly
stopping at 3-4 cycles when flights take 2-3+ hours.

All model features are computed from completed observed <= as-of transitions,
preserved across benign data-provider switches per V145. Future game events
are never consulted. Restock interval quantiles are NOT calibrated guarantees.
"""
from __future__ import annotations

import statistics

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v107_explicit_restock_cycle_baseline import empirical_quantile
from research.v145_provider_continuous_phases import observed_cycle_evidence_tier

MAX_FUTURE_CYCLES=16
MAX_WAIT_SECONDS=8*3600
MAX_REPLAN_SECONDS=300
GRACE_SECONDS=10
MIN_STOCK=30


def first_reachable_stock_cycles(item_key, periods, *, asof,
                                 max_cycles=MAX_FUTURE_CYCLES):
    if (type(asof) is not int or asof<=0
        or type(max_cycles) is not int or not 1<=max_cycles<=MAX_FUTURE_CYCLES
        or not isinstance(item_key,str) or item_key.count(":")!=1):
        raise ValueError("invalid proposal parameters")
    country,item=item_key.split(":",1)
    if country not in TRAVEL_SECONDS or not item:
        raise ValueError("unknown flight")
    if not isinstance(periods,dict):
        raise ValueError("missing periods")
    flight=TRAVEL_SECONDS[country]
    high=periods.get("stocked_durations")
    low=periods.get("depleted_durations")
    phase=periods.get("phase")
    onset=periods.get("phase_onset")
    last=periods.get("last_observation")
    if not isinstance(high,list) or not isinstance(low,list):
        raise ValueError("missing history arrays")
    tier=observed_cycle_evidence_tier(periods)
    common={
        "item_key":item_key,"issued_epoch":asof,"travel_seconds":flight,
        "recheck_by_epoch":asof+MAX_REPLAN_SECONDS,
        "min_stock_on_arrival":MIN_STOCK,
        "historical_evidence_tier":tier["tier"],
        "completed_stocked_windows":len(high),
        "completed_depleted_windows":len(low),
        "provider_freshness_verified":False,
        "calibrated_stock30_probability":None,
        "safe_to_fly_certified":False,
        "projected_windows":[],
        "first_reachable":None,
        "skipped_cycles_by_reason":{},
        "status":"NO_ENOUGH_BOUNDED_HISTORY",
    }
    if not high or not low:
        return common
    if (last is None or type(last.epoch) is not int or
        last.epoch>asof or asof-last.epoch>86400 or
        onset is None or type(onset) is not int or
        onset>asof or phase not in ("HIGH","LOW")):
        common["status"]="CURRENT_STATE_ONSET_NOT_VERIFIABLE"
        return common
    if len(high)+len(low)>100000:
        raise ValueError("unbounded historical arrays")
    age=asof-onset
    # Only completed, observed period lengths. We do not invent durations
    # from missing/reconstructed unobserved stock events.
    high50=empirical_quantile(high,.50)
    high25=empirical_quantile(high,.25)
    low50=empirical_quantile(low,.50)
    low75=empirical_quantile(low,.75)
    if min(high50,high25,low50,low75)<=0:
        raise ValueError("invalid duration")
    windows=[]
    if phase=="HIGH":
        surviving=[d for d in high if d>age]
        if not surviving:
            common["status"]="CURRENT_STOCK_SURVIVAL_UNKNOWN"
            return common
        # Current stock has already begun. It is not a predicted NEXT
        # restock. Preserve separately for possible leave-now arrival.
        current_end=asof+empirical_quantile([d-age for d in surviving],.50)
        current_early_end=asof+empirical_quantile(
            [d-age for d in surviving],.25)
        windows.append({
            "cycle_number":0,"type":"CURRENT_STOCK_NOT_NEW_RESTOCK",
            "expected_start_epoch":asof,
            "late_start_epoch":asof,
            "expected_end_epoch":current_end,
            "early_end_epoch":current_early_end,
        })
        prior_end=current_end
        first_next=prior_end+low50
    else:
        surviving=[d for d in low if d>age]
        if not surviving:
            common["status"]="CURRENT_DEPLETION_SURVIVAL_UNKNOWN"
            return common
        first_next=asof+empirical_quantile(
            [d-age for d in surviving],.50)
    for n in range(1,max_cycles+1):
        start=first_next if n==1 else prior_end+low50
        late_start=start+(low75-low50)
        end=start+high50
        early_end=start+high25
        windows.append({
            "cycle_number":n,"type":"PROJECTED_NEW_RESTOCK",
            "expected_start_epoch":start,
            "late_start_epoch":late_start,
            "expected_end_epoch":end,
            "early_end_epoch":early_end,
        })
        prior_end=end
        if start>asof+MAX_WAIT_SECONDS+flight:
            break
    skipped={}
    candidate=None
    for window in windows:
        # Even a conservative early stocked lifetime must extend BEYOND
        # the late restock bound, otherwise never emit misleading GO.
        late=window["late_start_epoch"]
        end=window["early_end_epoch"]
        if end-late<=GRACE_SECONDS:
            reason="UNCERTAINTY_WINDOWS_DO_NOT_OVERLAP"
        else:
            departure=max(asof, late-flight)
            latest=end-flight-GRACE_SECONDS
            if departure>latest:
                reason="FLIGHT_CANNOT_REACH_THIS_CYCLE"
            elif departure>asof+MAX_WAIT_SECONDS:
                reason="BEYOND_EIGHT_HOUR_DEPARTURE_HORIZON"
            else:
                reason=None
                item_window={
                    **window,
                    "earliest_departure_epoch":departure,
                    "latest_departure_epoch":latest,
                    "arrival_epoch":departure+flight,
                    "wait_seconds":departure-asof,
                    "provisional":True,
                    "stock_ge_30_on_arrival_verified":False,
                    "departure_status":(
                        "RESEARCH_LEAVE_NOW" if departure==asof
                        else "RESEARCH_DEPART_SOON" if departure-asof<=300
                        else "RESEARCH_WATCH_RECONFIRM"
                    ),
                }
                if candidate is None:
                    candidate=item_window
        if reason:
            skipped[reason]=skipped.get(reason,0)+1
    common["projected_windows"]=windows
    common["first_reachable"]=candidate
    common["skipped_cycles_by_reason"]=skipped
    if candidate:
        common["status"]="PROVISIONAL_FIRST_REACHABLE_STOCK_WINDOW"
        # Compare ONLY with actual observed restock onsets, never infer
        # a 30-minute cadence from the catalog/item name.
        onsets=periods.get("observed_clean_restock_onsets",[])
        if len(onsets)>=3:
            cadence=int(statistics.median([
                b-a for a,b in zip(onsets,onsets[1:])
            ]))
            common["observed_median_restock_cadence_seconds"]=cadence
            common["long_wait_despite_short_cadence"]=(
                candidate["wait_seconds"]>max(900,2*cadence))
        else:
            common["observed_median_restock_cadence_seconds"]=None
            common["long_wait_despite_short_cadence"]=False
        if common["long_wait_despite_short_cadence"]:
            common["status"]="LONG_WAIT_CHECK_NEARER_RESTOCKS"
    else:
        common["status"]="NO_CONSERVATIVE_REACHABLE_WINDOW"
    return common
