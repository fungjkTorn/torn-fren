"""V107: explicit, causal restock/depletion availability-window baseline.

Unlike V103/V106 score-threshold planning, this forecasts stock-state changes:
 - below 30: empirical time from prior threshold depletion to next restock;
 - at least 30: empirical duration from prior restock to depletion;
 - later cycles: recursively projected replenishment and availability windows.
Departure is computed from these time windows using V102 flight timing.

Research baseline, NOT a claimed champion. Uses only COMPLETED historic phases
whose closing event was observed <= query epoch. Excludes source-switch and
collection-gap crossings, abstains on unknown phase onset or thin samples, and
uses conditional survivor durations for the current censored phase.

Events detected in change-only stock observations are approximate and can be
late; YATA country-specific update ages were not recorded historically. The
confidence bands below are empirical duration percentiles, NOT calibrated
probabilities or verified exact restock instants.

Pure functions: no SQLite writes, imports of live services, requests or actions.
"""
from __future__ import annotations

import bisect
import math
import statistics
from dataclasses import dataclass
from typing import Sequence

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v102_restock_departure_bridge import (
    StockedWindowForecast,derive_departure_windows
)

MIN_QTY=30
MAX_STALE_STOCK_AGE=86400
MAX_WAIT=28800
MIN_COMPLETED_PHASES=5
MAX_PROJECTED_WINDOWS=4


@dataclass(frozen=True)
class StockObservation:
    epoch: int
    quantity: int
    source: str


def empirical_quantile(xs, p):
    """Non-interpolated sample quantile: never invent fractional durations."""
    if not xs or not 0<=p<=1:
        raise ValueError("no history or invalid percentile")
    vals=sorted(int(x) for x in xs)
    return vals[min(len(vals)-1,math.ceil(p*len(vals))-1)]


def completed_phases(
    observations: Sequence[StockObservation], *,
    asof: int, collection_gaps=(),
):
    """Extract completed ≥30 and <30 durations using only records <= asof.

    Discontinuous source segments are not spliced together. Every completed
    duration is closed by an as-of observation; ongoing phases are censored.
    Missing collector periods invalidate the crossing and its duration.
    """
    events=[]
    high_durations=[]
    low_durations=[]
    current=None
    last=None
    previous=None
    source=None

    def crossed_gap(a,b):
        return any(start<=b and (end is None or end>=a)
                   for start,end in collection_gaps)

    for obs in observations:
        if obs.epoch>asof:
            break
        if (type(obs.epoch) is not int or type(obs.quantity) is not int
            or obs.quantity<0 or not obs.source):
            continue
        flag=obs.quantity>=MIN_QTY
        if previous is not None and (
            obs.epoch<=previous.epoch or obs.source!=source
            or crossed_gap(previous.epoch,obs.epoch)):
            current=None
            last=None
        if current is None:
            current=flag
            last=None
        elif current!=flag:
            # This transition timestamp denotes the *observed* crossing.
            # If a matching start transition has been observed within the
            # uninterrupted provider segment, the completed duration is valid.
            if last is not None and obs.epoch>last:
                if current:
                    high_durations.append(obs.epoch-last)
                else:
                    low_durations.append(obs.epoch-last)
            kind="DEPLETED_BELOW_30" if not flag else "REPLENISHED_TO_30"
            events.append((obs.epoch,kind,obs.quantity))
            last=obs.epoch
            current=flag
        previous=obs
        source=obs.source
    phase=("HIGH" if current is True else "LOW"
           if current is False else "UNKNOWN")
    return {
        "phase":phase,
        "phase_onset":last,
        "last_observation":previous,
        "stocked_durations":high_durations,
        "depleted_durations":low_durations,
        "observed_transitions":events,
        "asof":asof,
    }


def next_windows(
    item_key: str,
    observations: Sequence[StockObservation], *,
    asof: int, collection_gaps=(),
    min_phases: int=MIN_COMPLETED_PHASES,
    max_windows: int=MAX_PROJECTED_WINDOWS,
):
    """Project future threshold windows from completed past restock cycles.

    Conservative bounds: upper-quartile replenishment delay and lower-
    quartile stocked duration. Both based on completed historical periods.
    """
    if (type(asof) is not int or not 1<=min_phases<=1000
        or not 1<=max_windows<=MAX_PROJECTED_WINDOWS
        or not isinstance(item_key,str) or ":" not in item_key
        or item_key.split(":",1)[0] not in TRAVEL_SECONDS):
        raise ValueError("invalid research baseline parameters")
    history=completed_phases(
        observations,asof=asof,collection_gaps=collection_gaps)
    last=history["last_observation"]
    common={
        "asof":asof,"item_key":item_key,
        "past_completed_stocked_phases":len(history["stocked_durations"]),
        "past_completed_depleted_phases":len(history["depleted_durations"]),
        "current_observed_phase":history["phase"],
        "explicit_threshold_window_model":True,
        "country_provider_age_verified":False,
        "independent_restock_events_verified":False,
        "recommends_player_action":False,
        "windows":[],
    }
    if last is None or last.epoch>asof or asof-last.epoch>MAX_STALE_STOCK_AGE:
        return dict(common,status="ABSTAIN_STALE_OR_MISSING_STOCK")
    if history["phase_onset"] is None:
        return dict(common,status="ABSTAIN_PHASE_START_UNKNOWN")
    high=history["stocked_durations"]
    low=history["depleted_durations"]
    if min(len(high),len(low))<min_phases:
        return dict(common,status="ABSTAIN_INSUFFICIENT_COMPLETED_CYCLES")
    active_from=int(history["phase_onset"])
    age=asof-active_from
    if age<0:
        raise AssertionError("historical phase start after query")

    median_high=empirical_quantile(high,.50)
    shortest_high=empirical_quantile(high,.25)
    median_low=empirical_quantile(low,.50)
    longest_low=empirical_quantile(low,.75)
    projected=[]

    if history["phase"]=="HIGH":
        surviving=[d for d in high if d>age]
        if len(surviving)<min_phases:
            return dict(common,status="ABSTAIN_NO_STOCK_SURVIVOR_ANALOGS")
        high_until=active_from+empirical_quantile(surviving,.50)
        cautious_until=active_from+empirical_quantile(surviving,.25)
        if high_until>asof:
            projected.append((asof,high_until,asof,cautious_until))
        future_depletion=high_until
    elif history["phase"]=="LOW":
        surviving=[d for d in low if d>age]
        if len(surviving)<min_phases:
            return dict(common,status="ABSTAIN_NO_RESTOCK_SURVIVOR_ANALOGS")
        first_onset=active_from+empirical_quantile(surviving,.50)
        late_onset=active_from+empirical_quantile(surviving,.75)
        first_end=first_onset+median_high
        earliest_end=first_onset+shortest_high
        projected.append((first_onset,first_end,late_onset,earliest_end))
        future_depletion=first_end
    else:
        return dict(common,status="ABSTAIN_UNKNOWN_STOCK_PHASE")

    while len(projected)<max_windows:
        onset=future_depletion+median_low
        late_onset=future_depletion+longest_low
        end=onset+median_high
        earliest_end=onset+shortest_high
        projected.append((onset,end,late_onset,earliest_end))
        future_depletion=end

    for onset,end,late,early in projected:
        if end<=onset or onset>asof+MAX_WAIT+TRAVEL_SECONDS[
                item_key.split(":",1)[0]]:
            continue
        bounds_possible=late<early
        forecast=StockedWindowForecast(
            item_key=item_key,
            model_id="v107_empirical_threshold_cycle_baseline",
            issued_at=asof,stock_as_of=last.epoch,
            expected_start=int(onset),expected_end=int(end),
            late_start=int(late) if bounds_possible else None,
            early_end=int(early) if bounds_possible else None,
        )
        departures=derive_departure_windows(forecast,now=asof)
        common["windows"].append({
            "expected_stocked_start":int(onset),
            "expected_drop_below_30":int(end),
            "pessimistic_restock_onset":int(late),
            "pessimistic_depletion":int(early),
            "conservative_interval_exists":bounds_possible,
            "earliest_expected_departure":departures[
                "earliest_expected_departure"],
            "earliest_conservative_departure":departures[
                "earliest_conservative_departure"],
            "expected_arrival":departures["expected_arrival"],
        })
    common["status"]=(
        "FORECAST_AVAILABLE" if any(
            w["earliest_expected_departure"] is not None
            for w in common["windows"])
        else "ABSTAIN_NO_FLIGHT_CAN_REACH_PREDICTED_WINDOW")
    return common
