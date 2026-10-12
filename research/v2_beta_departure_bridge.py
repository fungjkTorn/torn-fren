"""Pure shared arrival/departure view contract for EXISTING V2 and beta board.

This is NOT a model, web route, background job, or source of verified Torn
availability. Convert V2's as-issued multi-cycle restock/depletion *windows*
into earliest reachable provisional departures, while keeping an incumbent
specialist's independently recorded >=30 arrival estimate separate.

Important: V2 forecasts a general stocked lifetime, not an actual >=30
quantity-at-landing guarantee. Do not fabricate that field or transplant a
V128 simulation score into a restock timestamp. Snapshot freshness is gated
by the model issue, not just the time a cached HTTP response was returned.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from urllib.parse import urlencode

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v141_v2_feasible_departure_window import assess as assess_v2_window
from research.v97_experimental_dashboard_state import classify_prediction

REPLAN_SECONDS = 300
SOURCE_MAX_AGE_SECONDS = 180
MAX_WAIT_SECONDS = 8 * 3600
MIN_STOCK = 30


def _epoch(value):
    return value if type(value) is int and 0 < value < 2**40 else None


def _identity(item_key):
    if not isinstance(item_key, str) or item_key.count(":") != 1:
        raise ValueError("invalid item key")
    country, item = item_key.split(":", 1)
    if country not in TRAVEL_SECONDS or not item or item != item.strip():
        raise ValueError("unrecognized destination or item")
    return country, item, TRAVEL_SECONDS[country]


def _status_for(wait):
    if wait == 0:
        return "PROVISIONAL_LEAVE_NOW"
    if wait <= 300:
        return "PROVISIONAL_DEPART_SOON"
    return "FUTURE_WATCH_RECONFIRM_REQUIRED"


def _baseline(*, item_key, country, item, now, issued, stock_as_of):
    return {
        "item_key": item_key,
        "item_name": item,
        "country": country,
        "v2_graph_url": "/?" + urlencode({"country": country, "item": item}),
        "now_epoch": now,
        "forecast_issued_epoch": issued,
        "source_as_of_epoch": stock_as_of,
        "valid_until_epoch": None,
        "refresh_in_seconds": None,
        "status": "NO_FRESH_V2_FORECAST",
        "first_reachable": None,
        "cycle_candidates": [],
        "next_predicted_restock": None,
        "skipped_by_reason": {},
        "source_country_freshness_verified": False,
        "stock_at_arrival_at_least_30_verified": False,
        "minimum_desired_stock": MIN_STOCK,
        "departure_advice_is_provisional": True,
        "incumbent_specialist": None,
        "specialist_does_not_replace_v2_restock": True,
    }


def _specialist_view(row, *, item_key, now, flight):
    """Only translate an ACTUAL as-issued existing /experimental row.

    This forecasts arrival availability rather than V2's next restock
    boundary. It must never be used to invent a V2 next-restock timestamp.
    """
    if row is None:
        return None
    if not isinstance(row, dict):
        return {
            "status": "INVALID_INCUMBENT_ROW", "model_family": None,
            "departure_epoch": None, "arrival_epoch": None,
            "verified_stock_at_arrival": False,
        }
    if row.get("item_key") != item_key:
        return {
            "status": "SPECIALIST_ITEM_IDENTITY_MISMATCH",
            "model_family": row.get("model_family"),
            "departure_epoch": None, "arrival_epoch": None,
            "verified_stock_at_arrival": False,
        }
    try:
        state = classify_prediction(row, now=now)
    except (ValueError, TypeError, KeyError):
        return {
            "status": "INVALID_INCUMBENT_ROW",
            "model_family": row.get("model_family"),
            "departure_epoch": None, "arrival_epoch": None,
            "verified_stock_at_arrival": False,
        }
    dep = state.get("departure_time")
    arr = state.get("arrival_time")
    if dep is not None and (
        type(dep) is not int or type(arr) is not int
        or arr - dep != flight or dep < now
        or dep > now + MAX_WAIT_SECONDS
    ):
        dep = arr = None
        view_status = "SPECIALIST_FLIGHT_OR_HORIZON_INVALID"
    else:
        view_status = state["display_state"]
    return {
        "status": view_status,
        "model_family": row.get("model_family"),
        "model_config": row.get("model_config"),
        "issued_epoch": state.get("snapshot_as_of"),
        "valid_until_epoch": state.get("snapshot_valid_until"),
        "departure_epoch": dep, "arrival_epoch": arr,
        "leave_in_seconds": dep - now if dep is not None else None,
        "evidence_kind": "EXISTING_SPECIALIST_ARRIVAL_CANDIDATE",
        "verified_stock_at_arrival": False,
        "recheck_required": True,
        "probability_calibrated": False,
    }


def build_item_timeline(item_key, v2, *, now, issued_at, stock_as_of,
                        incumbent=None, valid_until=None,
                        forecast_stale=False):
    """Read-only first reachable V2 cycle and optional specialist comparison.

    True model issuance must be supplied explicitly. It must NOT be minted
    from a warm /api/history response's prediction_v2_checked_at. The
    external source_as_of is the latest collector evidence, not a verified
    country-provider update timestamp. Departure proposals are never GO.
    """
    country, item, flight = _identity(item_key)
    if type(now) is not int or now <= 0:
        raise ValueError("invalid evaluation time")
    issued = _epoch(issued_at)
    source = _epoch(stock_as_of)
    out = _baseline(item_key=item_key, country=country, item=item,
                    now=now, issued=issued, stock_as_of=source)
    out["incumbent_specialist"] = _specialist_view(
        incumbent, item_key=item_key, now=now, flight=flight)
    if not isinstance(v2, dict) or forecast_stale:
        out["status"] = "V2_WARMING_OR_STALE"
        return out
    if issued is None or source is None or source > issued or issued > now:
        out["status"] = "ISSUANCE_OR_SOURCE_UNKNOWN"
        return out
    if valid_until is not None and _epoch(valid_until) is None:
        out["status"] = "INVALID_MODEL_VALIDITY"
        return out
    expires = min(issued + REPLAN_SECONDS, valid_until or issued + REPLAN_SECONDS)
    out["valid_until_epoch"] = expires
    out["refresh_in_seconds"] = max(0, expires - now)
    if now >= expires:
        out["status"] = "MODEL_ISSUE_EXPIRED"
        return out
    if now - source > SOURCE_MAX_AGE_SECONDS:
        out["status"] = "COLLECTOR_EVIDENCE_STALE"
        return out
    chain = v2.get("predictions")
    if not isinstance(chain, list) or len(chain) > 8:
        out["status"] = "MISSING_OR_UNBOUNDED_V2_CYCLES"
        return out
    if not chain:
        out["status"] = "NO_V2_CYCLES"
        return out

    # Fail the entire cohort if the source payload contains duplicate,
    # nonchronological, or malformed cycle identities.
    numbers = [p.get("prediction_number") if isinstance(p, dict) else None
               for p in chain]
    if any(type(n) is not int or n <= 0 for n in numbers):
        out["status"] = "INVALID_V2_CYCLE_IDENTITIES"
        return out
    if numbers != sorted(set(numbers)):
        out["status"] = "INVALID_V2_CYCLE_IDENTITIES"
        return out
    if any(p.get("travel_seconds") not in (None, flight) for p in chain):
        out["status"] = "TRAVEL_TIME_MISMATCH"
        return out
    restocks = [_epoch(p.get("estimate_timestamp")) for p in chain]
    if (any(t is None for t in restocks)
        or any(a >= b for a, b in zip(restocks, restocks[1:]))):
        out["status"] = "INVALID_OR_UNSORTED_RESTOCK_CHAIN"
        return out

    skipped = Counter()
    candidates = []
    first_restock = chain[0]
    restock = _epoch(first_restock.get("estimate_timestamp"))
    if restock is not None:
        out["next_predicted_restock"] = {
            "cycle": numbers[0],
            "estimate_epoch": restock,
            "window_start_epoch": _epoch(
                first_restock.get("window_start_timestamp")),
            "window_end_epoch": _epoch(
                first_restock.get("window_end_timestamp")),
            "is_stock_30_at_landing_forecast": False,
        }
    for p in chain:
        enriched = {**p, "travel_seconds": flight}
        evaluated = assess_v2_window(enriched, now=now)
        stage = evaluated["window_class"]
        if stage not in ("TOO_EARLY", "PROVISIONAL_DEPARTURE_WINDOW"):
            skipped[stage] += 1
            continue
        earlier = evaluated["earliest_departure_epoch"]
        latest = evaluated["latest_departure_epoch"]
        if earlier is None or latest is None:
            skipped["NO_FEASIBLE_STOCKED_INTERVAL"] += 1
            continue
        actual_departure = max(now, earlier)
        if actual_departure > latest:
            skipped["DEPARTURE_WINDOW_EXPIRED"] += 1
            continue
        if actual_departure > issued + MAX_WAIT_SECONDS:
            skipped["BEYOND_EIGHT_HOUR_ISSUE_HORIZON"] += 1
            continue
        # This is an estimated *nonzero stocked* window. A model must
        # independently establish >=30 at landing before that can be claimed.
        candidate = {
            "prediction_number": p["prediction_number"],
            "v2_model": p.get("model_name"),
            "forecast_restock_epoch": _epoch(p.get("estimate_timestamp")),
            "forecast_restock_late_epoch": _epoch(
                p.get("window_end_timestamp")),
            "earliest_departure_epoch": actual_departure,
            "latest_departure_epoch": latest,
            "arrival_epoch": actual_departure + flight,
            "earliest_arrival_epoch": evaluated["earliest_arrival_epoch"],
            "latest_arrival_epoch": evaluated["latest_arrival_epoch"],
            "leave_in_seconds": actual_departure - now,
            "status": _status_for(actual_departure - now),
            "requires_reconfirmation": True,
            "estimated_stock_at_arrival_30_or_more": None,
            "forecast_type": "V2_RESTOCK_AND_STOCK_LIFETIME",
            "reliability_label": p.get("travel_reliability"),
        }
        candidates.append(candidate)
    out["skipped_by_reason"] = dict(sorted(skipped.items()))
    # Earliest departure is the product requirement, even if later cycles
    # have a better-looking model confidence label.
    candidates.sort(key=lambda x:(
        x["earliest_departure_epoch"], x["prediction_number"]))
    out["cycle_candidates"] = candidates
    out["first_reachable"] = candidates[0] if candidates else None
    out["status"] = (
        "V2_FIRST_REACHABLE_PROVISIONAL" if candidates
        else "NO_REACHABLE_V2_WINDOW")
    return out
