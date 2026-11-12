"""V102 research-only conversion: predicted stocked windows -> departure times.

The current champion planners often score arrival availability across a delay
grid, then select one preferred point; they do NOT consistently return a
forecast of the restock/depletion boundary. V102 is a pure, low-cost bridge:
  1. When a specialist models item quantity >=30 as an explicit availability
     interval, derive the earliest *expected* departure and a later
     *conservative-estimate* departure from the interval endpoints.
  2. When a specialist offers only an availability-score curve, select its
     earliest eligible arrival point and best-scoring point on the SAME curve.
     The raw model score is NOT a calibrated probability of game availability.
No VM, collector, network, model, or gameplay actions are invoked.

Time calculations use epoch seconds and pinned model flight durations. An
arrival exactly at the predicted stocked-window end is NOT considered stocked.
Bounds are model estimates, NOT mathematically guaranteed game outcomes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from research.plushie_champions.common import TRAVEL_SECONDS

MIN_QTY=30
GRACE=10
MAX_WAIT=8*3600


@dataclass(frozen=True)
class StockedWindowForecast:
    """Future interval when >=30 is predicted.

    expected_start: predicted earliest >=30-stock moment
    expected_end: predicted earliest moment predicted to fall below 30
    late_start: optional later-estimate onset accounting for uncertainty
    early_end: optional earlier-estimate depletion accounting for uncertainty

    If bounds absent, no safer departure is calculated, rather than
    pretending the central prediction is certain.
    """
    item_key: str
    model_id: str
    issued_at: int
    stock_as_of: int
    expected_start: int
    expected_end: int
    late_start: int | None = None
    early_end: int | None = None
    model_generated: bool = True


@dataclass(frozen=True)
class ArrivalScore:
    """Forecast made at issue time for a possible arrival (not truth data)."""
    arrival_epoch: int
    raw_availability_score: float
    predicted_quantity: int | None = None


def _flight(item_key: str):
    if not isinstance(item_key,str) or ":" not in item_key:
        raise ValueError("invalid item key")
    country,item=item_key.split(":",1)
    if country not in TRAVEL_SECONDS or not item:
        raise ValueError("unknown country/item")
    return TRAVEL_SECONDS[country]


def _departure_for_window(now: int, flight: int, start: int, end: int):
    """Depart at first arrival in [start,end), or abstain if too late."""
    departure=max(now,start-flight)
    if departure+flight>=end or departure>now+MAX_WAIT:
        return None
    return departure


def derive_departure_windows(forecast: StockedWindowForecast, *, now: int):
    """Convert restock/depletion forecast to earliest plausible flight.

    Conservatism means *using later onset + earlier depletion*, not claiming
    stock is guaranteed. The [+10s] observational grace criterion is an
    evaluation contract only, not a reason to recommend arriving before stock.
    """
    if type(now) is not int or not isinstance(forecast,StockedWindowForecast):
        raise ValueError("invalid departure request")
    flight=_flight(forecast.item_key)
    epochs=(forecast.issued_at,forecast.stock_as_of,
            forecast.expected_start,forecast.expected_end)
    if any(type(t) is not int for t in epochs):
        raise ValueError("invalid forecast timestamps")
    if not forecast.model_id or not forecast.model_generated:
        raise ValueError("not a model forecast")
    if not forecast.stock_as_of<=forecast.issued_at<=now:
        raise ValueError("future evidence or inconsistent issue clock")
    if forecast.expected_end<=forecast.expected_start:
        raise ValueError("impossible forecasted stocked interval")
    if forecast.late_start is not None and (
        type(forecast.late_start) is not int or
        forecast.late_start<forecast.expected_start):
        raise ValueError("late onset boundary precedes expected")
    if forecast.early_end is not None and (
        type(forecast.early_end) is not int or
        forecast.early_end>forecast.expected_end):
        raise ValueError("early depletion boundary follows expected")
    if (forecast.late_start is None)!=(forecast.early_end is None):
        raise ValueError("need both uncertainty boundaries for conservative estimate")

    expected=_departure_for_window(
        now,flight,forecast.expected_start,forecast.expected_end)
    conservative=None
    if forecast.late_start is not None:
        conservative=_departure_for_window(
            now,flight,forecast.late_start,forecast.early_end)

    return {
        "item_key":forecast.item_key,
        "model_id":forecast.model_id,
        "flight_seconds":flight,
        "predicted_stocked_start":forecast.expected_start,
        "predicted_stocked_end":forecast.expected_end,
        "earliest_expected_departure":expected,
        "expected_arrival":None if expected is None else expected+flight,
        "expected_latest_departure_exclusive":forecast.expected_end-flight,
        "earliest_conservative_departure":conservative,
        "conservative_arrival":None if conservative is None else conservative+flight,
        "conservative_window_available":forecast.late_start is not None,
        "mode":"PREDICTED_STOCK_WINDOW",
        "verified_game_stock":False,
        "guaranteed":False,
        "reason":("MISSED_OR_UNREACHABLE_EXPECTED_WINDOW" if expected is None
                  else "MODEL_ESTIMATE_NOT_GUARANTEE"),
    }


def derive_from_arrival_scores(
    item_key: str, scores: Sequence[ArrivalScore], *,
    now: int, issued_at: int, stock_as_of: int,
    minimum_raw_score: float,
    min_consecutive_points: int = 1,
    step_seconds: int = 300,
):
    """Select earliest and strongest valid departures from one score grid.

    minimum_raw_score is an EXPLICIT research policy parameter, and raw scores
    must NOT be described as calibrated probabilities. It requires no extra
    forecasting, but does not infer restock timing where unavailable.
    """
    flight=_flight(item_key)
    if (type(now) is not int or type(issued_at) is not int
        or type(stock_as_of) is not int
        or not stock_as_of<=issued_at<=now
        or not isinstance(minimum_raw_score,(int,float))
        or isinstance(minimum_raw_score,bool)
        or not math.isfinite(minimum_raw_score)
        or not 0<=minimum_raw_score<=1
        or type(step_seconds) is not int or step_seconds<=0
        or type(min_consecutive_points) is not int
        or not 1<=min_consecutive_points<=30):
        raise ValueError("invalid score policy or timestamps")
    # Normalize: only past-issued forecast output and positive model scores.
    curve=[]
    seen=set()
    for p in scores:
        if not isinstance(p,ArrivalScore):
            raise ValueError("invalid scored arrival")
        arrival=p.arrival_epoch
        score=p.raw_availability_score
        if type(arrival) is not int or (
            not isinstance(score,(float,int)) or isinstance(score,bool)
            or not math.isfinite(score) or not 0<=score<=1):
            raise ValueError("invalid scored arrival values")
        if p.predicted_quantity is not None and (
            type(p.predicted_quantity) is not int or p.predicted_quantity<0):
            raise ValueError("invalid projected quantity")
        if arrival in seen:
            raise ValueError("duplicate arrival grid point")
        seen.add(arrival)
        departure=arrival-flight
        if not now<=departure<=issued_at+MAX_WAIT:
            continue
        curve.append((arrival,float(score),p.predicted_quantity))
    curve.sort()
    passing=[False]*len(curve)
    for i,(arrival,raw,quantity) in enumerate(curve):
        # A model quantity estimate below 30 trumps its availability score.
        passing[i]=(raw>=minimum_raw_score
                    and (quantity is None or quantity>=MIN_QTY))
    qualified=[]
    for i in range(len(curve)):
        if not passing[i]:
            continue
        # A plateau must have at least N adjacent grid points; this is an
        # optional stability filter, not a statistical confidence guarantee.
        j=i
        while j<len(curve) and passing[j] and (
            j==i or curve[j][0]-curve[j-1][0]==step_seconds):
            j+=1
        if j-i>=min_consecutive_points:
            qualified.extend(curve[i:j])
        if j>i:
            for skip in range(i+1,j):
                passing[skip]=False
    if not qualified:
        return {
            "item_key":item_key,"mode":"ARRIVAL_SCORE_CURVE",
            "earliest":None,"best_score":None,"raw_score_calibrated":False,
            "qualifying_grid_points":0,"reason":"NO_ELIGIBLE_SCORE_WINDOW",
        }
    # The earliest candidate is the FIRST qualifying arrival grid point,
    # not the middle of the highest-scoring region.
    first=qualified[0]
    best=max(qualified,key=lambda x:(x[1],x[2] if x[2] is not None else -1,-x[0]))
    def pack(p):
        return {"departure_epoch":p[0]-flight,
                "arrival_epoch":p[0],
                "raw_model_availability_score":p[1],
                "predicted_quantity":p[2]}
    return {
        "item_key":item_key,"mode":"ARRIVAL_SCORE_CURVE",
        "earliest":pack(first),"best_score":pack(best),
        "raw_score_calibrated":False,
        "qualifying_grid_points":len(qualified),
        "minimum_raw_score_policy":float(minimum_raw_score),
        "reason":"MODEL_SCORE_ONLY_NOT_A_PREDICTED_RESTOCK_BOUNDARY",
    }
