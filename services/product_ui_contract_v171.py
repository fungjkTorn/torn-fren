"""Unified production-facing UI contract for TORN-FREN.

Pure transformation only. It standardizes terminology across:
- multi-item overview
- detailed V2 item graph
- Travel Decisions

It does not run models, read the collector, schedule travel, or promote research
results. Existing API fields remain valid; callers may add this contract
additively as ``ui``.
"""
from __future__ import annotations

SCHEMA_VERSION=1
FRESH_SECONDS=180
SOON_SECONDS=15*60
IMMINENT_SECONDS=60


def _int(value):
    return value if type(value) is int else None


def _safe_bool(value):
    return True if value is True else False


def _status(*,now,source_age,departure,deadline,valid_until):
    if source_age is None or source_age>FRESH_SECONDS:
        return "STALE"
    if valid_until is not None and now>valid_until:
        return "STALE"
    if departure is None:
        return "NO_SUPPORTED_TRIP"
    if deadline is not None and now>deadline:
        return "WINDOW_PASSED"
    if departure<=now:
        return "LEAVE_NOW"
    wait=departure-now
    if wait<=IMMINENT_SECONDS:
        return "LEAVE_IMMINENT"
    if wait<=SOON_SECONDS:
        return "LEAVE_SOON"
    return "WATCH"


LABELS={
    "STALE":"Data needs refresh",
    "NO_SUPPORTED_TRIP":"No supported trip",
    "WINDOW_PASSED":"Window passed",
    "LEAVE_NOW":"Leave now",
    "LEAVE_IMMINENT":"Leave imminently",
    "LEAVE_SOON":"Leave soon",
    "WATCH":"Watch",
}


def build_item_ui(row,*,now,source_poll_age_seconds=None):
    """Build one stable frontend-facing item contract from a board row."""
    if not isinstance(row,dict):
        raise ValueError("row must be a mapping")
    key=row.get("item_key")
    if not isinstance(key,str) or ":" not in key:
        raise ValueError("missing item_key")
    decision=row.get("decision") or {}
    dep=_int(row.get("departure_epoch"))
    arr=_int(row.get("arrival_epoch"))
    deadline=_int(row.get("departure_deadline_epoch"))
    valid=_int(decision.get("valid_until_epoch"))
    flight=_int(decision.get("player_flight_seconds"))
    status=_status(now=now,source_age=source_poll_age_seconds,departure=dep,
                   deadline=deadline,valid_until=valid)

    evidence=row.get("evidence")
    hist=None
    if isinstance(evidence,dict):
        n=evidence.get("resolved_arrivals"); hits=evidence.get("successes")
        frac=evidence.get("historical_fraction")
        if (type(n) is int and n>0 and type(hits) is int and 0<=hits<=n
                and isinstance(frac,(int,float)) and 0<=frac<=1):
            hist={
                "label":evidence.get("label") or "Historical evidence",
                "successes":hits,"resolved_arrivals":n,
                "success_fraction":float(frac),
                "applies_to_selected_trip":_safe_bool(
                    evidence.get("applies_to_selected_trip")),
                "calibrated_probability":False,
            }

    timeline=[]
    for e in (row.get("event_timeline") or decision.get("forecast_events") or []):
        if not isinstance(e,dict):
            continue
        idx=e.get("index",e.get("event_index"))
        timeline.append({
            "index":idx,
            "restock_epoch":_int(e.get("predicted_restock_epoch")),
            "restock_early_epoch":_int(e.get("restock_early_epoch")),
            "restock_late_epoch":_int(e.get("restock_late_epoch")),
            "stock_below_30_epoch":_int(e.get("predicted_stock_below_30_epoch")),
            "flight_reachable":_safe_bool(
                e.get("flight_reachable",e.get("reachable"))),
            "selected":idx==decision.get("selected_restock_event_index"),
        })

    return {
        "schema_version":SCHEMA_VERSION,
        "item":{
            "key":key,"name":row.get("item_name"),
            "country":row.get("country"),"country_name":row.get("country_name"),
            "category":row.get("category"),"graph_url":row.get("graph_url"),
        },
        "live":{
            "observed_quantity":row.get("observed_quantity"),
            "last_quantity_change_epoch":_int(row.get("last_quantity_change_epoch")),
            "source_poll_age_seconds":source_poll_age_seconds,
            "fresh":source_poll_age_seconds is not None
                and 0<=source_poll_age_seconds<=FRESH_SECONDS,
        },
        "decision":{
            "status":status,"label":LABELS[status],
            "departure_epoch":dep,"arrival_epoch":arr,
            "departure_deadline_epoch":deadline,
            "leave_in_seconds":max(0,dep-now) if dep is not None else None,
            "flight_seconds":flight,
            "selected_restock_event_index":decision.get("selected_restock_event_index"),
            "source":row.get("departure_source"),
            "recheck_before_departure":True,
        },
        "forecast":{
            "events":timeline,"model_name":row.get("model_name"),
            "event_model_name":row.get("event_model_name"),
            "policy":row.get("policy"),
            "quality_label":row.get("quality_label")
                or "Research estimate — recheck before travel",
        },
        "evidence":{
            "historical":hist,"guaranteed":False,
            "arrival_probability_calibrated":False,
        },
        "copy":{
            "primary_action":(
                "Refresh data" if status=="STALE" else
                "Choose another item" if status in {"NO_SUPPORTED_TRIP","WINDOW_PASSED"} else
                "Recheck before leaving"
            ),
            "safety_note":"Forecasts can change. Confirm the latest estimate before you travel.",
        },
    }


def attach_board_ui(board,*,now):
    """Add ``ui`` to every Travel Decisions row without breaking old clients."""
    if not isinstance(board,dict) or not isinstance(board.get("rows"),list):
        raise ValueError("invalid board")
    age=board.get("source_poll_age_seconds")
    out=dict(board)
    out["ui_contract_version"]=SCHEMA_VERSION
    out["rows"]=[{**row,"ui":build_item_ui(
        row,now=now,source_poll_age_seconds=age)} for row in board["rows"]]
    out["navigation"]=[
        {"id":"overview","label":"Overview","href":"/experimental"},
        {"id":"detail","label":"Item detail","href":"/"},
        {"id":"travel","label":"Travel decisions","href":"/travel-decisions"},
    ]
    return out
