"""V141: fail-closed Prediction V2 window feasibility for future UI integration.

Original browser/server implementations silently collapse a negative arrival
window to a point, potentially labeling it GOOD TO LEAVE. Return NO_WINDOW
instead. This is NOT a new prediction model and it is NOT mounted on web.
Current-stock predictions are not automatically safe merely because the
observed quantity is nonzero; threshold>=30 at ETA requires independent
evidence, which Prediction V2 currently does not persist.
"""
from __future__ import annotations

from math import isfinite

MIN_STOCK = 30

def _number(v):
    if type(v) not in (int, float) or not isfinite(v) or v <= 0:
        return None
    return float(v)

def assess(prediction, *, now):
    if not isinstance(prediction, dict) or type(now) not in (int,float):
        raise ValueError("invalid prediction or current clock")
    flight = _number(prediction.get("travel_seconds"))
    estimate = _number(prediction.get("estimate_timestamp"))
    late_restock = _number(prediction.get("window_end_timestamp"))
    recommended = _number(prediction.get("recommended_arrival_timestamp"))
    depletion = _number(prediction.get("target_depletion_timestamp"))
    lifetime = _number(prediction.get("expected_stock_lifetime_seconds"))

    base = {
        "window_class": "UNKNOWN",
        "earliest_departure_epoch": None,
        "latest_departure_epoch": None,
        "earliest_arrival_epoch": None,
        "latest_arrival_epoch": None,
        "depart_in_seconds": None,
        "flight_seconds": int(flight) if flight is not None else None,
        "target_minimum_stock": MIN_STOCK,
        "arrival_stock_at_least_30_verified": False,
        "supports_certified_go": False,
        "next_restock_not_conflated_with_current_stock": True,
    }
    if flight is None or not (estimate or recommended or late_restock):
        return {**base,"window_class":"INSUFFICIENT_V2_FORECAST"}
    earliest = max(recommended or estimate or 0,
                   late_restock or estimate or 0)
    if not earliest:
        return {**base,"window_class":"INSUFFICIENT_V2_FORECAST"}

    # Without an actual modeled end of the stocked interval, do not invent a
    # latest safe arrival from the end of the *restock prediction interval*.
    if depletion is None:
        return {**base,"window_class":"NO_STOCK_LIFETIME_BOUND"}
    buffer = max(60, min(300, round(lifetime * .10))) if lifetime else 60
    latest = depletion - buffer
    if latest <= earliest:
        return {**base,"window_class":"NO_FEASIBLE_STOCKED_INTERVAL",
                "reason":"Predicted depletion buffer ends before safe arrival begins."}
    earliest_leave = earliest - flight
    latest_leave = latest - flight
    if now > latest_leave:
        return {**base,"window_class":"DEPARTURE_WINDOW_EXPIRED"}
    stage = "TOO_EARLY" if now < earliest_leave else "PROVISIONAL_DEPARTURE_WINDOW"
    return {
        **base, "window_class":stage,
        "earliest_departure_epoch":round(earliest_leave),
        "latest_departure_epoch":round(latest_leave),
        "earliest_arrival_epoch":round(earliest),
        "latest_arrival_epoch":round(latest),
        "depart_in_seconds":max(0,round(earliest_leave-now)),
        "reason":"V2 forecast window only; arrival stock >=30 is not verified.",
    }

def current_stock_threshold_note(*, observed_quantity, arrival_stock_lower_bound=None):
    """Never turn a nonzero current observation into >=30 at arrival."""
    if type(observed_quantity) is not int or observed_quantity < 0:
        return "UNKNOWN_CURRENT_STOCK"
    if observed_quantity < MIN_STOCK:
        return "BELOW_30_NOW"
    if type(arrival_stock_lower_bound) is not int:
        return "ABOVE_30_NOW_BUT_LANDING_UNVERIFIED"
    if arrival_stock_lower_bound < MIN_STOCK:
        return "PREDICTED_BELOW_30_AT_ARRIVAL"
    return "LOWER_BOUND_AT_ARRIVAL_30_OR_MORE_RESEARCH_ONLY"
