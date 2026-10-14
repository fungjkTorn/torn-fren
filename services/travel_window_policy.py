"""Shared cheap flight-window policy; no model fitting, simulation or I/O."""
from services.travel_decision_contract_v166 import build_item_travel_decision

POLICIES=frozenset(("median","quarter","midpoint","late","current_quarter"))


def project_policy(forecast,*,now,poll_age_seconds,kind="median",player_flight_seconds=None,target_qty=30):
    if kind not in POLICIES:
        raise ValueError("unknown departure policy")
    decision=build_item_travel_decision(forecast,now=now,
        poll_age_seconds=poll_age_seconds,player_flight_seconds=player_flight_seconds,target_qty=target_qty)
    decision["departure_policy"]=kind
    flight=decision["player_flight_seconds"]
    grace=decision["arrival_grace_seconds"]
    healthy=(decision["status"]!="STALE_DATA" and target_qty==30
             and forecast["status"]=="EVENT_TIMELINE_FORECAST_AVAILABLE")
    if not healthy:
        return decision
    if kind=="current_quarter":
        current=forecast.get("current_stock_window")
        if current and now+flight+grace<current["predicted_stock_below_30_epoch"]:
            return dict(decision,estimated_departure_epoch=now,
                        estimated_departure_deadline_epoch=current["predicted_stock_below_30_epoch"]-flight-grace-1,
                        estimated_arrival_epoch=now+flight+grace,
                        departure_countdown_seconds=0,
                        selected_restock_event_index=0,
                        status="MODELED_CURRENT_STOCK_REACHABLE",
                        reason="OBSERVED_CURRENT_STOCK_WITH_MODELED_SURVIVAL_RECHECK")
        kind="quarter"
    if decision["estimated_departure_epoch"] is None or kind=="median":
        return decision
    for event in decision["forecast_events"]:
        start=event["predicted_restock_epoch"]
        end=event["predicted_stock_below_30_epoch"]
        target=(start+(end-start)//2 if kind=="midpoint" else
                start+(end-start)//4 if kind=="quarter" else event["restock_late_epoch"])
        depart=max(now,target-flight-grace)
        if start<=depart+flight+grace<end:
            return dict(decision,estimated_departure_epoch=depart,
                        estimated_departure_deadline_epoch=end-flight-grace-1,
                        estimated_arrival_epoch=depart+flight+grace,
                        departure_countdown_seconds=depart-now,
                        selected_restock_event_index=event["index"],
                        status="ESTIMATED_DEPARTURE_WINDOW_OPEN" if depart==now else "WAIT_FOR_ESTIMATED_DEPARTURE",
                        reason="BUFFERED_STOCK_WINDOW_ESTIMATE_RECONFIRM")
    return dict(decision,estimated_departure_epoch=None,estimated_arrival_epoch=None,
                estimated_departure_deadline_epoch=None,departure_countdown_seconds=None,
                selected_restock_event_index=None,status="NO_REACHABLE_BUFFERED_WINDOW")
