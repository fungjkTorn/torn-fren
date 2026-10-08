"""Offline-only shared contract for restock forecasting and travel optimization.

No website/Discord/production routing is changed by importing this module.
Probabilities cannot be surfaced unless explicitly marked calibrated.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

SCHEMA = "torn-fren-dual-layer-v1"
TIMING_LABELS = {"insufficient", "unreliable", "marginal", "good", "excellent"}


def _number(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric or null")
    return int(round(value))


def _probability(value, name, calibrated):
    if value is None:
        return None
    if not calibrated:
        raise ValueError(f"{name}: uncalibrated probabilities cannot be published")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be between zero and one")
    return float(value)


def _window(point, start, end, name):
    p = _number(point, name + ".point")
    lo = _number(start, name + ".start")
    hi = _number(end, name + ".end")
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(f"{name}: start > end")
    if p is not None and lo is not None and p < lo:
        raise ValueError(f"{name}: point precedes window")
    if p is not None and hi is not None and p > hi:
        raise ValueError(f"{name}: point exceeds window")
    return {"estimate_timestamp": p, "start_timestamp": lo, "end_timestamp": hi}


def build_dual_layer_prediction(
    *,
    country: str,
    item_name: str,
    as_of_timestamp: int,
    observed_quantity: int | None,
    last_observed_timestamp: int | None,
    requested_quantity: int = 30,
    forecast: dict[str, Any] | None = None,
    travel: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
):
    """Normalize independent model outputs for the future shared frontend API.

    Layer 1 forecasts restocks and sellouts. Layer 2 optimizes departures.
    One layer can be present without the other. No fabricated timestamps or odds.
    """
    if not country or not item_name:
        raise ValueError("country and item name required")
    if isinstance(requested_quantity, bool) or not isinstance(requested_quantity, int) or requested_quantity < 1:
        raise ValueError("requested_quantity must be a positive integer")

    now = _number(as_of_timestamp, "as_of")
    qty = _number(observed_quantity, "observed_quantity")
    seen = _number(last_observed_timestamp, "last_observed")
    if qty is not None and qty < 0:
        raise ValueError("observed_quantity cannot be negative")
    if seen is not None and now is not None and seen > now:
        raise ValueError("last observation cannot be in the future")
    state = ("unknown" if qty is None else "sold_out" if qty == 0\n             else "active" if qty >= requested_quantity else "below_requested_quantity")

    quality = deepcopy(data_quality or {})
    warnings = list(quality.get("warnings") or [])
    if seen is None or now is None or now - seen > 600:
        warnings.append("stock observation is stale or unavailable")

    fc = forecast or {}
    label = fc.get("confidence_label", "insufficient")
    if label not in TIMING_LABELS:
        raise ValueError("unknown forecast confidence label")
    events = []
    for i, raw in enumerate((fc.get("events") or [])[:8], start=1):
        events.append({
            "event_index": i,
            "restock": _window(
                raw.get("estimated_restock_timestamp"),
                raw.get("restock_window_start_timestamp"),
                raw.get("restock_window_end_timestamp"), f"event[{i}].restock",
            ),
            "depletion": _window(
                raw.get("estimated_depletion_timestamp"),
                raw.get("depletion_window_start_timestamp"),
                raw.get("depletion_window_end_timestamp"), f"event[{i}].depletion",
            ),
            "projected": bool(raw.get("projected", False)),
        })

    historical_max = quality.get("historical_max_quantity")\n    if historical_max is not None and historical_max < requested_quantity:\n        warnings.append("requested quantity exceeds historically observed maximum")\n\n    tr = travel or {}
    seconds = _number(tr.get("travel_seconds"), "travel_seconds")
    if seconds is not None and seconds < 0:\n        raise ValueError("travel_seconds cannot be negative")\n    leave = _number(tr.get("recommended_leave_timestamp"), "leave")
    arrival = _number(tr.get("recommended_arrival_timestamp"), "arrival")
    leave_window = _window(
        leave, tr.get("leave_window_start_timestamp"),
        tr.get("leave_window_end_timestamp"), "leave_window",
    )
    if leave is not None and seconds is not None:
        implied = leave + seconds
        if arrival is not None and abs(arrival - implied) > 1:
            raise ValueError("arrival is not departure + flight")
        if arrival is None:
            arrival = implied

    wait = None if now is None or leave is None else max(0, leave - now)
    cap = _number(tr.get("max_wait_seconds"), "max_wait")
    if cap is not None and wait is not None and wait > cap:
        warnings.append("recommended departure exceeds user wait budget")
    if tr.get("session_cap"):
        warnings.append("forced departure at wait cap; not optimal timing")

    calibrated = bool(tr.get("probabilities_calibrated", False))
    prob_keys = ("p_arrival", "p_plus_10s", "p_plus_1m", "p_plus_3m")
    probs = {
        k: _probability(tr.get(k), k, calibrated) for k in prob_keys
    }
    last_prob = None
    for key in prob_keys:
        p = probs[key]
        if p is not None:
            if last_prob is not None and p < last_prob:
                raise ValueError("grace-window success probabilities cannot decrease")
            last_prob = p

    quality["warnings"] = list(dict.fromkeys(warnings))
    return {
        "schema": SCHEMA,
        "country": country.strip().lower(),
        "item_name": item_name.strip(),
        "as_of_timestamp": now,
        "current": {
            "quantity": qty,
            "last_observed_timestamp": seen,
            "requested_quantity": requested_quantity,
            "state": state,
        },
        "forecast": {
            "model_name": fc.get("model_name"),
            "confidence_label": label,
            "window_coverage_probability": _probability(
                fc.get("window_coverage_probability"),
                "window_coverage_probability",
                bool(fc.get("window_coverage_calibrated", False)),
            ),
            "events": events,
        },
        "travel": {
            "model_name": tr.get("model_name"),
            "travel_seconds": seconds,
            "recommended_leave_timestamp": leave,
            "recommended_arrival_timestamp": arrival,
            "leave_window": leave_window,
            "wait_seconds": wait,
            "max_wait_seconds": cap,
            "target_event_index": tr.get("target_event_index"),
            "probabilities_calibrated": calibrated,
            "probabilities": probs,
            "historical_arrival_success_rate": tr.get("historical_arrival_success_rate"),
            "historical_evaluation_n": tr.get("historical_evaluation_n"),
        },
        "data_quality": quality,
    }
