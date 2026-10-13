"""V151 read-only research departure candidates using deterministic whole cycles.

The V148 baseline combines independent "late restock" and "early depletion"
quantiles; on short stocked phases the interval can be empty even with actual
completed cycles. V151 instead simulates full observed LOW/HIGH trajectories,
including fully observed stock starts/ends surviving benign provider changes
(V145). All features are from event timestamps <= issue. It scores >=30 stock
on arrival at departure+country flight+10-second grace.

Unlike V128's seed+issue_epoch, the PRNG is keyed to the completed historical
phase data and last observation, so five-minute re-issues on identical history
do not arbitrarily re-roll scenarios. Conditioning on the *current phase age*
still legitimately changes the projection.

This is NOT a calibrated probability, confirmed game stock, actual flight
decision, or production implementation. It deliberately preserves low-sample
warnings, score-based abstentions and per-country coverage uncertainty.
"""
from __future__ import annotations

import bisect
import hashlib
import random
import statistics

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v145_provider_continuous_phases import observed_cycle_evidence_tier

THRESHOLD=30
STEP_SECONDS=300
GRACE_SECONDS=10
EIGHT_HOURS=28800
DEFAULT_SCENARIOS=96
SCENARIO_MAX=256
MAX_TRANSITIONS_PER_PATH=512
MIN_SCORE_FLOOR=.60
MAX_SOURCE_AGE=86400


def _median(xs):
    return int(statistics.median(xs)) if xs else None


def _stable_seed(key, periods):
    last=periods["last_observation"]
    state=(
        key,periods["phase"],periods["phase_onset"],
        last.epoch,last.quantity,last.source,
        tuple(sorted(periods["stocked_durations"])),
        tuple(sorted(periods["depleted_durations"])),
    )
    return int.from_bytes(hashlib.blake2b(
        repr(state).encode("utf8"),digest_size=8).digest(),"big")


def _score_policy(scores, *, asof, flight, floor, lifetime_sample,
                  observed_cadence):
    """Earliest two adjacent qualified 5-min bins, no arbitrary max-score wait.

    If NOW is supported by its own arrival-stock scenario bin, never impose
    an artificial 5-minute waiting floor merely to find two adjacent bins.
    Future single-bin opportunities remain NONACTIONABLE watches because
    their narrow windows require very careful reconfirmation.
    """
    # Earliest means NOW when its own arrival grid bin qualifies. Waiting
    # for two adjacent bins must never discard an actually supported
    # immediate-arrival opportunity on a short-lived stocked cycle.
    if scores and scores[0]>=floor:
        immediate={
            "departure_epoch":asof,
            "arrival_epoch":asof+flight,
            "wait_seconds":0,
            "scenario_stock_fraction":round(scores[0],6),
            "two_adjacent_5min_bins":(
                len(scores)>1 and scores[1]>=floor),
            "provisional":True,
            "stock_at_arrival_verified":False,
            "scenario_fraction_calibrated_probability":False,
            "cadence_warning":None,
            "needs_reconfirmation":False,
            "status":"RESEARCH_NOW",
        }
        return immediate,{
            "reason":"EARLIEST_IMMEDIATE_SUPPORTED_BIN",
            "short_window_single_bin":not immediate[
                "two_adjacent_5min_bins"],
            "long_wait_over_multiple_observed_cycles":False,
        }
    candidate=None
    for i,score in enumerate(scores):
        if score < floor:
            continue
        if i+1 >= len(scores) or scores[i+1] < floor:
            continue
        candidate={
            "departure_epoch":asof+i*STEP_SECONDS,
            "arrival_epoch":asof+i*STEP_SECONDS+flight,
            "wait_seconds":i*STEP_SECONDS,
            "scenario_stock_fraction":round(score,6),
            "two_adjacent_5min_bins":True,
            "provisional":True,
            "stock_at_arrival_verified":False,
            "scenario_fraction_calibrated_probability":False,
        }
        break
    if candidate is None:
        possible=[
            (i,s) for i,s in enumerate(scores) if s>=floor
        ]
        return None,{
            "reason":"NO_TWO_CONSECUTIVE_SUPPORTED_ARRIVAL_BINS",
            "single_bins_above_gate":len(possible),
            "short_stocked_phases_may_not_survive_five_minutes":(
                lifetime_sample is not None
                and lifetime_sample < STEP_SECONDS),
            "first_single_bin_delay_seconds":(
                possible[0][0]*STEP_SECONDS if possible else None),
        }
    wait=candidate["wait_seconds"]
    long=(observed_cadence is not None and
          wait>max(900,2*observed_cadence))
    candidate["cadence_warning"]=(
        "LONG_WAIT_RECHECK_NEARER_RESTOCKS" if long else None)
    candidate["needs_reconfirmation"]=wait>STEP_SECONDS
    candidate["status"]=(
        "RESEARCH_NOW" if wait==0 else
        "RESEARCH_SOON_RECONFIRM" if wait<=STEP_SECONDS else
        "RESEARCH_WATCH_RECONFIRM")
    return candidate,{"reason":"EARLIEST_SUPPORTED_TWO_BIN_WINDOW",
                       "long_wait_over_multiple_observed_cycles":long}


def stable_earliest_departure(item_key, periods, *, asof,
                              scenarios=DEFAULT_SCENARIOS,
                              score_floor=MIN_SCORE_FLOOR):
    """Forecast on an eight-hour 5-min departure grid, research only."""
    if (not isinstance(item_key,str) or item_key.count(":")!=1
        or type(asof) is not int or asof<=0
        or type(scenarios) is not int or not 1<=scenarios<=SCENARIO_MAX
        or not isinstance(score_floor,(int,float)) or isinstance(score_floor,bool)
        or not .01<=score_floor<=1.0
        or not isinstance(periods,dict)):
        raise ValueError("invalid candidate input")
    country,item=item_key.split(":",1)
    if country not in TRAVEL_SECONDS or not item:
        raise ValueError("unrecognized flight item")
    flight=TRAVEL_SECONDS[country]
    high=periods.get("stocked_durations")
    low=periods.get("depleted_durations")
    last=periods.get("last_observation")
    onset=periods.get("phase_onset")
    phase=periods.get("phase")
    if not isinstance(high,list) or not isinstance(low,list):
        raise ValueError("missing bounded histories")
    if len(high)+len(low)>10000 or any(
        type(v) is not int or v<=0 for v in high+low
    ):
        raise ValueError("invalid bounded phase length")
    tier=observed_cycle_evidence_tier(periods)
    default={
        "status":"INSUFFICIENT_OBSERVED_BOUNDED_HISTORY",
        "item_key":item_key,
        "issued_epoch":asof,
        "flight_seconds":flight,
        "history_tier":tier["tier"],
        "completed_stocked_periods":len(high),
        "completed_depleted_periods":len(low),
        "observed_start_end_cycles_accepted":True,
        "country_provider_freshness_verified":False,
        "simulation_fraction_not_calibrated":True,
        "game_stock30_at_arrival_verified":False,
        "forward_performance_untested":True,
        "replan_by_epoch":asof+STEP_SECONDS,
        "first_reachable":None,
        "secondary_research_signal":None,
        "first_next_restock_onset_median_seconds":None,
        "median_observed_restock_cadence_seconds":None,
        "score_now":None,
        "score_bins":[],
        "diagnostic":None,
    }
    if not high or not low:
        return default
    if (last is None or type(last.epoch) is not int
        or last.epoch>asof or asof-last.epoch>MAX_SOURCE_AGE
        or phase not in ("HIGH","LOW")
        or type(onset) is not int or onset>asof):
        default["status"]="CURRENT_PHASE_OR_SOURCE_UNKNOWN"
        return default
    if any(not isinstance(v,int) or isinstance(v,bool) for v in
           (last.quantity,last.epoch)):
        raise ValueError("invalid last collector state")
    if (last.quantity>=THRESHOLD)!=(phase=="HIGH"):
        default["status"]="INCONSISTENT_LAST_STOCK_PHASE"
        return default
    age=asof-onset
    current=high if phase=="HIGH" else low
    surviving=[d-age for d in current if d>age]
    if not surviving:
        default["status"]="NO_HISTORICAL_SURVIVAL_ANALOG"
        return default
    onsets=periods.get("observed_clean_restock_onsets",[])
    if not isinstance(onsets,list):
        raise ValueError("invalid observed restock events")
    if len(onsets)>=3:
        spacings=[b-a for a,b in zip(onsets,onsets[1:])
                  if type(a) is int and type(b) is int and b>a]
        if len(spacings)>=2:
            default["median_observed_restock_cadence_seconds"]=_median(spacings)
    rng=random.Random(_stable_seed(item_key,periods))
    bins=EIGHT_HOURS//STEP_SECONDS+1
    arrivals=[flight+GRACE_SECONDS+i*STEP_SECONDS for i in range(bins)]
    scores=[0]*bins
    first_next_restocks=[]
    max_arrival=arrivals[-1]
    all_high=tuple(high)
    all_low=tuple(low)
    for _ in range(scenarios):
        position=rng.choice(surviving)
        state=phase
        stocked_starts=[]
        stocked_ends=[]
        if phase=="HIGH":
            stocked_starts.append(0)
            stocked_ends.append(position)
        first_restock=None
        loops=0
        while position<=max_arrival and loops<MAX_TRANSITIONS_PER_PATH:
            loops+=1
            state="HIGH" if state=="LOW" else "LOW"
            duration=rng.choice(all_high if state=="HIGH" else all_low)
            if state=="HIGH":
                if first_restock is None:
                    first_restock=position
                stocked_starts.append(position)
                stocked_ends.append(position+duration)
            position+=duration
        if position<=max_arrival:
            raise RuntimeError("insufficient scenario transition budget")
        if first_restock is not None:
            first_next_restocks.append(int(first_restock))
        for i,arrival in enumerate(arrivals):
            pos=bisect.bisect_right(stocked_starts,arrival)-1
            if pos>=0 and arrival<stocked_ends[pos]:
                scores[i]+=1
    fractions=[v/scenarios for v in scores]
    default["score_now"]=round(fractions[0],6)
    default["score_bins"]=[round(v,6) for v in fractions]
    default["scenario_count"]=scenarios
    default["first_next_restock_onset_median_seconds"]=_median(first_next_restocks)
    winner,reason=_score_policy(
        fractions,asof=asof,flight=flight,floor=score_floor,
        lifetime_sample=_median(high),
        observed_cadence=default["median_observed_restock_cadence_seconds"])
    default["diagnostic"]=reason
    if winner:
        default["first_reachable"]=winner
        default["status"]=(
            "LONG_WAIT_NEEDS_NEARER_CYCLE_AUDIT"
            if winner["cadence_warning"] else
            "PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE"
        )
    else:
        default["status"]="NO_TWO_BIN_SUPPORTED_DEPARTURE"
        # Preserve the earliest one-bin result as non-actionable research,
        # especially on very short-lived stocked windows.
        if reason["first_single_bin_delay_seconds"] is not None:
            default["secondary_research_signal"]={
                "first_one_bin_delay_seconds":reason[
                    "first_single_bin_delay_seconds"],
                "not_actionable":True,
                "why":"No second adjacent 5-minute arrival bin passes the "
                      "scenario floor; stock may disappear very quickly.",
            }
    return default
