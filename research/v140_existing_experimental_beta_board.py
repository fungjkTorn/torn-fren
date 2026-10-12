"""V140: PURE beta-board contract for the EXISTING /experimental page.

No new HTML page or endpoint. The deployed /experimental and
/api/experimental/v41/predictions are not represented in the research checkout,
so this adapter is deliberately NOT mounted onto the live app.

Merge *separate* V41 incumbent rows and V133 V128 research preview in one
display contract; never swap the per-item incumbent model for V128, never
promote a provisional forecast into verified GO, never manufacture missing
forecasts, and preserve direct links to the original V2 graph.
"""
from __future__ import annotations

from collections import Counter
from urllib.parse import urlencode
from research.v97_experimental_dashboard_state import classify_prediction

ROSTER_SIZE = 24
LEGACY_ROSTER_SIZE = 21
NEAR_SECONDS = 300
V128_TTL_SECONDS = 300

def _safe_epoch(x):
    return x if type(x) is int and 0 < x < 2**40 else None

def _remaining(timestamp, now):
    return max(0, timestamp - now) if timestamp is not None else None

def _legacy_record(row, *, now):
    """Preserve the deployed incumbent's label and independently validated TTL."""
    if row is None:
        return {
            "present": False, "model_family": None, "model_config": None,
            "model_status": "NO_EXISTING_EXPERIMENTAL_RECORD",
            "display_state": "NO_CURRENT_RECOMMENDATION",
            "departure_epoch": None, "arrival_epoch": None,
            "issued_epoch": None, "valid_until_epoch": None,
            "refresh_due_in_seconds": None, "display_explanation":
            "No existing experimental model row; do not substitute V128.",
            "verified_departure": False,
        }
    issued = _safe_epoch(row.get("computed_at"))
    if issued is None or issued > now:
        return {**_legacy_record(None, now=now),
                "present": True, "model_status": "INVALID_INCUMBENT_ISSUE_TIME",
                "display_state": "INVALID_INCUMBENT_DATA"}
    try:
        status = classify_prediction(row, now=now)
    except (ValueError, TypeError, KeyError):
        return {**_legacy_record(None, now=now),
                "present": True, "model_status": "INVALID_INCUMBENT_RECORD",
                "display_state": "INVALID_INCUMBENT_DATA"}
    deadline = _safe_epoch(status["snapshot_valid_until"])
    return {
        "present": True,
        "model_family": row.get("model_family"),
        "model_config": row.get("model_config"),
        "model_status": row.get("status"),
        "display_state": status["display_state"],
        "departure_epoch": status["departure_time"],
        "arrival_epoch": status["arrival_time"],
        "issued_epoch": status["snapshot_as_of"],
        "valid_until_epoch": deadline,
        "refresh_due_in_seconds": _remaining(deadline, now),
        "display_explanation": status["display_explanation"],
        "verified_departure": False,
        "prediction_accuracy_verified": row.get("prediction_accuracy_verified") is True,
        "live_country_stock_freshness_verified": False,
    }

def _v128_record(row, *, now):
    """V128 candidate always remains a separately labeled research estimate."""
    if row is None or not isinstance(row, dict):
        return {
            "present": False, "model_family": "V128",
            "display_state": "NO_COMPLETE_V128_BATCH",
            "departure_epoch": None, "arrival_epoch": None,
            "issued_epoch": None, "valid_until_epoch": None,
            "refresh_due_in_seconds": None, "display_explanation":
            "24-item V128 research batch missing or invalid.",
            "verified_departure": False,
        }
    issue = _safe_epoch(row.get("forecast_issued_epoch"))
    valid = issue + V128_TTL_SECONDS if issue is not None else None
    state = row.get("display_status") or "UNKNOWN"
    departure = _safe_epoch(row.get("proposed_departure_epoch"))
    arrival = _safe_epoch(row.get("proposed_arrival_epoch"))
    supported = state in {
        "RESEARCH_NEAR_TERM_NOT_CERTIFIED",
        "RESEARCH_FUTURE_WATCH_RECHECK_REQUIRED",
    }
    message = row.get("message")
    if issue is None or issue > now:
        state = "FUTURE_ISSUANCE_REJECTED" if issue else "INVALID_RESEARCH_ISSUE_TIME"
        message = "Research issue time is invalid; no departure guidance."
        supported = False
    elif now >= valid:
        state = "RESEARCH_SNAPSHOT_EXPIRED"
        message = "Research snapshot expired; obtain a fresh near-departure recheck."
        supported = False
    elif supported:
        if departure is None or arrival is None or arrival <= departure:
            state = "NO_QUALIFYING_RESEARCH_DEPARTURE"
            message = "Research departure/arrival timestamps are invalid."
            supported = False
        elif departure < now:
            state = "PROPOSED_DEPARTURE_ALREADY_PASSED"
            message = "Proposed departure passed; a new forecast is required."
            supported = False
        else:
            state = ("RESEARCH_NEAR_TERM_NOT_CERTIFIED" if departure - now <= NEAR_SECONDS
                     else "RESEARCH_FUTURE_WATCH_RECHECK_REQUIRED")
            message = ("Near-term research candidate; landing stock is not certified."
                       if departure - now <= NEAR_SECONDS else
                       "Future research WATCH; recheck with a fresh forecast near departure.")
    if not (supported and valid is not None and now < valid
            and departure is not None and departure >= now
            and arrival is not None and arrival > departure
            and row.get("research_only") is True):
        departure = arrival = None
    return {
        "present": True, "model_family": "V128",
        "display_state": state,
        "departure_epoch": departure, "arrival_epoch": arrival,
        "issued_epoch": issue,
        "valid_until_epoch": valid,
        "refresh_due_in_seconds": _remaining(valid, now),
        "display_explanation": message,
        "verified_departure": False,
        "estimated_stock_at_arrival": None,
        "score_is_calibrated_probability": False,
        "live_country_stock_freshness_verified": False,
        "scenario_availability_fraction_uncalibrated": (
            row.get("simulation_arrival_fraction_not_calibrated_probability")),
    }

def build_board(legacy, panel, *, now, roster_keys):
    """Render exactly 24 rows; never change the incumbent /experimental payload.

    `roster_keys` must come from pinned exact_roster(), not from untrusted
    legacy API rows. Any missing/ambiguous incumbent data is made visible.
    An incomplete V128 batch yields no V128 departures for ANY item.
    """
    if type(now) is not int or now <= 0:
        raise ValueError("invalid as-of epoch")
    keys = list(roster_keys)
    if (len(keys) != ROSTER_SIZE or len(set(keys)) != ROSTER_SIZE
        or any(not isinstance(k, str) or k.count(":") != 1
               or not all(k.split(":", 1)) for k in keys)):
        raise ValueError("roster must have 24 unique valid country:item keys")

    raw = legacy.get("latest") if isinstance(legacy, dict) else None
    raw = raw if isinstance(raw, list) else []
    incumbent = {}
    collisions = set()
    for r in raw:
        if not isinstance(r, dict):
            continue
        key = r.get("item_key")
        if key not in keys:
            continue
        if key in incumbent:
            collisions.add(key)
        incumbent[key] = r
    for key in collisions:
        incumbent.pop(key, None)

    panel_ok = (
        isinstance(panel, dict)
        and panel.get("status") == "V133_SAFE_RESEARCH_24_ITEM_DEPARTURE_PANEL_DATA"
        and panel.get("roster_size") == ROSTER_SIZE
        and isinstance(panel.get("items"), dict)
        and set(panel["items"]) == set(keys)
        and _safe_epoch(panel.get("selected_issued_epoch")) is not None
        and all(
            isinstance(v, dict)
            and v.get("item_key") == k
            and v.get("forecast_issued_epoch") == panel["selected_issued_epoch"]
            for k, v in panel["items"].items()
        )
    )
    v128_rows = panel["items"] if panel_ok else {}

    rows = []
    for key in sorted(keys):
        country, item = key.split(":", 1)
        old = _legacy_record(incumbent.get(key), now=now)
        newer = _v128_record(v128_rows.get(key), now=now)
        rows.append({
            "item_key": key,
            "country": country,
            "item_name": item,
            "graph_url": "/?" + urlencode({"country": country, "item": item}),
            "existing_experimental_model": old,
            "v128_research_challenger": newer,
            "primary_is_incumbent_not_v128": True,
            "minimum_arrival_stock_target": 30,
            "stock_at_landing_verified": False,
            "no_in_game_action_taken": True,
        })
    status_counts = dict(sorted(Counter(
        r["existing_experimental_model"]["display_state"] for r in rows
    ).items()))
    v128_counts = dict(sorted(Counter(
        r["v128_research_challenger"]["display_state"] for r in rows
    ).items()))
    return {
        "status": "V140_EXISTING_EXPERIMENTAL_24_BETA_BOARD_CONTRACT",
        "read_only": True,
        "integration_mounted": False,
        "existing_page_to_reuse": "/experimental",
        "existing_api_to_reuse": "/api/experimental/v41/predictions",
        "detailed_page_to_reuse": "/",
        "roster_count": len(rows),
        "legacy_raw_row_count": len(raw),
        "legacy_unique_usable_keys": len(incumbent),
        "legacy_duplicate_item_keys": sorted(collisions),
        "legacy_complete_24": len(incumbent) == ROSTER_SIZE,
        "v128_complete_24": panel_ok,
        "incumbent_status_counts": status_counts,
        "v128_status_counts": v128_counts,
        "accuracy_is_not_verified": True,
        "provider_country_freshness_not_verified": True,
        "original_v2_graph_unchanged": True,
        "rows": rows,
    }
