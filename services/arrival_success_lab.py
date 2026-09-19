import math
import statistics

from services.cycle_feature_lab import _percentile
from services.history_service import (
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)
from services.medium_model_lab import analyze_advanced_item
from services.prediction_v2_selector import select_prediction_v2_model


# PI + pilot / Airstrip one-way travel times supplied from Torn Travel Agency.
TRAVEL_SECONDS = {
    "mex": 17 * 60,
    "cay": 23 * 60,
    "can": 27 * 60,
    "haw": 89 * 60,
    "uni": 106 * 60,
    "arg": 111 * 60,
    "swi": 116 * 60,
    "jap": 149 * 60,
    "chi": 160 * 60,
    "uae": 180 * 60,
    "sou": 197 * 60,
}


def _model_records_key(selected_name):
    if selected_name == "depletion/all_median":
        return "baseline_all_median"
    return selected_name


def _incoming_lifetimes(country, item_name):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, _ = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    cycles, _active, _waits = _build_validated_cycles(rows)
    result = {}
    for cycle in cycles:
        if (
            cycle.get("complete")
            and not cycle.get("tiny_restock")
            and cycle.get("valid_lifetime")
            and cycle.get("restock_time") is not None
            and cycle.get("lifetime_seconds") is not None
            and cycle.get("lifetime_seconds") > 0
        ):
            result[int(cycle["restock_time"])] = float(cycle["lifetime_seconds"])
    return result


def _success(error_seconds, lifetime_seconds, arrival_offset_seconds):
    # error = actual restock - predicted restock.
    # arrival = predicted restock + offset.
    # Success iff actual_restoc <= arrival < actual_depletion.
    relative_to_actual = arrival_offset_seconds - error_seconds
    return 0 <= relative_to_actual < lifetime_seconds


def _best_offset(prior_rows, max_offset_seconds=None):
    """
    Choose an arrival offset using ONLY already-resolved historical predictions.

    We search the intervals in which each historical trip would have succeeded:
        error <= offset < error + lifetime

    Primary objective: maximize historical arrival success.
    Tie break: stay near the center of the best plateau rather than hugging a
    boundary.  Optional max_offset keeps the recommendation inside a useful
    stock-lifetime scale.
    """
    usable = [
        r for r in prior_rows
        if r.get("signed_error_seconds") is not None
        and r.get("actual_lifetime_seconds") is not None
        and r["actual_lifetime_seconds"] > 0
    ]
    if len(usable) < 5:
        return None

    boundaries = {0.0}
    for r in usable:
        lo = float(r["signed_error_seconds"])
        hi = lo + float(r["actual_lifetime_seconds"])
        boundaries.add(lo)
        boundaries.add(hi)

    ordered = sorted(boundaries)
    candidates = set()
    for value in ordered:
        candidates.add(value)
    for a, b in zip(ordered, ordered[1:]):
        candidates.add((a + b) / 2)

    if max_offset_seconds is not None:
        candidates = {x for x in candidates if x <= max_offset_seconds}
    # Negative offset means "arrive before predicted restock"; that can be valid
    # and sometimes desirable, but cap it to a reasonable one-lifetime lead.
    lead_floor = -float(max_offset_seconds or 6 * 3600)
    candidates = {x for x in candidates if x >= lead_floor}

    scored = []
    for offset in candidates:
        hits = sum(_success(r["signed_error_seconds"], r["actual_lifetime_seconds"], offset) for r in usable)
        rate = hits / len(usable)
        margins = []
        for r in usable:
            if _success(r["signed_error_seconds"], r["actual_lifetime_seconds"], offset):
                rel = offset - r["signed_error_seconds"]
                margins.append(min(rel, r["actual_lifetime_seconds"] - rel))
        median_margin = statistics.median(margins) if margins else -1
        scored.append((rate, median_margin, offset))

    if not scored:
        return None
    best_rate = max(x[0] for x in scored)
    best_margin = max(x[1] for x in scored if x[0] == best_rate)
    best_offsets = [x[2] for x in scored if x[0] == best_rate and x[1] == best_margin]
    return statistics.median(best_offsets), best_rate


def _coverage_interval(prior_rows, target=0.90, max_width_seconds=None):
    """
    Smallest restock-error interval that contains at least target fraction of
    prior signed errors.  This is diagnostic for a predicted restock window.

    Uses resolved errors only; no current-cycle hindsight.
    """
    errors = sorted(
        float(r["signed_error_seconds"])
        for r in prior_rows
        if r.get("signed_error_seconds") is not None
    )
    n = len(errors)
    if n < 8:
        return None
    need = max(1, math.ceil(target * n))
    best = None
    for i in range(0, n - need + 1):
        lo, hi = errors[i], errors[i + need - 1]
        width = hi - lo
        if max_width_seconds is not None and width > max_width_seconds:
            continue
        if best is None or width < best[2]:
            best = (lo, hi, width)
    return best


def backtest_arrival_policy(country, item_name, min_train=15, target_coverage=0.90):
    selector = select_prediction_v2_model(country, item_name, min_train=min_train)
    selected_name = selector["selected_model"]["name"]
    records_key = _model_records_key(selected_name)

    analysis = analyze_advanced_item(country, item_name, min_train=min_train)
    records = list(analysis["records_by_model"].get(records_key, []))
    lifetimes = _incoming_lifetimes(country, item_name)

    median_lifetime = selector.get("median_stock_lifetime_seconds")
    scored_history = []
    results = []

    for record in records:
        actual_restock = record.get("actual_restock_timestamp")
        lifetime = lifetimes.get(int(actual_restock)) if actual_restock is not None else None
        if lifetime is None:
            continue

        prior = list(scored_history)
        max_offset = median_lifetime if median_lifetime else None
        choice = _best_offset(prior, max_offset_seconds=max_offset)
        interval = _coverage_interval(
            prior,
            target=target_coverage,
            max_width_seconds=median_lifetime if median_lifetime else None,
        )

        # Always score the trivial "arrive at predicted timestamp" policy.
        at_prediction_hit = _success(
            record["signed_error_seconds"],
            lifetime,
            0.0,
        )

        optimized_offset = choice[0] if choice else None
        optimized_hit = (
            _success(record["signed_error_seconds"], lifetime, optimized_offset)
            if optimized_offset is not None else None
        )

        row = dict(record)
        row["actual_lifetime_seconds"] = lifetime
        row["at_prediction_hit"] = at_prediction_hit
        row["recommended_arrival_offset_seconds"] = optimized_offset
        row["optimized_hit"] = optimized_hit
        row["prior_empirical_hit_rate"] = choice[1] if choice else None
        if interval:
            row["restock_window_lo_error_seconds"] = interval[0]
            row["restock_window_hi_error_seconds"] = interval[1]
            row["restock_window_width_seconds"] = interval[2]
        else:
            row["restock_window_lo_error_seconds"] = None
            row["restock_window_hi_error_seconds"] = None
            row["restock_window_width_seconds"] = None
        results.append(row)
        scored_history.append(row)

    warm = [r for r in results if r["optimized_hit"] is not None]
    direct = [r for r in results if r["at_prediction_hit"] is not None]

    optimized_rate = (
        sum(bool(r["optimized_hit"]) for r in warm) / len(warm)
        if warm else None
    )
    direct_rate = (
        sum(bool(r["at_prediction_hit"]) for r in direct) / len(direct)
        if direct else None
    )

    recent20 = warm[-20:]
    recent10 = warm[-10:]
    latest_offset = _best_offset(
        scored_history,
        max_offset_seconds=median_lifetime if median_lifetime else None,
    )
    latest_window = _coverage_interval(
        scored_history,
        target=target_coverage,
        max_width_seconds=median_lifetime if median_lifetime else None,
    )

    return {
        "country": country.upper(),
        "item_name": item_name,
        "behavior_class": selector["behavior_class"],
        "selection_tier": selector["selection_tier"],
        "selected_model": selected_name,
        "history_samples": selector["history_samples"],
        "median_stock_lifetime_seconds": median_lifetime,
        "travel_seconds": TRAVEL_SECONDS.get(country.lower()),
        "scored_predictions": len(results),
        "optimized_predictions": len(warm),
        "arrival_at_prediction_success_rate": direct_rate,
        "optimized_arrival_success_rate": optimized_rate,
        "recent20_arrival_success_rate": (
            sum(bool(r["optimized_hit"]) for r in recent20) / len(recent20)
            if recent20 else None
        ),
        "recent10_arrival_success_rate": (
            sum(bool(r["optimized_hit"]) for r in recent10) / len(recent10)
            if recent10 else None
        ),
        "recommended_arrival_offset_seconds": latest_offset[0] if latest_offset else None,
        "historical_fit_success_rate": latest_offset[1] if latest_offset else None,
        "target_coverage": target_coverage,
        "restock_window_lo_error_seconds": latest_window[0] if latest_window else None,
        "restock_window_hi_error_seconds": latest_window[1] if latest_window else None,
        "restock_window_width_seconds": latest_window[2] if latest_window else None,
        "window_is_useful": (
            None if latest_window is None or median_lifetime is None
            else latest_window[2] < median_lifetime
        ),
        "rows": results,
    }
