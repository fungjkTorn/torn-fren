import json
import math
import statistics
import threading
import time
from pathlib import Path

from services.arrival_success_lab import TRAVEL_SECONDS, _coverage_interval
from services.cycle_feature_lab import (
    _percentile,
    _tertile_prediction,
    build_cycle_feature_rows,
)
from services.history_service import (
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _prediction_anchor_is_currently_trustworthy,
    _suppress_provider_bounces,
)
from services.medium_model_lab import (
    _bucket2_prediction,
    _ridge_prediction,
    _tree_leaf_prediction,
    _weighted_recent,
    analyze_advanced_item,
)
from services.prediction_v2_preflight import build_prediction_v2_preflight


_PROFILE_CACHE = {}
_PROFILE_REFRESHING = set()
_PROFILE_LOCK = threading.Lock()
PROFILE_TTL_SECONDS = 10 * 60
DISK_PROFILE_SOFT_TTL_SECONDS = 60 * 60
DISK_PROFILE_MAX_STALE_SECONDS = 24 * 60 * 60
PROFILE_SCHEMA_VERSION = "v2.4"
_PROFILE_CACHE_FILE = Path(__file__).parent.parent / "data" / "prediction_v2_profiles.json"


# Reachable-cycle forecast limits.
# We keep forecasting until we find the earliest cycle a traveler can still
# leave for, plus one backup cycle, without projecting forever.
MAX_FORECAST_CYCLES = 8
MAX_FORECAST_HORIZON_SECONDS = 12 * 60 * 60
BACKUP_CYCLES_AFTER_TARGET = 1


def _median(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _pctl(values, p):
    vals = [v for v in values if v is not None]
    return _percentile(vals, p) if vals else None


def _safe_int(value):
    return None if value is None else int(round(value))


def _downgrade_reliability(label):
    order = ["insufficient", "unreliable", "marginal", "good", "excellent"]
    if label not in order:
        return "insufficient"
    return order[max(0, order.index(label) - 1)]


def _current_state(country, item_name):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, bounces = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    if not rows:
        return None

    cycles, active_cycle, wait_samples = _build_validated_cycles(rows)
    completed = [
        c for c in cycles
        if c.get("complete") and not c.get("tiny_restock")
    ]
    valid_completed = [
        c for c in completed
        if c.get("valid_lifetime") and c.get("lifetime_seconds")
    ]
    valid_waits = [s for s in wait_samples if s.get("valid")]

    return {
        "rows": rows,
        "current_stock": rows[-1][1],
        "latest_timestamp": rows[-1][0],
        "completed": completed,
        "valid_completed": valid_completed,
        "active_cycle": active_cycle,
        "valid_waits": valid_waits,
        "provider_bounces": bounces,
    }


def _build_current_depletion_feature(country, item_name, state, feature_rows):
    if state["current_stock"] != 0 or not state["completed"]:
        return None

    previous = state["completed"][-1]
    if previous.get("depletion_time") is None:
        return None

    waits = [r["target_wait_seconds"] for r in feature_rows]
    lifetimes = [
        r.get("prev_lifetime_seconds")
        for r in feature_rows
        if r.get("prev_lifetime_seconds") is not None
    ]
    peaks = [
        r.get("prev_peak_quantity")
        for r in feature_rows
        if r.get("prev_peak_quantity") is not None
    ]

    lifetime = previous.get("lifetime_seconds")
    peak = previous.get("peak_quantity")
    first_seen = previous.get("first_seen_quantity")
    peak_delay = None
    if previous.get("peak_time") and previous.get("restock_time"):
        peak_delay = previous["peak_time"] - previous["restock_time"]

    depletion_rate = None
    if lifetime and lifetime > 0 and peak is not None:
        depletion_rate = peak / (lifetime / 60)

    depletion_ts = previous["depletion_time"]
    depletion_hour = (depletion_ts % 86400) / 3600
    angle = 2 * math.pi * depletion_hour / 24

    recent5_peak = _median(peaks[-5:])
    recent5_lifetime = _median(lifetimes[-5:])

    return {
        "anchor_timestamp": depletion_ts,
        "target_wait_seconds": None,
        "prev_peak_quantity": peak,
        "prev_first_seen_quantity": first_seen,
        "prev_lifetime_seconds": lifetime,
        "prev_peak_delay_seconds": peak_delay,
        "prev_depletion_rate_per_minute": depletion_rate,
        "previous_wait_seconds": waits[-1] if waits else None,
        "recent3_wait_median_seconds": _median(waits[-3:]),
        "recent5_wait_median_seconds": _median(waits[-5:]),
        "recent10_wait_median_seconds": _median(waits[-10:]),
        "recent3_lifetime_median_seconds": _median(lifetimes[-3:]),
        "recent5_lifetime_median_seconds": recent5_lifetime,
        "peak_vs_recent5_ratio": (peak / recent5_peak) if peak and recent5_peak else None,
        "lifetime_vs_recent5_ratio": (
            lifetime / recent5_lifetime
            if lifetime and recent5_lifetime else None
        ),
        "depletion_hour_sin": math.sin(angle),
        "depletion_hour_cos": math.cos(angle),
        "depletion_weekday": int((depletion_ts // 86400 + 3) % 7),
    }


def _estimate_wait(model_name, training, current):
    waits = [r["target_wait_seconds"] for r in training]
    if not waits:
        return None

    core = [
        "prev_peak_quantity",
        "prev_lifetime_seconds",
        "prev_depletion_rate_per_minute",
        "previous_wait_seconds",
        "recent3_wait_median_seconds",
        "recent5_wait_median_seconds",
    ]
    expanded = core + [
        "peak_vs_recent5_ratio",
        "lifetime_vs_recent5_ratio",
        "depletion_hour_sin",
        "depletion_hour_cos",
    ]
    tree_features = [
        "prev_peak_quantity",
        "prev_lifetime_seconds",
        "prev_depletion_rate_per_minute",
        "previous_wait_seconds",
        "recent3_wait_median_seconds",
        "peak_vs_recent5_ratio",
        "depletion_hour_sin",
        "depletion_hour_cos",
    ]

    if model_name in {"baseline_all_median", "depletion/all_median"}:
        estimate = statistics.median(waits)
    elif model_name == "recent10_median":
        estimate = statistics.median(waits[-10:])
    elif model_name == "weighted_recent10":
        estimate = _weighted_recent(waits)
    elif model_name == "peak_tertile_median":
        estimate = _tertile_prediction(training, "prev_peak_quantity", current)
    elif model_name == "peak_x_prevwait_bucket":
        estimate = _bucket2_prediction(
            training, current, "prev_peak_quantity", "previous_wait_seconds"
        )
    elif model_name == "peak_x_lifetime_bucket":
        estimate = _bucket2_prediction(
            training, current, "prev_peak_quantity", "prev_lifetime_seconds"
        )
    elif model_name == "ridge_core_l1":
        estimate = _ridge_prediction(training, current, core, ridge_lambda=1.0)
    elif model_name == "ridge_core_l10":
        estimate = _ridge_prediction(training, current, core, ridge_lambda=10.0)
    elif model_name == "ridge_expanded_l10":
        estimate = _ridge_prediction(training, current, expanded, ridge_lambda=10.0)
    elif model_name == "ridge_residual_recent5":
        estimate = _ridge_prediction(
            training,
            current,
            expanded,
            ridge_lambda=10.0,
            residual_base_key="recent5_wait_median_seconds",
        )
    elif model_name == "tree_depth2":
        estimate = _tree_leaf_prediction(
            training, current, tree_features, max_depth=2, min_leaf=5
        )
    else:
        estimate = statistics.median(waits)

    if estimate is None or not math.isfinite(estimate) or estimate <= 0:
        return statistics.median(waits)
    return float(estimate)


def _read_disk_profiles():
    try:
        if not _PROFILE_CACHE_FILE.exists():
            return {}
        return json.loads(_PROFILE_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_disk_profile(key, value):
    try:
        _PROFILE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _PROFILE_LOCK:
            all_profiles = _read_disk_profiles()
            all_profiles[key] = {
                "generated_at": int(time.time()),
                "value": value,
            }
            tmp = _PROFILE_CACHE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(all_profiles, indent=2), encoding="utf-8")
            tmp.replace(_PROFILE_CACHE_FILE)
    except Exception:
        # Cache failure must never break live prediction.
        pass


def _calculate_profile(country, item_name):
    preflight = build_prediction_v2_preflight(country, item_name)
    chosen = preflight.get("chosen") or {}
    model_name = chosen.get("model") or "baseline_all_median"
    policy = chosen.get("policy") or "lifetime"

    analysis = analyze_advanced_item(country, item_name)
    records = analysis.get("records_by_model", {}).get(model_name, [])

    median_lifetime = preflight.get("median_stock_lifetime_seconds")
    restock_window = _coverage_interval(
        records,
        target=0.90,
        max_width_seconds=median_lifetime,
    )

    if restock_window:
        window_lo, window_hi, window_width = restock_window
    else:
        window_lo = window_hi = window_width = None

    learned_arrival_offset = chosen.get("current_arrival_offset_seconds")

    # If there is not enough arrival-history to learn the ideal offset yet,
    # still provide a best-effort target rather than leaving arrival/leave-by blank.
    # Targeting the middle of the typical stock lifetime gives the largest symmetric
    # timing cushion around an uncertain restock estimate.
    fallback_arrival_offset = None
    if learned_arrival_offset is None and median_lifetime:
        fallback_arrival_offset = float(median_lifetime) * 0.50

    return {
        "preflight": preflight,
        "model_name": model_name,
        "arrival_policy": policy,
        "arrival_offset_seconds": (
            learned_arrival_offset
            if learned_arrival_offset is not None
            else fallback_arrival_offset
        ),
        "arrival_offset_source": (
            "learned"
            if learned_arrival_offset is not None
            else "mid-stock fallback" if fallback_arrival_offset is not None
            else "unavailable"
        ),
        "arrival_success_rate": chosen.get("arrival_success_rate"),
        "recent20_success_rate": chosen.get("recent20_success_rate"),
        "recent10_success_rate": chosen.get("recent10_success_rate"),
        "travel_reliability": preflight.get("travel_reliability", "insufficient"),
        "model_evidence_tier": preflight.get("model_evidence_tier", "sparse"),
        "ready_for_live_guidance": bool(preflight.get("ready_for_live_guidance")),
        "caution_only": bool(preflight.get("caution_only")),
        "median_stock_lifetime_seconds": median_lifetime,
        "restock_window_lo_error_seconds": window_lo,
        "restock_window_hi_error_seconds": window_hi,
        "restock_window_width_seconds": window_width,
        "behavior_class": preflight.get("behavior_class"),
    }


def _background_refresh_profile(country, item_name, key):
    try:
        value = _calculate_profile(country, item_name)
        _PROFILE_CACHE[(country.lower(), item_name.lower())] = {
            "cached_at": time.time(),
            "value": value,
        }
        _write_disk_profile(key, value)
    finally:
        with _PROFILE_LOCK:
            _PROFILE_REFRESHING.discard(key)


def _profile(country, item_name, force=False):
    mem_key = (country.lower(), item_name.lower())
    disk_key = f"{PROFILE_SCHEMA_VERSION}::{country.lower()}::{item_name.lower()}"
    now = time.time()

    cached = _PROFILE_CACHE.get(mem_key)
    if (
        not force
        and cached is not None
        and now - cached["cached_at"] < PROFILE_TTL_SECONDS
    ):
        return cached["value"]

    # Persistent cache prevents a browser refresh from waiting ~10-20 seconds
    # for the full walk-forward selector after every server restart.
    if not force:
        disk = _read_disk_profiles().get(disk_key)
        if disk and disk.get("value"):
            age = now - float(disk.get("generated_at") or 0)
            if age <= DISK_PROFILE_MAX_STALE_SECONDS:
                value = disk["value"]
                _PROFILE_CACHE[mem_key] = {
                    "cached_at": now,
                    "value": value,
                }

                # Serve the known-good profile immediately, then refresh it in
                # the background when it is over an hour old. This lets rolling
                # metrics improve without making the graph request block.
                if age > DISK_PROFILE_SOFT_TTL_SECONDS:
                    with _PROFILE_LOCK:
                        if disk_key not in _PROFILE_REFRESHING:
                            _PROFILE_REFRESHING.add(disk_key)
                            threading.Thread(
                                target=_background_refresh_profile,
                                args=(country, item_name, disk_key),
                                daemon=True,
                            ).start()
                return value

    # First-ever calculation for an item is necessarily slower. The result is
    # persisted so subsequent graph/bot processes can reuse it immediately.
    value = _calculate_profile(country, item_name)
    _PROFILE_CACHE[mem_key] = {"cached_at": now, "value": value}
    _write_disk_profile(disk_key, value)
    return value

def _conditional_zero_wait(feature_rows, elapsed):
    """
    If the item is still at zero after the original estimate/window has become
    stale, condition on historical waits that ALSO survived at least this long.

    This is much safer than leaving an old prediction on screen or blindly
    jumping to "cycle #2" when cycle #1 never actually occurred.
    """
    waits = sorted(r["target_wait_seconds"] for r in feature_rows)
    survivors = [w for w in waits if w >= elapsed]
    if len(survivors) < 3:
        return None

    target_total_wait = statistics.median(survivors)
    lo = _pctl(survivors, 0.10)
    hi = _pctl(survivors, 0.90)
    return {
        "sample_count": len(survivors),
        "estimate_total_wait_seconds": max(float(elapsed), float(target_total_wait)),
        "window_total_wait_lo_seconds": max(float(elapsed), float(lo)),
        "window_total_wait_hi_seconds": max(float(elapsed), float(hi)),
    }


def _make_prediction(
    *,
    number,
    estimate,
    window_start,
    window_end,
    arrival_offset,
    travel_seconds,
    reliability,
    evidence_tier,
    model_name,
    method,
    projected=False,
    success_rate=None,
    recent20=None,
    recent10=None,
    now=None,
):
    now = time.time() if now is None else now
    arrival = (
        estimate + arrival_offset
        if estimate is not None and arrival_offset is not None
        else None
    )
    leave_by = (
        arrival - travel_seconds
        if arrival is not None and travel_seconds is not None
        else None
    )

    usable = True
    if leave_by is not None and leave_by <= now:
        usable = False
    if window_end is not None and travel_seconds is not None:
        latest_possible_leave = window_end - travel_seconds
        if latest_possible_leave <= now:
            usable = False

    return {
        "prediction_number": number,
        "estimate_timestamp": _safe_int(estimate),
        "window_start_timestamp": _safe_int(window_start),
        "window_end_timestamp": _safe_int(window_end),
        "recommended_arrival_timestamp": _safe_int(arrival),
        "recommended_leave_by_timestamp": _safe_int(leave_by),
        "travel_seconds": _safe_int(travel_seconds),
        "travel_reliability": reliability,
        "model_evidence_tier": evidence_tier,
        "model_name": model_name,
        "method": method,
        "projected": bool(projected),
        "arrival_success_rate": success_rate,
        "recent20_arrival_success_rate": recent20,
        "recent10_arrival_success_rate": recent10,
        "usable_for_departure": bool(usable),
    }


def _annotate_arrival_source(prediction, profile):
    if prediction is not None:
        prediction["arrival_offset_source"] = profile.get("arrival_offset_source")
        prediction["arrival_guidance_calibrated"] = (
            profile.get("arrival_offset_source") == "learned"
        )
    return prediction



def _projection_reliability(base_label, cycle_number, raw_window_width, median_lifetime):
    """
    Projection reliability is separate from the item's base travel reliability.

    Each unobserved cycle adds timing uncertainty. We downgrade gradually by
    projection depth, and force UNRELIABLE if the raw projected restock window
    becomes as wide as (or wider than) the item's normal stock lifetime.
    """
    label = base_label
    # P1 can be observed-anchor or a one-cycle projection.  Extra future cycles
    # beyond that get progressively less trustworthy.
    extra_steps = max(0, int(cycle_number) - 1)
    for _ in range(extra_steps):
        label = _downgrade_reliability(label)

    if (
        raw_window_width is not None
        and median_lifetime
        and raw_window_width >= median_lifetime
    ):
        label = "unreliable"

    return label


def _project_future_chain(
    *,
    first_prediction,
    profile,
    median_lifetime,
    median_wait,
    lifetimes,
    waits,
    travel_seconds,
    now,
    start_number=1,
    first_is_projected=True,
):
    """
    Build a rolling forecast chain P1..Pn.

    The first prediction is supplied by the caller (observed depletion anchor or
    next-cycle projection). Each following cycle advances by:
        expected stock lifetime + expected zero->restock wait

    We stop after finding the earliest reachable cycle plus one backup, or after
    MAX_FORECAST_CYCLES / MAX_FORECAST_HORIZON_SECONDS.

    The chain is rebuilt from current observed state on every request. As actual
    restocks/depletions occur, future cycles automatically re-anchor and tighten.
    """
    if first_prediction is None:
        return []

    chain = [first_prediction]
    if not median_lifetime or not median_wait:
        return chain

    life_mad = (
        statistics.median(abs(v - median_lifetime) for v in lifetimes)
        if len(lifetimes) >= 3
        else median_lifetime * 0.15
    )
    wait_mad = (
        statistics.median(abs(v - median_wait) for v in waits)
        if len(waits) >= 3
        else median_wait * 0.15
    )

    first_window_start = first_prediction.get("window_start_timestamp")
    first_window_end = first_prediction.get("window_end_timestamp")
    first_estimate = first_prediction.get("estimate_timestamp")
    if first_estimate is None:
        return chain

    if first_window_start is not None and first_window_end is not None:
        raw_half = max(
            60.0,
            (float(first_window_end) - float(first_window_start)) / 2.0,
        )
    else:
        raw_half = max(60.0, (life_mad + wait_mad))

    active_found_at = None
    if first_prediction.get("usable_for_departure"):
        active_found_at = 0

    while len(chain) < MAX_FORECAST_CYCLES:
        prev = chain[-1]
        prev_estimate = prev.get("estimate_timestamp")
        if prev_estimate is None:
            break

        next_estimate = float(prev_estimate) + float(median_lifetime) + float(median_wait)
        if next_estimate - now > MAX_FORECAST_HORIZON_SECONDS:
            break

        # Uncertainty grows with every projected lifetime + drought pair.
        raw_half = raw_half + float(life_mad) + float(wait_mad)
        raw_width = raw_half * 2.0

        # For display, never draw a "restock window" wider than typical stock
        # lifetime. We preserve raw width separately and downgrade reliability
        # when the projection has become too uncertain.
        display_half = raw_half
        window_capped = False
        if median_lifetime and display_half * 2.0 >= median_lifetime:
            display_half = float(median_lifetime) * 0.49
            window_capped = True

        number = start_number + len(chain)
        reliability = _projection_reliability(
            profile["travel_reliability"],
            number,
            raw_width,
            median_lifetime,
        )

        nxt = _make_prediction(
            number=number,
            estimate=next_estimate,
            window_start=next_estimate - display_half,
            window_end=next_estimate + display_half,
            arrival_offset=profile["arrival_offset_seconds"],
            travel_seconds=travel_seconds,
            reliability=reliability,
            evidence_tier=profile["model_evidence_tier"],
            model_name=f"projected cycle +{number - 1}",
            method=(
                "rolling cycle projection: previous restock + median stock lifetime "
                "+ median depletion→restock wait"
            ),
            projected=True,
            success_rate=None,
            recent20=None,
            recent10=None,
            now=now,
        )
        nxt = _annotate_arrival_source(nxt, profile)
        nxt["projection_depth"] = number - 1
        nxt["raw_projected_window_width_seconds"] = _safe_int(raw_width)
        nxt["window_capped_to_stock_lifetime"] = bool(window_capped)
        chain.append(nxt)

        if active_found_at is None and nxt.get("usable_for_departure"):
            active_found_at = len(chain) - 1
        elif active_found_at is not None:
            # Keep one backup cycle after the active reachable target.
            if len(chain) - 1 >= active_found_at + BACKUP_CYCLES_AFTER_TARGET:
                break

    return chain


def _select_active_forecast(chain):
    """Return the earliest cycle whose recommended departure is still usable."""
    for prediction in chain:
        if prediction.get("usable_for_departure"):
            return prediction
    return None


def _forecast_chain_summary(chain, active):
    if not chain:
        return {
            "forecast_cycle_count": 0,
            "cycles_before_active_target": None,
            "active_prediction_number": None,
        }

    active_number = active.get("prediction_number") if active else None
    return {
        "forecast_cycle_count": len(chain),
        "cycles_before_active_target": (
            max(0, int(active_number) - 1) if active_number is not None else None
        ),
        "active_prediction_number": active_number,
    }


def _build_live_prediction_v2_impl(country, item_name, now_timestamp=None, force_profile=False):
    now = time.time() if now_timestamp is None else float(now_timestamp)
    country = country.lower().strip()
    item_name = item_name.strip()

    state = _current_state(country, item_name)
    if not state:
        return {
            "status": "no_history",
            "note": "No stock history is available for this item yet.",
            "prediction_1": None,
            "prediction_2": None,
            "predictions": [],
            "display_prediction": None,
        }

    profile = _profile(country, item_name, force=force_profile)
    feature_rows, _ = build_cycle_feature_rows(country, item_name)
    waits = [r["target_wait_seconds"] for r in feature_rows]
    lifetimes = [
        c["lifetime_seconds"]
        for c in state["valid_completed"]
        if c.get("lifetime_seconds")
    ]
    median_wait = _median(waits)
    median_lifetime = profile["median_stock_lifetime_seconds"] or _median(lifetimes)
    travel_seconds = TRAVEL_SECONDS.get(country)

    base = {
        "status": None,
        "current_stock": state["current_stock"],
        "behavior_class": profile["behavior_class"],
        "model_name": profile["model_name"],
        "arrival_policy": profile["arrival_policy"],
        "arrival_offset_source": profile.get("arrival_offset_source"),
        "model_evidence_tier": profile["model_evidence_tier"],
        "travel_reliability": profile["travel_reliability"],
        "ready_for_live_guidance": profile["ready_for_live_guidance"],
        "caution_only": profile["caution_only"],
        "arrival_success_rate": profile["arrival_success_rate"],
        "recent20_arrival_success_rate": profile["recent20_success_rate"],
        "recent10_arrival_success_rate": profile["recent10_success_rate"],
        "median_stock_lifetime_seconds": _safe_int(median_lifetime),
        "median_zero_wait_seconds": _safe_int(median_wait),
        "travel_seconds": _safe_int(travel_seconds),
        "forecast_horizon_seconds": MAX_FORECAST_HORIZON_SECONDS,
        "max_forecast_cycles": MAX_FORECAST_CYCLES,
        "prediction_1": None,
        "prediction_2": None,
        "predictions": [],
        "display_prediction": None,
        "note": "",
    }

    # ------------------------------------------------------------------
    # ZERO STOCK: next restock is anchored to the known clean depletion.
    # ------------------------------------------------------------------
    if state["current_stock"] == 0:
        current = _build_current_depletion_feature(
            country, item_name, state, feature_rows
        )
        if current is None:
            base["status"] = "waiting_for_depletion_anchor"
            base["note"] = "Zero stock is visible, but no qualified depletion anchor is available."
            return base

        anchor = current["anchor_timestamp"]
        trustworthy, reason = _prediction_anchor_is_currently_trustworthy(
            anchor, int(now)
        )
        if not trustworthy:
            base["status"] = "waiting_for_clean_anchor"
            base["note"] = (
                "Historical model data is usable, but the current depletion anchor "
                f"is not trustworthy: {reason}"
            )
            return base

        estimated_wait = _estimate_wait(
            profile["model_name"], feature_rows, current
        )
        estimate = anchor + estimated_wait

        lo_err = profile["restock_window_lo_error_seconds"]
        hi_err = profile["restock_window_hi_error_seconds"]
        if lo_err is not None and hi_err is not None:
            window_start = estimate + lo_err
            window_end = estimate + hi_err
        else:
            # Fallback is deliberately labelled as uncalibrated below.
            abs_errors = []
            analysis = analyze_advanced_item(country, item_name)
            recs = analysis.get("records_by_model", {}).get(profile["model_name"], [])
            abs_errors = [r["absolute_error_seconds"] for r in recs]
            spread = _pctl(abs_errors, 0.90) if len(abs_errors) >= 5 else None
            if spread is None:
                spread = min(
                    (median_lifetime or 20 * 60) * 0.35,
                    max(60, statistics.median(waits) * 0.10 if waits else 5 * 60),
                )
            # Never claim a fallback window wider than normal stock lifetime.
            spread = min(float(spread), (median_lifetime or spread * 3) * 0.45)
            window_start = estimate - spread
            window_end = estimate + spread

        method = f"{profile['model_name']} from clean depletion anchor"
        elapsed = max(0, now - anchor)

        # If the original predicted restock window has passed and the item is
        # STILL zero, do not leave a dead prediction on screen. Recondition the
        # wait on the fact that this drought has survived this long.
        if now > window_end:
            conditional = _conditional_zero_wait(feature_rows, elapsed)
            if conditional:
                estimate = anchor + conditional["estimate_total_wait_seconds"]
                window_start = anchor + conditional["window_total_wait_lo_seconds"]
                window_end = anchor + conditional["window_total_wait_hi_seconds"]
                method = (
                    f"conditional drought update ({conditional['sample_count']} historical waits "
                    "survived this long)"
                )
                # Conditional droughts are inherently less certain.
                reliability = _downgrade_reliability(profile["travel_reliability"])
            else:
                reliability = "unreliable"
                # Keep a point estimate for reference but remove recommendation confidence.
                estimate = max(estimate, now)
                window_start = max(window_start, now)
                window_end = max(window_end, now + 60)
                method = "overdue drought; insufficient matching historical waits"
        else:
            reliability = profile["travel_reliability"]

        p1 = _make_prediction(
            number=1,
            estimate=estimate,
            window_start=window_start,
            window_end=window_end,
            arrival_offset=profile["arrival_offset_seconds"],
            travel_seconds=travel_seconds,
            reliability=reliability,
            evidence_tier=profile["model_evidence_tier"],
            model_name=profile["model_name"],
            method=method,
            projected=False,
            success_rate=profile["arrival_success_rate"],
            recent20=profile["recent20_success_rate"],
            recent10=profile["recent10_success_rate"],
            now=now,
        )
        p1 = _annotate_arrival_source(p1, profile)
        base["prediction_1"] = p1
        base["status"] = "waiting_for_restock"

        # Build as many projected cycles as necessary to find the earliest
        # reachable travel target. This is important for rapid items where a long
        # flight can span P1, P2, P3, etc.
        chain = _project_future_chain(
            first_prediction=p1,
            profile=profile,
            median_lifetime=median_lifetime,
            median_wait=median_wait,
            lifetimes=lifetimes,
            waits=waits,
            travel_seconds=travel_seconds,
            now=now,
            start_number=1,
            first_is_projected=False,
        )
        base["predictions"] = chain
        base["prediction_1"] = chain[0] if chain else None
        base["prediction_2"] = chain[1] if len(chain) > 1 else None

        active_target = _select_active_forecast(chain)
        base["display_prediction"] = active_target
        base.update(_forecast_chain_summary(chain, active_target))

        if active_target:
            number = active_target.get("prediction_number") or 1
            if number == 1:
                base["status"] = "waiting_for_restock"
                base["note"] = (
                    "Prediction #1 is anchored to the observed depletion. "
                    "Future cycles will automatically re-anchor as real restocks "
                    "and depletions are observed."
                )
            else:
                base["status"] = "using_future_reachable_cycle"
                base["note"] = (
                    f"Prediction #{number} is the earliest reachable cycle. "
                    f"{number - 1} earlier cycle(s) are expected before it. "
                    "This projected target will automatically update and re-anchor "
                    "as those earlier cycles resolve."
                )
        else:
            base["status"] = "no_reachable_forecast_within_horizon"
            base["note"] = (
                f"No reachable departure target was found within the next "
                f"{len(chain)} forecast cycle(s) / {MAX_FORECAST_HORIZON_SECONDS // 3600}h horizon. "
                "The estimates are retained for reference and will roll forward "
                "as new stock events are observed."
            )
        return base


    # ------------------------------------------------------------------
    # STOCK ACTIVE: the previous restock already happened. Do not keep the
    # old prediction on screen. Project the next cycle from actual restock +
    # median lifetime + median zero-wait until a real depletion gives us a
    # new high-quality anchor.
    # ------------------------------------------------------------------
    base["status"] = "stock_active_projecting_next_cycle"
    active = state["active_cycle"]
    last_restock = (
        active.get("restock_time") if active
        else state["completed"][-1].get("restock_time") if state["completed"]
        else None
    )

    if last_restock and median_lifetime and median_wait:
        estimated_depletion = last_restock + median_lifetime
        next_restock = estimated_depletion + median_wait

        life_mad = (
            statistics.median(abs(v - median_lifetime) for v in lifetimes)
            if len(lifetimes) >= 3 else median_lifetime * 0.15
        )
        wait_mad = (
            statistics.median(abs(v - median_wait) for v in waits)
            if len(waits) >= 3 else median_wait * 0.15
        )
        half = life_mad + wait_mad
        projected_reliability = _downgrade_reliability(
            profile["travel_reliability"]
        )
        if half * 2 >= median_lifetime:
            projected_reliability = "unreliable"
            half = median_lifetime * 0.49

        p1 = _make_prediction(
            number=1,
            estimate=next_restock,
            window_start=next_restock - half,
            window_end=next_restock + half,
            arrival_offset=profile["arrival_offset_seconds"],
            travel_seconds=travel_seconds,
            reliability=projected_reliability,
            evidence_tier=profile["model_evidence_tier"],
            model_name="projected next cycle",
            method="actual restock + median lifetime + median depletion→restock wait",
            projected=True,
            success_rate=None,
            recent20=None,
            recent10=None,
            now=now,
        )
        p1["estimated_depletion_timestamp"] = _safe_int(estimated_depletion)
        p1 = _annotate_arrival_source(p1, profile)

        chain = _project_future_chain(
            first_prediction=p1,
            profile=profile,
            median_lifetime=median_lifetime,
            median_wait=median_wait,
            lifetimes=lifetimes,
            waits=waits,
            travel_seconds=travel_seconds,
            now=now,
            start_number=1,
            first_is_projected=True,
        )
        base["predictions"] = chain
        base["prediction_1"] = chain[0] if chain else None
        base["prediction_2"] = chain[1] if len(chain) > 1 else None

        active_target = _select_active_forecast(chain)
        base["display_prediction"] = active_target
        base.update(_forecast_chain_summary(chain, active_target))

        if active_target:
            number = active_target.get("prediction_number") or 1
            if number == 1:
                base["status"] = "stock_active_projecting_next_cycle"
                base["note"] = (
                    "Current stock is active. Prediction #1 is the projected next "
                    "cycle until this stock actually depletes; the forecast will "
                    "re-anchor immediately when that depletion is observed."
                )
            else:
                base["status"] = "stock_active_using_future_reachable_cycle"
                base["note"] = (
                    f"Current stock is active. Prediction #{number} is the earliest "
                    f"reachable future cycle; {number - 1} projected cycle(s) come first. "
                    "The target will tighten and re-anchor as real cycles resolve."
                )
        else:
            base["status"] = "stock_active_no_reachable_forecast_within_horizon"
            base["note"] = (
                f"Current stock is active, but no reachable departure target was "
                f"found within {len(chain)} projected cycle(s) / "
                f"{MAX_FORECAST_HORIZON_SECONDS // 3600}h."
            )

        if travel_seconds is not None:
            eta_now = now + travel_seconds
            base["current_stock_estimated_reachable"] = bool(
                eta_now < estimated_depletion
            )
            base["current_stock_eta_if_leave_now_timestamp"] = _safe_int(eta_now)
            base["estimated_current_depletion_timestamp"] = _safe_int(
                estimated_depletion
            )
    else:
        base["display_prediction"] = None
        base["note"] = (
            "Stock is currently active. Waiting for enough lifetime/wait history "
            "to project the next restock."
        )

    return base



def build_live_prediction_v2(
    country,
    item_name,
    now_timestamp=None,
    force_profile=False,
    audit_source="live",
    record_audit=True,
):
    """
    Public Prediction v2 entry point.

    Forecast auditing is intentionally best-effort: an audit/database failure
    must never prevent the graph or Discord from receiving a prediction.
    """
    result = _build_live_prediction_v2_impl(
        country,
        item_name,
        now_timestamp=now_timestamp,
        force_profile=force_profile,
    )

    if record_audit:
        try:
            from services.forecast_auditor import record_forecast_snapshot
            record_forecast_snapshot(
                country,
                item_name,
                result,
                source=audit_source,
            )
        except Exception as exc:
            # Keep live prediction independent from audit persistence.
            result["forecast_audit_warning"] = str(exc)

    return result
