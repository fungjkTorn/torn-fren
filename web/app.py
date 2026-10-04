from pathlib import Path
import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from services.history_service import get_item_history_since, get_stock_catalog, get_stock_graph_analysis, get_latest_item_snapshot
from services.prediction_v2_live import build_live_prediction_v2
from services.admin_health import build_admin_health
from services.forecast_auditor import get_recent_active_forecasts
from services.profitability import enrich_items_with_profitability, profitability_for_item

app = FastAPI(title="Torn Fren Stock Graph")

STATIC_DIR = Path(__file__).parent / "static"

_PREDICTION_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="graph-prediction")
_PREDICTION_LOCK = threading.RLock()
_PREDICTION_CACHE = {}
_PREDICTION_FUTURES = {}
_PREDICTION_CACHE_TTL_SECONDS = 20
_ANALYSIS_CACHE = {}
_ANALYSIS_FUTURES = {}
_ANALYSIS_CACHE_TTL_SECONDS = 20


def _analysis_worker(country, item):
    # Build once with the widest graph window. Per-request event filtering is
    # cheap and avoids rebuilding every historical cycle for each timeframe.
    return get_stock_graph_analysis(country, item, 168)


def _store_analysis_result(key, future):
    try:
        value = future.result()
    except Exception:
        value = None
    with _PREDICTION_LOCK:
        if value is not None:
            _ANALYSIS_CACHE[key] = {"cached_at": time.time(), "value": value}
        if _ANALYSIS_FUTURES.get(key) is future:
            _ANALYSIS_FUTURES.pop(key, None)


def _ensure_analysis_future(country, item):
    key = _prediction_key(country, item)
    with _PREDICTION_LOCK:
        future = _ANALYSIS_FUTURES.get(key)
        if future is None or future.done():
            future = _PREDICTION_EXECUTOR.submit(_analysis_worker, country, item)
            _ANALYSIS_FUTURES[key] = future
            future.add_done_callback(lambda f, k=key: _store_analysis_result(k, f))
    return key, future


def _get_analysis_nonblocking(country, item):
    key = _prediction_key(country, item)
    now = time.time()
    with _PREDICTION_LOCK:
        cached = _ANALYSIS_CACHE.get(key)

    if cached:
        age = now - cached["cached_at"]
        if age > _ANALYSIS_CACHE_TTL_SECONDS:
            _ensure_analysis_future(country, item)
        return cached["value"], age > _ANALYSIS_CACHE_TTL_SECONDS

    key, future = _ensure_analysis_future(country, item)
    try:
        value = future.result(timeout=0.35)
        return _roll_prediction_to_now(value, now), False
    except FutureTimeoutError:
        return None, True


def _analysis_for_window(base_analysis, minutes):
    if base_analysis is None:
        return None
    analysis = dict(base_analysis)
    cutoff = int(time.time()) - int(minutes * 60)
    analysis["events"] = [
        event for event in (base_analysis.get("events") or [])
        if event.get("timestamp", 0) >= cutoff
    ]
    return analysis


def _prediction_key(country, item):
    return (country.lower().strip(), item.lower().strip())


def _latest_safe_leave_timestamp(prediction):
    """
    Reproduce the browser's modeled departure window without rebuilding the
    forecast. Reachability is clock-dependent; point estimates are not.
    """
    if not prediction:
        return None

    estimate = prediction.get("estimate_timestamp")
    calibrated_arrival = prediction.get("recommended_arrival_timestamp")
    late_restock_bound = prediction.get("window_end_timestamp")
    depletion = prediction.get("target_depletion_timestamp")
    lifetime = prediction.get("expected_stock_lifetime_seconds")
    travel = prediction.get("travel_seconds")

    if not travel:
        return None

    earliest_arrival = max(
        calibrated_arrival or estimate or 0,
        late_restock_bound or estimate or 0,
    )
    if not earliest_arrival:
        return None

    depletion_buffer = (
        max(60, min(300, round(float(lifetime) * 0.10)))
        if lifetime else 60
    )
    latest_arrival = (
        float(depletion) - depletion_buffer
        if depletion is not None else None
    )
    if latest_arrival is None or latest_arrival <= earliest_arrival:
        latest_arrival = (
            late_restock_bound or calibrated_arrival or estimate
        )
    if latest_arrival is None:
        return None
    latest_arrival = max(float(latest_arrival), float(earliest_arrival))
    return latest_arrival - float(travel)


def _roll_prediction_to_now(prediction_v2, now=None):
    """
    Cheap time-only refresh for a cached Prediction V2 result.

    Forecast estimates stay frozen. Only per-cycle reachability and the active
    display target are advanced as departure windows expire.
    """
    if not prediction_v2:
        return prediction_v2

    now = time.time() if now is None else float(now)
    result = copy.deepcopy(prediction_v2)
    chain = result.get("predictions") or []

    active = None
    for prediction in chain:
        latest_leave = _latest_safe_leave_timestamp(prediction)
        usable = bool(latest_leave is not None and latest_leave >= now)
        prediction["usable_for_departure"] = usable
        prediction["latest_safe_leave_timestamp"] = (
            int(round(latest_leave)) if latest_leave is not None else None
        )
        if active is None and usable:
            active = prediction

    result["display_prediction"] = active
    result["active_prediction_number"] = (
        active.get("prediction_number") if active else None
    )
    result["cycles_before_active_target"] = (
        max(0, int(active.get("prediction_number", 1)) - 1)
        if active else None
    )
    result["forecast_cycle_count"] = len(chain)

    if active:
        number = int(active.get("prediction_number") or 1)
        if number > 1:
            result["note"] = (
                f"Prediction #{number} is the earliest cycle still reachable "
                f"from the current time. {number - 1} earlier cycle(s) are no "
                "longer usable for departure."
            )
    elif chain:
        result["note"] = (
            "All currently cached forecast departure windows have passed. "
            "Waiting for the next model refresh to extend the chain."
        )

    return result


def _store_prediction_result(key, future):
    try:
        value = future.result()
    except Exception as exc:
        value = {
            "status": "error",
            "note": f"Prediction v2 background calculation failed: {exc}",
        }
    with _PREDICTION_LOCK:
        _PREDICTION_CACHE[key] = {"cached_at": time.time(), "value": value}
        if _PREDICTION_FUTURES.get(key) is future:
            _PREDICTION_FUTURES.pop(key, None)


def _ensure_prediction_future(country, item):
    key = _prediction_key(country, item)
    with _PREDICTION_LOCK:
        future = _PREDICTION_FUTURES.get(key)
        if future is None or future.done():
            future = _PREDICTION_EXECUTOR.submit(build_live_prediction_v2, country, item)
            _PREDICTION_FUTURES[key] = future
            future.add_done_callback(lambda f, k=key: _store_prediction_result(k, f))
    return key, future


def _get_prediction_nonblocking(country, item):
    key = _prediction_key(country, item)
    now = time.time()
    with _PREDICTION_LOCK:
        cached = _PREDICTION_CACHE.get(key)

    if cached and now - cached["cached_at"] <= _PREDICTION_CACHE_TTL_SECONDS:
        return _roll_prediction_to_now(cached["value"], now), False

    key, future = _ensure_prediction_future(country, item)

    if cached:
        # Serve the last known prediction immediately while a fresh one is
        # calculated in the background. The graph auto-refresh will pick up
        # the refreshed result without blocking stock history rendering.
        return _roll_prediction_to_now(cached["value"], now), True

    # Warm-profile predictions normally finish quickly. Give them a tiny chance
    # to complete so users still get prediction + graph in one response. Cold
    # profile builds are allowed to continue in the background instead of
    # holding the graph request for tens of seconds or minutes.
    try:
        value = future.result(timeout=0.35)
        return value, False
    except FutureTimeoutError:
        return {
            "status": "warming",
            "note": "Prediction v2 is calculating in the background. Stock history remains available while the model warms.",
        }, True



@app.get("/api/history")
def api_history(
    country: str = Query(..., min_length=3, max_length=3),
    item: str = Query(..., min_length=1),
    minutes: int = Query(1440, ge=1, le=10080),
):
    country = country.lower().strip()
    item = item.strip()

    if not item:
        raise HTTPException(status_code=400, detail="Item name is required.")

    hours = minutes / 60
    rows = get_item_history_since(country, item, hours)
    latest_item_state = get_latest_item_snapshot(country, item) or {}
    base_analysis, analysis_warming = _get_analysis_nonblocking(country, item)
    analysis = _analysis_for_window(base_analysis, minutes) if base_analysis else {
        "current_stock": rows[-1]["quantity"] if rows else None,
        "current_cost": latest_item_state.get("cost"),
        "current_cost_timestamp": latest_item_state.get("timestamp"),
        "current_cost_source": latest_item_state.get("source"),
        "latest_timestamp": rows[-1]["timestamp"] if rows else None,
        "events": [],
        "prediction": None,
        "analysis_warming": True,
    }
    analysis["analysis_warming"] = bool(analysis_warming)
    # Price is a cheap latest-state lookup and should appear immediately even
    # while historical stats / Prediction v2 are warming in the background.
    analysis["current_cost"] = latest_item_state.get("cost")
    analysis["current_cost_timestamp"] = latest_item_state.get("timestamp")
    analysis["current_cost_source"] = latest_item_state.get("source")

    # Profitability v1 is global/player-agnostic: one inventory slot, PI + pilot,
    # and a 5% Item Market sale fee. Personalized capacity comes later.
    profitability, market_meta = profitability_for_item(country, latest_item_state)
    analysis["profitability"] = profitability
    analysis["market_price_error"] = market_meta.get("error")

    # Prediction v2 is isolated from the base history analysis so a model-side
    # issue cannot take the graph down.  The old prediction is retained as
    # baseline_prediction for diagnostics.
    try:
        prediction_v2, prediction_stale = _get_prediction_nonblocking(country, item)
        analysis["baseline_prediction"] = analysis.get("prediction")
        analysis["prediction_v2"] = prediction_v2
        analysis["prediction_v2_stale"] = bool(prediction_stale)

        display = prediction_v2.get("display_prediction") if prediction_v2 else None
        if display and display.get("estimate_timestamp"):
            # Compatibility shape used by the existing chart overlay.
            analysis["prediction"] = {
                **display,
                "confidence": display.get("travel_reliability"),
                "sample_count": prediction_v2.get("model_evidence_tier"),
                "excluded_sample_count": None,
                "note": prediction_v2.get("note"),
            }
        elif prediction_v2.get("status") == "warming":
            # Do not expose the older baseline predictor as if it were the
            # current Prediction v2 result while the expensive profile warms.
            analysis["prediction"] = None

        analysis["forecast_history"] = get_recent_active_forecasts(
            country,
            item,
            since_timestamp=int(time.time()) - minutes * 60,
            limit=16,
        )
    except Exception as exc:
        analysis["prediction_v2_error"] = str(exc)

    return {
        "country": country,
        "item": item,
        "minutes": minutes,
        "rows": rows,
        "analysis": analysis,
    }


@app.get("/api/catalog")
def api_catalog():
    catalog = get_stock_catalog()
    countries = []
    market_meta = None
    for entry in catalog.get("countries", []):
        items, meta = enrich_items_with_profitability(entry.get("country"), entry.get("items") or [])
        market_meta = market_meta or meta
        countries.append({**entry, "items": items})
    return {
        "countries": countries,
        "profitability": {
            "basis": "one slot · PI + pilot round trip · 5% Item Market fee",
            "market_price_source": "Torn market value",
            "market_price_fetched_at": (market_meta or {}).get("fetched_at"),
            "market_price_stale": bool((market_meta or {}).get("stale")),
            "market_price_error": (market_meta or {}).get("error"),
        },
    }


@app.get("/api/admin/health")
def api_admin_health():
    return build_admin_health()


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")