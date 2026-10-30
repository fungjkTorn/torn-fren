"""First ten items: first reachable stock window, then frozen timing refinement.

An additive, read-only publisher entry point, not wired into the website yet.
The event forecaster determines reachability. V18/V19 can refine timing only
inside that first window; unsupported timing never suppresses the window or
causes a search of later events. No model tournaments or gameplay actions.
"""
from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sqlite3
import time
from types import MappingProxyType

from services.travel_decision_contract_v166 import (
    build_item_travel_decision, STATUS_ACTIVE, STATUS_WAIT,
)

# Identities are the ten incumbents, not V174's screened challengers.
FIRST_RELEASE_MODELS = MappingProxyType({
    "arg:Ceibo Flower": ("v18", "dyn3"),
    "can:Crocus": ("v18", "dyn5"),
    "cay:Banana Orchid": ("v18", "dyn7"),
    "haw:Orchid": ("v18", "dyn3"),
    "jap:Cherry Blossom": ("v19", "dyn2"),
    "mex:Dahlia": ("v18", "dyn2"),
    "mex:Jaguar Plushie": ("v18", "dyn3"),
    "swi:Edelweiss": ("v19", "dyn9"),
    "uae:Tribulus Omanense": ("v18", "dyn3"),
    "uni:Heather": ("v18", "dyn3"),
})
MIN_QUANTITY = 31  # The requested live rule is stock >30, not >=30.
MAX_TIMING_POINTS = 64


def _delays(earliest, latest, now):
    """Bound computation within ONE event without a calendar horizon cap."""
    span = latest - earliest
    if span <= 300 * (MAX_TIMING_POINTS - 1):
        points = list(range(earliest, latest + 1, 300))
        if points[-1] != latest:
            points.append(latest)
    else:
        points = [earliest + span * i // (MAX_TIMING_POINTS - 1)
                  for i in range(MAX_TIMING_POINTS)]
    return [p - now for p in sorted(set(points))]


def build_first_release_decision(forecast, *, now, flight_seconds,
                                 poll_age_seconds, timing_choice=None,
                                 model_roster=FIRST_RELEASE_MODELS):
    """Pure decision policy. timing_choice may only select from supplied delays.

    Forecasts must explicitly model >=31. Model confidence is advisory, not
    permission to omit an otherwise reachable opportunity. Missing/stale data
    still prevents recommendations. Inputs are never modified.
    """
    key = forecast.get("item_key")
    if key not in model_roster:
        raise ValueError("item is outside the first-release roster")
    generation, config = model_roster[key]
    result = build_item_travel_decision(
        forecast, now=now, player_flight_seconds=flight_seconds,
        poll_age_seconds=poll_age_seconds, target_qty=MIN_QUANTITY,
        grace_seconds=0, arrival_policy="expected",
    )
    result.update(
        scheduling_policy="FIRST_REACHABLE_EVENT_BEFORE_TIMING_SCORE",
        timing_model_generation=generation, timing_model_config=config,
        timing_refinement_status="NOT_RUN", model_selection_changed=False,
        live_accuracy_verified=False, historical_percentages_do_not_transfer=True,
    )
    if result["estimated_departure_epoch"] is None:
        return result
    index = result["selected_restock_event_index"]
    selected = (result["current_stock_candidate"] if index == 0 else
                next(e for e in result["forecast_events"] if e["index"] == index))
    earliest = selected["estimated_departure_start_epoch"]
    latest = selected["estimated_latest_departure_epoch"]
    departure = earliest
    if timing_choice is not None:
        delays = _delays(earliest, latest, now)
        proposal = timing_choice(
            item_key=key, generation=generation, config=config,
            now=now, flight_seconds=flight_seconds,
            min_quantity=MIN_QUANTITY, delays=tuple(delays),
        )
        if proposal is None:
            result["timing_refinement_status"] = "UNAVAILABLE_USING_EVENT_ESTIMATE"
        elif (isinstance(proposal, dict)
              and type(proposal.get("departure")) is int
              and proposal["departure"] - now in delays):
            departure = proposal["departure"]
            result["timing_refinement_status"] = "REFINED_WITHIN_FIRST_EVENT"
            result["advisory_timing_score"] = proposal.get("score")
        else:
            result["timing_refinement_status"] = "REJECTED_OUTSIDE_FIRST_EVENT"
    else:
        result["timing_refinement_status"] = "NOT_REQUESTED_USING_EVENT_ESTIMATE"
    result.update(
        estimated_departure_epoch=departure,
        estimated_arrival_epoch=departure + flight_seconds,
        estimated_arrival_plus_grace_epoch=departure + flight_seconds,
        departure_countdown_seconds=departure - now,
        status=STATUS_ACTIVE if departure == now else STATUS_WAIT,
        reason="FIRST_REACHABLE_WINDOW_SELECTED",
    )
    return result


def native_timing_choice(db, *, model_roster=FIRST_RELEASE_MODELS,
                         full_history=False, **request):
    """Run exactly one frozen configuration against a read-only source.

    Use in an isolated publisher process: the legacy engines share a module
    history adapter. Restore its globals even if inference raises an error.
    No source data may be newer than the requested issue time.
    """
    from services import history_service
    from services.frozen_candidate_worker_v31 import (
        _install_frozen_readonly_history, inspect_live_source,
    )
    if model_roster.get(request["item_key"]) != (
            request["generation"], request["config"]):
        raise ValueError("frozen model identity mismatch")
    source = inspect_live_source(db, request["now"])
    if source["status"] != "FRESH":
        raise ValueError("native timing source is not fresh and causal: " + source["status"])
    engine = importlib.import_module(
        "services.plushie_flower_dynamic_planner_" + request["generation"])
    config = next(c for c in engine.configs() if c.name == request["config"])
    if type(full_history) is not bool:
        raise ValueError("full_history must be an explicit boolean")
    if full_history:
        config = replace(config, lookback_points=None)
    saved = {name: getattr(history_service, name) for name in
             ("DB_PATH", "_connect", "init_db", "_DB_READY")}
    try:
        _install_frozen_readonly_history(history_service, db)
        from services.native_history_acceleration import immutable_history_queries
        with immutable_history_queries(history_service,engine) if full_history else nullcontext():
            country, item = request["item_key"].split(":", 1)
            quantity = request["min_quantity"]
            loaded = engine.load_item(country, item, quantity)
            cleaned, cycles = loaded[:2]
            if request["generation"] in ("v19","v20"):
                gaps = engine.normalize_gaps(history_service.get_collection_gaps())
                timeline = engine.Timeline(cleaned, cycles, quantity, gaps=gaps)
                deps, features = engine.completed_cycle_features(cycles, gaps=gaps)
            else:
                timeline = engine.Timeline(cleaned, cycles, quantity)
                deps, features = engine.completed_cycle_features(cycles)
            points = engine.build_points(timeline, deps, features, 600)
            if len(points) < 60:
                return None
            proposal = engine.plan(
                float(request["now"]), points, [p.t for p in points],
                timeline, deps, features, config, list(request["delays"]),
                request["flight_seconds"], 0,
            )
            if proposal is None:
                return None
            return {"departure": int(proposal["departure_time"]),
                    "score": proposal.get("probability")}
    finally:
        for name, value in saved.items():
            setattr(history_service, name, value)


def forecast_first_release_item(source, item_key, *, now, flight_seconds,
                                model_roster=FIRST_RELEASE_MODELS,
                                timing_full_history=False):
    """Fresh, causal, read-only one-item pipeline; no production writes.

    Shared empirical stocked/depleted phases generate the event timeline.
    The named incumbent refines timing, rather than inventing a second event
    calendar. Forecasts and scheduling remain explicitly uncalibrated.
    """
    if item_key not in model_roster:
        raise ValueError("item is outside the first-release roster")
    from deploy.scripts.v163_readonly_event_first_preview import predict_events
    from research.v128_full24_earliest_shadow import _read_item
    from research.v145_provider_continuous_phases import provider_continuous_phases
    from services.frozen_candidate_worker_v31 import inspect_live_source
    source = Path(source).resolve(strict=True)
    health = inspect_live_source(source, now)
    if health["status"] != "FRESH":
        return {"item_key": item_key, "status": health["status"],
                "estimated_departure_epoch": None, "source": health}
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        rows, error = _read_item(db, item_key, now)
        if error:
            raise ValueError(error)
        gaps = db.execute(
            "SELECT start_timestamp,end_timestamp FROM collection_gaps "
            "WHERE start_timestamp<=? ORDER BY start_timestamp", (now,),
        ).fetchall()
    phases = provider_continuous_phases(
        rows, asof=now, gaps=gaps, min_qty=MIN_QUANTITY)
    forecast = predict_events(
        item_key, phases, asof=now, horizon=None, min_qty=MIN_QUANTITY)
    forecast["phase_definition"] = "STOCK_ABOVE_30_PURCHASE_AVAILABILITY"
    # Legacy field names say below_30; expose the actual >=31 semantics too.
    for event in forecast["restock_events"]:
        event["predicted_stock_below_threshold_epoch"] = event["predicted_stock_below_30_epoch"]
    decision = build_first_release_decision(
        forecast, now=now, flight_seconds=flight_seconds,
        poll_age_seconds=now - health["last_successful_heartbeat"],
        timing_choice=lambda **kw: native_timing_choice(source,model_roster=model_roster,
            full_history=timing_full_history,**kw),
        model_roster=model_roster,
    )
    return {"item_key": item_key, "asof_epoch": now,
            "forecast": forecast, "decision": decision,
            "collector_written": False, "production_deployed": False,
            "timing_full_history_override": timing_full_history,
            "country_specific_freshness_verified": False}


def freeze_trip(decision, *, opportunity_id, existing=None):
    """Immutable evaluation record: refreshes cannot move an issued trip.

    The evaluator must supply a stable physical-opportunity ID, not a tick
    timestamp or the forecast's mutable ordinal. This does not freeze the UI.
    It requires neither a user departure nor a real player flight.
    """
    if not isinstance(opportunity_id, str) or not opportunity_id:
        raise ValueError("stable opportunity identity required")
    if existing is not None:
        if (existing.get("opportunity_id") != opportunity_id
                or existing.get("item_key") != decision.get("item_key")):
            raise ValueError("trip identity mismatch")
        return deepcopy(existing)
    if decision.get("estimated_departure_epoch") is None:
        raise ValueError("no departure to record")
    return {"opportunity_id": opportunity_id,
            "item_key": decision["item_key"],
            "issued_epoch": decision["asof_epoch"],
            "departure_epoch": decision["estimated_departure_epoch"],
            "arrival_epoch": decision["estimated_arrival_epoch"],
            "min_quantity": MIN_QUANTITY,
            "model_generation": decision["timing_model_generation"],
            "model_config": decision["timing_model_config"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--item", required=True, choices=tuple(FIRST_RELEASE_MODELS))
    parser.add_argument("--flight-seconds", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(forecast_first_release_item(
        args.source, args.item, now=int(time.time()),
        flight_seconds=args.flight_seconds), sort_keys=True))


if __name__ == "__main__":
    main()
