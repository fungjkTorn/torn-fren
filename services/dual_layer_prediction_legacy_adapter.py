"""Offline migration adapter: existing V2 stock forecasts to dual-layer contract.

No live routing change. Deliberately does NOT claim the old "leave by" time
is an optimal departure, or that historical accuracy is a calibrated trip odds.
"""
from __future__ import annotations

from services.dual_layer_prediction_contract import build_dual_layer_prediction, TIMING_LABELS


def from_legacy_v2(
    *,
    country,
    item_name,
    as_of_timestamp,
    last_observed_timestamp,
    prediction_v2,
    requested_quantity=30,
):
    v2 = prediction_v2 or {}
    chain = v2.get("predictions") or []
    display = v2.get("display_prediction") or v2.get("prediction_1") or {}
    if not chain and display:
        chain = [display]

    events = []
    for p in chain[:8]:
        events.append({
            "estimated_restock_timestamp": p.get("estimate_timestamp"),
            "restock_window_start_timestamp": p.get("window_start_timestamp"),
            "restock_window_end_timestamp": p.get("window_end_timestamp"),
            "estimated_depletion_timestamp": p.get("target_depletion_timestamp"),
            "projected": bool(p.get("projected", False)),
        })

    reliability = (
        display.get("travel_reliability")
        or v2.get("travel_reliability")
        or "insufficient"
    )
    if reliability not in TIMING_LABELS:
        reliability = "insufficient"

    forecast = {
        "model_name": display.get("model_name") or v2.get("model_name"),
        "confidence_label": reliability,
        "window_coverage_probability": None,
        "window_coverage_calibrated": False,
        "events": events,
    }
    travel = {
        "model_name": "legacy_v2_arrival_offset",
        "travel_seconds": display.get("travel_seconds", v2.get("travel_seconds")),
        "leave_by_timestamp": display.get("recommended_leave_by_timestamp"),
        # An old latest leave-by estimate is NOT a distinct optimized leave time.
        "recommended_leave_timestamp": None,
        "recommended_arrival_timestamp": display.get("recommended_arrival_timestamp"),
        "probabilities_calibrated": False,
        "historical_arrival_success_rate": v2.get("arrival_success_rate"),
    }
    caution = v2.get("caution_only")
    warnings = []
    if caution:
        warnings.append("legacy forecast marked caution-only")
    status = v2.get("status")
    if status in {"waiting_for_clean_anchor", "waiting_for_depletion_anchor"}:
        warnings.append("current forecast anchor is not trustworthy")

    return build_dual_layer_prediction(
        country=country,
        item_name=item_name,
        as_of_timestamp=as_of_timestamp,
        observed_quantity=v2.get("current_stock"),
        last_observed_timestamp=last_observed_timestamp,
        requested_quantity=requested_quantity,
        forecast=forecast,
        travel=travel,
        data_quality={
            "legacy_status": status,
            "legacy_note": v2.get("note"),
            "warnings": warnings,
        },
    )
