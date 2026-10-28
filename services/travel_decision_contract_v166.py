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


MAX_FORECAST_AGE_SECONDS=300
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
    forecast, *, now, player_flight_seconds=None,
    poll_age_seconds=None, max_poll_age_seconds=DEFAULT_MAX_HEARTBEAT_AGE_SECONDS,
    target_qty=30, grace_seconds=DEFAULT_GRACE_SECONDS,
    arrival_policy="expected",
):
    """Issue-pinned restock -> first reachable configured-stock arrival.

    Legacy forecasts use >=30; other targets require matching forecast metadata.
    Physical 0->positive events are kept even when purchase-window estimation
    abstains. Arrival is the *actual landing epoch*; the ten seconds after
    landing are an additional stock-survival requirement, not permission to
    land before restock. Future departures require fresh reconfirmation.
    """
    if not isinstance(forecast, dict):
        raise ValueError("forecast must be a mapping")
    _epoch(now, "now")
    issued = _epoch(forecast.get("asof_epoch"), "asof_epoch")
    if issued > now + 15:
        raise ValueError("forecast issued in the future")
    flight = (forecast.get("flight_seconds") if player_flight_seconds is None
              else player_flight_seconds)
    if type(flight) is not int or not 60 <= flight <= 86400:
        raise ValueError("invalid player flight duration")
    if type(grace_seconds) is not int or not 0 <= grace_seconds <= 120:
        raise ValueError("invalid arrival grace")
    if type(target_qty) is not int or not 1 <= target_qty <= 100000:
        raise ValueError("invalid target quantity")
    if type(max_poll_age_seconds) is not int or not 10 <= max_poll_age_seconds <= 3600:
        raise ValueError("invalid heartbeat policy")
    if poll_age_seconds is not None and (
            type(poll_age_seconds) is not int or poll_age_seconds < 0):
        raise ValueError("invalid heartbeat age")
    if arrival_policy not in ("expected", "bounded"):
        raise ValueError("unrecognized evidence policy")
    key = forecast.get("item_key")
    if type(key) is not str or key.count(":") != 1:
        raise ValueError("invalid item key")

    purchase = forecast.get("restock_events", [])
    physical = forecast.get("true_restock_events", purchase)
    if not isinstance(purchase, list) or not isinstance(physical, list):
        raise ValueError("invalid event timeline")
    if len(physical) > MAX_EVENTS_PER_ITEM or len(purchase) > MAX_EVENTS_PER_ITEM:
        raise ValueError("unbounded event timeline")
    # Physical events are authoritative for ordinal identity. No positional
    # relabeling from a partial purchase list is permitted.
    if purchase and len(purchase) != len(physical):
        raise ValueError("purchase events lack physical ordinal alignment")

    events = []
    previous = 0
    selected = None
    for i, physical_event in enumerate(physical):
        if not isinstance(physical_event, dict):
            raise ValueError("invalid physical restock event")
        center = _epoch(physical_event.get("predicted_restock_epoch"),
                        "predicted physical restock")
        low = _epoch(physical_event.get("restock_early_epoch"), "early restock")
        high = _epoch(physical_event.get("restock_late_epoch"), "late restock")
        if not low <= center <= high or center <= previous:
            raise ValueError("unsorted physical restock timeline")
        previous = center
        buy = purchase[i] if purchase else None
        stock_end = None
        early_end = None
        if buy is not None:
            if not isinstance(buy, dict) or buy.get("predicted_restock_epoch") != center:
                raise ValueError("purchase and physical event identity mismatch")
            stock_end = _epoch(buy.get("predicted_stock_below_30_epoch"),
                               "predicted stock below 30")
            if stock_end <= center:
                raise ValueError("purchase window ends before restock")
            early_end = _safe_epoch(buy.get("early_stock_end_epoch"))
        start = high if arrival_policy == "bounded" else center
        end = early_end if arrival_policy == "bounded" else stock_end
        depart = max(now, start - flight)
        latest = end - flight - grace_seconds - 1 if end is not None else None
        reachable = (end is not None and start < end and depart <= latest and
                     start <= depart + flight and
                     depart + flight + grace_seconds < end)
        arrival = depart + flight if reachable else None
        reason = ("PURCHASE_WINDOW_NOT_ESTABLISHED" if stock_end is None else
                  "UNCERTAINTY_BOUNDS_DO_NOT_OVERLAP" if arrival_policy == "bounded"
                  and (end is None or start >= end) else
                  "ESTIMATED_STOCKED_PHASE_REACHABLE" if reachable else
                  "NOT_REACHABLE_WITH_PLAYER_FLIGHT")
        record = {
            "index": i + 1,
            "predicted_restock_epoch": center,
            "restock_early_epoch": low,
            "restock_late_epoch": high,
            "predicted_stock_below_30_epoch": stock_end,
            "early_stock_end_epoch": early_end,
            "estimated_departure_start_epoch": depart if reachable else None,
            "estimated_latest_departure_epoch": latest if reachable else None,
            "estimated_arrival_epoch": arrival,
            "estimated_arrival_plus_grace_epoch": (
                arrival + grace_seconds if arrival is not None else None),
            "flight_reachable": bool(reachable),
            "item_quantity_threshold": target_qty,
            "calibration_state": "UNCALIBRATED",
            "forecast_horizon_seconds": center - issued,
            "model_proven_success": False,
            "reason": reason,
            "predicted_true_depletion_epoch": physical_event.get(
                "predicted_true_depletion_epoch",
                buy.get("predicted_true_depletion_epoch") if buy else None),
        }
        zero = record["predicted_true_depletion_epoch"]
        if zero is not None:
            _epoch(zero, "true zero depletion")
            if stock_end is not None and zero < stock_end:
                raise ValueError("zero depletion precedes availability loss")
        events.append(record)
        if reachable and selected is None:
            selected = record

    # Current observed >=30 phase is a separate opportunity, NOT a restock.
    current = forecast.get("current_stock_window")
    current_offer = None
    # Some legacy research families can emit a partial placeholder for the
    # observed current window. It has no safe timing geometry and must never
    # become a departure recommendation. Physical future events remain intact.
    if isinstance(current, dict) and (
            current.get("predicted_restock_epoch") is None or
            current.get("predicted_stock_below_30_epoch") is None):
        current = None
    if current is not None:
        if not isinstance(current, dict):
            raise ValueError("invalid current purchase window")
        center = _epoch(current.get("predicted_restock_epoch"),
                        "current stock prediction timestamp")
        stock_end = _epoch(current.get("predicted_stock_below_30_epoch"),
                           "current stock below 30")
        if center > now or stock_end <= center:
            raise ValueError("invalid current stock window")
        early_end = _safe_epoch(current.get("early_stock_end_epoch"))
        end = early_end if arrival_policy == "bounded" else stock_end
        if end is not None and now + flight + grace_seconds < end:
            current_offer = {
                "index": 0, "predicted_restock_epoch": None,
                "estimated_departure_start_epoch": now,
                "estimated_latest_departure_epoch": end - flight - grace_seconds - 1,
                "estimated_arrival_epoch": now + flight,
                "estimated_arrival_plus_grace_epoch": now + flight + grace_seconds,
                "flight_reachable": True,
                "reason": "CURRENT_MODELED_STOCK_WINDOW_REACHABLE",
                "calibration_state": "UNCALIBRATED",
                "model_proven_success": False,
            }
    if current_offer is not None:
        selected = current_offer

    too_old = now - issued >= 300
    stale_poll = poll_age_seconds is None or poll_age_seconds > max_poll_age_seconds
    model_available = forecast.get("status") == "EVENT_TIMELINE_FORECAST_AVAILABLE"
    # Legacy forecasts omit this metadata and have always used >=30.
    # A new threshold is valid only when the forecaster used that threshold.
    if target_qty != forecast.get("arrival_stock_threshold", 30):
        status, reason = STATUS_ABSTAIN, "REQUESTED_THRESHOLD_NOT_SUPPORTED_BY_MODEL"
    elif stale_poll or too_old:
        status = STATUS_STALE
        reason = "STALE_SOURCE_POLL" if stale_poll else "STALE_MODEL_FORECAST"
    elif not model_available:
        status, reason = STATUS_ABSTAIN, str(forecast.get("status") or "MODEL_NO_FORECAST")
    elif selected is None:
        status, reason = STATUS_NO_WINDOW, "NO_REACHABLE_RESTOCK_IN_EVENT_LIST"
    elif selected["estimated_departure_start_epoch"] <= now:
        status, reason = STATUS_ACTIVE, "MODELED_STOCKED_PHASE_RECONFIRM_BEFORE_TRAVEL"
    else:
        status, reason = STATUS_WAIT, "MODEL_DEPARTURE_NOT_YET_REACHED"
    chosen = selected if status in (STATUS_ACTIVE, STATUS_WAIT) else None
    eta = chosen["estimated_departure_start_epoch"] - now if chosen else None
    return {
        "item_key": key, "asof_epoch": issued, "evaluated_at_epoch": now,
        "forecast_age_seconds": max(0, now - issued),
        "source_poll_age_seconds": poll_age_seconds,
        "player_flight_seconds": flight, "target_quantity": target_qty,
        "depletion_stock_quantity": forecast.get(
            "depletion_stock_quantity", forecast.get("physical_depletion_quantity")),
        "restock_timer_anchor": forecast.get("restock_timer_anchor"),
        "arrival_grace_seconds": grace_seconds,
        "arrival_policy": arrival_policy,
        "status": status, "reason": reason,
        "estimated_departure_epoch": (
            chosen["estimated_departure_start_epoch"] if chosen else None),
        "estimated_departure_deadline_epoch": (
            chosen["estimated_latest_departure_epoch"] if chosen else None),
        "estimated_arrival_epoch": chosen["estimated_arrival_epoch"] if chosen else None,
        "estimated_arrival_plus_grace_epoch": (
            chosen["estimated_arrival_plus_grace_epoch"] if chosen else None),
        "departure_countdown_seconds": eta,
        "selected_restock_event_index": chosen["index"] if chosen else None,
        "current_stock_candidate": current_offer,
        "forecast_events": events,
        "all_restock_events_preserved": len(events) == len(physical),
        "prediction_calibrated": False,
        "verified_arrival_stock_success_probability": None,
        "departure_recommendation_is_estimate": True,
        "reconfirm_before_departure": True,
        "valid_until_epoch": min(issued + 300, now + max(0, max_poll_age_seconds -
                                 (poll_age_seconds if poll_age_seconds is not None else max_poll_age_seconds))),
        "no_automated_gameplay": True,
    }
