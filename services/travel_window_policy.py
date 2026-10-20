"""Shared cheap flight-window policy; no model fitting, simulation or I/O.

Policy variants adjust a real landing target, never the flight duration.
Ten-second grace is a post-landing stock-survival requirement, not a way
to arrive before a physical restock. This is an uncalibrated research adapter.
"""
from services.travel_decision_contract_v166 import build_item_travel_decision

POLICIES = frozenset(("median", "quarter", "midpoint", "late", "current_quarter"))
MAX_WAIT_SECONDS = 28800


def project_policy(forecast, *, now, poll_age_seconds, kind="median",
                   player_flight_seconds=None, target_qty=30):
    if kind not in POLICIES:
        raise ValueError("unknown departure policy")
    decision = build_item_travel_decision(
        forecast, now=now, poll_age_seconds=poll_age_seconds,
        player_flight_seconds=player_flight_seconds, target_qty=target_qty)
    decision["departure_policy"] = kind
    if decision["status"] not in (
            "ESTIMATED_DEPARTURE_WINDOW_OPEN", "WAIT_FOR_ESTIMATED_DEPARTURE"):
        return decision
    if kind == "median":
        return decision

    flight = decision["player_flight_seconds"]
    grace = decision["arrival_grace_seconds"]
    # Existing >=30 stock is a separate opportunity, and always beats a
    # forecasted future cycle when it remains viable at real landing+grace.
    if decision["current_stock_candidate"] is not None:
        if kind == "current_quarter":
            decision["status"] = "MODELED_CURRENT_STOCK_REACHABLE"
            decision["reason"] = "OBSERVED_CURRENT_STOCK_WITH_MODELED_SURVIVAL_RECHECK"
        return decision

    if kind == "current_quarter":
        kind = "quarter"
    for event in decision["forecast_events"]:
        center = event["predicted_restock_epoch"]
        stock_end = event["predicted_stock_below_30_epoch"]
        if stock_end is None:
            continue  # Keep physical event, but abstain on quantity survival.
        if kind == "late":
            start = event["restock_late_epoch"]
            end = event["early_stock_end_epoch"]
            target = start
        else:
            start = center
            end = stock_end
            fraction = 0.5 if kind == "midpoint" else 0.25
            target = start + int((end - start) * fraction)
        if end is None or start >= end:
            continue
        depart = max(now, target - flight)
        latest = end - flight - grace - 1
        landing = depart + flight
        if (depart > now + MAX_WAIT_SECONDS or depart > latest or
                not start <= landing or landing + grace >= end):
            continue
        return dict(
            decision, estimated_departure_epoch=depart,
            estimated_departure_deadline_epoch=latest,
            estimated_arrival_epoch=landing,
            estimated_arrival_plus_grace_epoch=landing + grace,
            departure_countdown_seconds=depart - now,
            selected_restock_event_index=event["index"],
            status="ESTIMATED_DEPARTURE_WINDOW_OPEN" if depart == now
                   else "WAIT_FOR_ESTIMATED_DEPARTURE",
            reason="BUFFERED_STOCK_WINDOW_ESTIMATE_RECONFIRM")

    return dict(
        decision, estimated_departure_epoch=None, estimated_arrival_epoch=None,
        estimated_arrival_plus_grace_epoch=None,
        estimated_departure_deadline_epoch=None, departure_countdown_seconds=None,
        selected_restock_event_index=None, status="NO_REACHABLE_BUFFERED_WINDOW",
        reason="NO_PHYSICAL_EVENT_WITH_BUFFERED_PURCHASE_WINDOW")
