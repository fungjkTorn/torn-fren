"""V166 shared read-only item-event -> per-player travel decision contract.

Input is the V163 event-first output for one item. Output is a deterministic
presentation contract suitable for the detailed graph, all-items dashboard
and future Travel Decisions page. This DOES NOT alter production or claim
stock-on-arrival success. All forecast timing is uncalibrated until prospective
as-issued and flight-arrival validation confirms otherwise.

All times are UTC POSIX seconds. No player API keys involved or accepted.
"""
from __future__ import annotations

import math


MAX_FORECAST_AGE_SECONDS=660
DEFAULT_MAX_HEARTBEAT_AGE_SECONDS=180
DEFAULT_GRACE_SECONDS=10
MAX_EVENTS_PER_ITEM=64
STATUS_WAIT="WAIT_FOR_ESTIMATED_DEPARTURE"
STATUS_ACTIVE="ESTIMATED_DEPARTURE_WINDOW_OPEN"
STATUS_NO_WINDOW="NO_REACHABLE_PREDICTED_WINDOW"
STATUS_ABSTAIN="MODEL_ABSTAIN"
STATUS_STALE="STALE_DATA"


def _epoch(n,field):
    if type(n) is not int or n<=0:
        raise ValueError("invalid "+field)
    return n


def _safe_epoch(n):
    return n if type(n) is int and n>0 else None


def build_item_travel_decision(
    forecast,*,now,player_flight_seconds=None,
    poll_age_seconds=None,max_poll_age_seconds=DEFAULT_MAX_HEARTBEAT_AGE_SECONDS,
    target_qty=30,grace_seconds=DEFAULT_GRACE_SECONDS
):
    """Pure, robust, user-specific presentation projection.

    Only V163's >=30 candidate phase model is available, so target_qty != 30
    explicitly abstains rather than inventing stock at a different threshold.

    Arrival reference = departure + player flight + grace, based solely on
    model-issued forecast and user travel duration. Return ALL future event
    records even if the earliest restock cannot be reached.
    """
    if not isinstance(forecast,dict):
        raise ValueError("forecast must be a mapping")
    _epoch(now,"now")
    issued=_epoch(forecast.get("asof_epoch"),"asof_epoch")
    if issued>now+15:
        raise ValueError("forecast issued in the future")
    base=forecast.get("flight_seconds")
    flight=base if player_flight_seconds is None else player_flight_seconds
    if type(flight) is not int or not 60<=flight<=86400:
        raise ValueError("invalid player flight duration")
    if type(grace_seconds) is not int or not 0<=grace_seconds<=120:
        raise ValueError("invalid arrival grace")
    if type(target_qty) is not int or not 1<=target_qty<=100000:
        raise ValueError("invalid target quantity")
    if type(max_poll_age_seconds) is not int or not 10<=max_poll_age_seconds<=3600:
        raise ValueError("invalid heartbeat policy")
    if poll_age_seconds is not None and (
        type(poll_age_seconds) is not int or poll_age_seconds<0):
        raise ValueError("invalid heartbeat age")
    key=forecast.get("item_key")
    if type(key) is not str or key.count(":")!=1:
        raise ValueError("invalid item key")
    raw=forecast.get("restock_events",[])
    if not isinstance(raw,list) or len(raw)>MAX_EVENTS_PER_ITEM:
        raise ValueError("invalid bounded event timeline")
    events=[]
    previous=0
    candidate=None
    for i,record in enumerate(raw):
        if not isinstance(record,dict):
            raise ValueError("invalid forecast event")
        center=_epoch(record.get("predicted_restock_epoch"),"predicted restock")
        low=_epoch(record.get("restock_early_epoch"),"early restock")
        high=_epoch(record.get("restock_late_epoch"),"late restock")
        stock_end=_epoch(record.get("predicted_stock_below_30_epoch"),"predicted stock end")
        if not low<=center<=high or not center<stock_end or center<=previous:
            raise ValueError("unsorted or inconsistent event times")
        previous=center
        raw_start=center-flight-grace_seconds
        first=max(now,raw_start)
        last=stock_end-flight-grace_seconds-1
        reachable=first<=last and first+flight+grace_seconds>=center
        arrival=first+flight+grace_seconds if reachable else None
        if reachable and not center<=arrival<stock_end:
            raise AssertionError("arrival is outside modeled stock phase")
        event={
            "index":i+1,
            "predicted_restock_epoch":center,
            "restock_early_epoch":low,
            "restock_late_epoch":high,
            "predicted_stock_below_30_epoch":stock_end,
            "estimated_departure_start_epoch":first if reachable else None,
            "estimated_latest_departure_epoch":last if reachable else None,
            "estimated_arrival_epoch":arrival,
            "flight_reachable":bool(reachable),
            "item_quantity_threshold":30,
            "calibration_state":"UNCALIBRATED",
            "forecast_horizon_seconds":center-issued,
            "model_proven_success":False,
            "reason":("ESTIMATED_STOCKED_PHASE_REACHABLE" if reachable
                      else "NOT_REACHABLE_WITH_PLAYER_FLIGHT"),
        }
        events.append(event)
        if reachable and candidate is None:
            candidate=event
    too_old=now-issued>MAX_FORECAST_AGE_SECONDS
    stale_poll=poll_age_seconds is None or poll_age_seconds>max_poll_age_seconds
    model_available=forecast.get("status")=="EVENT_TIMELINE_FORECAST_AVAILABLE"
    if target_qty!=30:
        status=STATUS_ABSTAIN
        reason="REQUESTED_THRESHOLD_NOT_SUPPORTED_BY_MODEL"
    elif stale_poll or too_old:
        status=STATUS_STALE
        reason="STALE_SOURCE_POLL" if stale_poll else "STALE_MODEL_FORECAST"
    elif not model_available:
        status=STATUS_ABSTAIN
        reason=str(forecast.get("status") or "MODEL_NO_FORECAST")
    elif candidate is None:
        status=STATUS_NO_WINDOW
        reason="NO_REACHABLE_RESTOCK_IN_FORECAST_HORIZON"
    elif candidate["estimated_departure_start_epoch"]<=now:
        status=STATUS_ACTIVE
        reason="MODELED_STOCKED_PHASE_RECONFIRM_BEFORE_TRAVEL"
    else:
        status=STATUS_WAIT
        reason="MODEL_DEPARTURE_NOT_YET_REACHED"
    # Do not publish an actionable clock when evidence is stale,
    # forecast missing, or target quantity unsupported.
    actionable=status in (STATUS_ACTIVE,STATUS_WAIT)
    chosen=candidate if actionable else None
    eta=(chosen["estimated_departure_start_epoch"]-now
         if chosen else None)
    return {
        "item_key":key,
        "asof_epoch":issued,
        "evaluated_at_epoch":now,
        "forecast_age_seconds":max(0,now-issued),
        "source_poll_age_seconds":poll_age_seconds,
        "player_flight_seconds":flight,
        "target_quantity":target_qty,
        "arrival_grace_seconds":grace_seconds,
        "status":status,
        "reason":reason,
        "estimated_departure_epoch":(chosen["estimated_departure_start_epoch"]
                                     if chosen else None),
        "estimated_departure_deadline_epoch":(
            chosen["estimated_latest_departure_epoch"] if chosen else None),
        "estimated_arrival_epoch":(chosen["estimated_arrival_epoch"]
                                  if chosen else None),
        "departure_countdown_seconds":eta,
        "selected_restock_event_index":(chosen["index"] if chosen else None),
        "forecast_events":events,
        "all_restock_events_preserved":len(events)==len(raw),
        "prediction_calibrated":False,
        "verified_arrival_stock_success_probability":None,
        "departure_recommendation_is_estimate":True,
        "no_automated_gameplay":True,
    }
