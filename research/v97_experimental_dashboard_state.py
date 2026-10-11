"""V97 read-only dashboard state contract: split near-term, watch and validity.

The old experimental page can label a 6h forecast 'Ready' simply because
its latest private snapshot is fresh for five minutes. That is misleading:
snapshot TTL is NOT how long the flight will be suitable for. Never display
out-of-scope future options as present-tense ready to leave.

Pure transformation. Not mounted in web, no DB/API/flight actions.
"""
from __future__ import annotations

STATUS_READY_SOON="DEPART_SOON_PROVISIONAL"
STATUS_READY_NOW="DEPART_NOW_PROVISIONAL"
STATUS_WATCH="FUTURE_FORECAST_WATCH"
STATUS_PASSED="DEPARTURE_PASSED"
STATUS_EXPIRED="EXPIRED_SNAPSHOT"
STATUS_UNAVAILABLE="NO_CURRENT_RECOMMENDATION"
STATUS_PREVIEW="UNVALIDATED_RESEARCH_PREVIEW"
STATUS_FRESHNESS_UNKNOWN="UNVERIFIED_SOURCE_FRESHNESS"
MAX_STOCK_AGE_SECONDS=180
DEFAULT_SOON_SECONDS=300
READY_NOW_SECONDS=30


def classify_prediction(row, *, now, soon_seconds=DEFAULT_SOON_SECONDS):
    if not isinstance(row,dict) or type(now) is not int or type(soon_seconds) is not int or not 0<=soon_seconds<=3600:
        raise ValueError("invalid prediction contract or clock")
    key=row.get("item_key")
    if not isinstance(key,str) or ":" not in key:
        raise ValueError("missing item key")
    state=str(row.get("status") or "UNKNOWN")
    preview=state.startswith("RESEARCH_PREVIEW_")
    issued=row.get("computed_at")
    valid=row.get("valid_until")
    source=row.get("stock_as_of")
    departure=row.get("departure")
    arrival=row.get("arrival")
    base={"item_key":key,"model_status":state,
          "original_actionable":row.get("actionable") is True,
          "unvalidated":row.get("prediction_accuracy_verified") is not True,
          "arrival_time":None,"departure_time":None,
          "leave_in_seconds":None,
          "snapshot_valid_until":valid if type(valid) is int else None,
          "snapshot_as_of":issued if type(issued) is int else None,
          "next_update_expected":True,
          "can_be_presented_as_verified_advice":False}
    def pack(status,why):
        return {**base,"display_state":status,"display_explanation":why}
    if preview:
        # A researcher may view the forecast window, but cannot treat the
        # unvalidated V82/V85 private forward pilot as verified game advice.
        return pack(STATUS_PREVIEW,"Forward-study preview only; no certified accuracy or gameplay departure guidance.")
    if state in {"DEPARTURE_PASSED","RESEARCH_PREVIEW_DEPARTURE_PASSED"}:
        return pack(STATUS_PASSED,"Previously recommended departure is already in the past.")
    if type(valid) is not int or valid<=now:
        return pack(STATUS_EXPIRED,"Model snapshot needs refresh; do not reuse the old departure.")
    if (type(source) is not int or source>now or now-source>MAX_STOCK_AGE_SECONDS):
        return pack(STATUS_FRESHNESS_UNKNOWN,"Collector/source timestamp is missing or stale.")
    if (not row.get("actionable") is True or type(departure) is not int
        or type(arrival) is not int):
        return pack(STATUS_UNAVAILABLE,"No currently qualifying provisional departure.")
    if departure<now:
        return pack(STATUS_PASSED,"The candidate departure time has already passed.")
    if arrival<=departure:
        return pack(STATUS_UNAVAILABLE,"Inconsistent predicted arrival timestamp.")
    base.update(departure_time=departure,arrival_time=arrival,
                leave_in_seconds=departure-now)
    if departure-now<=READY_NOW_SECONDS:
        return pack(STATUS_READY_NOW,
                    "Earliest provisional departure is imminent; stock on landing is not guaranteed.")
    if departure-now<=soon_seconds:
        return pack(STATUS_READY_SOON,
                    "Provisional departure within your quick-departure window.")
    return pack(STATUS_WATCH,
                "Farther-out provisional forecast; source snapshot expires and the model will replan before this departure.")
