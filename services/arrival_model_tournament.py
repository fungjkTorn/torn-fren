import math
import statistics

from services.arrival_success_lab import (
    _coverage_interval,
    _incoming_lifetimes,
    _success,
)
from services.medium_model_lab import analyze_advanced_item
from services.prediction_v2_selector import select_prediction_v2_model
from services.travel_reliability import classify_travel_reliability


def _adaptive_offset(prior_rows, recent_limit=None, max_offset_seconds=None):
    """
    Choose the offset that maximizes success over prior rows.

    If recent_limit is supplied, only the most recent resolved predictions are used.
    This lets us test whether a changing item such as Japan Xanax benefits from a
    rolling regime-aware policy instead of one lifetime-wide offset.
    """
    usable = [
        r for r in prior_rows
        if r.get("signed_error_seconds") is not None
        and r.get("actual_lifetime_seconds") is not None
        and r["actual_lifetime_seconds"] > 0
    ]
    if recent_limit:
        usable = usable[-recent_limit:]
    if len(usable) < 5:
        return None

    boundaries = {0.0}
    for r in usable:
        lo = float(r["signed_error_seconds"])
        hi = lo + float(r["actual_lifetime_seconds"])
        boundaries.add(lo)
        boundaries.add(hi)

    ordered = sorted(boundaries)
    candidates = set(ordered)
    for a, b in zip(ordered, ordered[1:]):
        candidates.add((a + b) / 2)

    if max_offset_seconds is not None:
        candidates = {
            x for x in candidates
            if -max_offset_seconds <= x <= max_offset_seconds
        }

    scored = []
    for offset in candidates:
        hits = sum(
            _success(r["signed_error_seconds"], r["actual_lifetime_seconds"], offset)
            for r in usable
        )
        rate = hits / len(usable)

        margins = []
        for r in usable:
            if _success(r["signed_error_seconds"], r["actual_lifetime_seconds"], offset):
                rel = offset - r["signed_error_seconds"]
                margins.append(min(rel, r["actual_lifetime_seconds"] - rel))
        median_margin = statistics.median(margins) if margins else -1

        # Prefer a safer center-of-stock offset when hit rate ties.
        scored.append((rate, median_margin, -abs(offset), offset))

    if not scored:
        return None
    return max(scored)[-1]


def _model_arrival_backtest(records, lifetimes, median_lifetime, recent_limit=None):
    history = []
    scored = []

    for rec in records:
        actual_restock = rec.get("actual_restock_timestamp")
        if actual_restock is None:
            continue
        lifetime = lifetimes.get(int(actual_restock))
        if lifetime is None:
            continue

        offset = _adaptive_offset(
            history,
            recent_limit=recent_limit,
            max_offset_seconds=median_lifetime,
        )

        row = dict(rec)
        row["actual_lifetime_seconds"] = lifetime
        row["recommended_arrival_offset_seconds"] = offset
        row["arrival_hit"] = (
            _success(rec["signed_error_seconds"], lifetime, offset)
            if offset is not None else None
        )

        scored.append(row)
        history.append(row)

    resolved = [r for r in scored if r["arrival_hit"] is not None]
    if not resolved:
        return None

    lifetime_rate = sum(bool(r["arrival_hit"]) for r in resolved) / len(resolved)
    recent20 = resolved[-20:]
    recent10 = resolved[-10:]

    current_offset = _adaptive_offset(
        history,
        recent_limit=recent_limit,
        max_offset_seconds=median_lifetime,
    )

    window = _coverage_interval(
        history,
        target=0.90,
        max_width_seconds=median_lifetime,
    )

    return {
        "n": len(resolved),
        "arrival_success_rate": lifetime_rate,
        "recent20_success_rate": (
            sum(bool(r["arrival_hit"]) for r in recent20) / len(recent20)
            if recent20 else None
        ),
        "recent10_success_rate": (
            sum(bool(r["arrival_hit"]) for r in recent10) / len(recent10)
            if recent10 else None
        ),
        "current_arrival_offset_seconds": current_offset,
        "window_width_seconds": window[2] if window else None,
        "window_is_useful": window is not None,
    }


def tournament_arrival_models(country, item_name, min_train=15):
    """
    Score every Prediction-v2 candidate by the thing we actually care about:
    would a walk-forward recommended arrival have landed while stock existed?

    Tests both lifetime-history and rolling recent policies.  This is especially
    useful for Japan Xanax, where a single fixed offset has been unstable.
    """
    selector = select_prediction_v2_model(country, item_name, min_train=min_train)
    analysis = analyze_advanced_item(country, item_name, min_train=min_train)
    lifetimes = _incoming_lifetimes(country, item_name)
    median_lifetime = selector.get("median_stock_lifetime_seconds")

    rows = []
    for model_name, records in analysis["records_by_model"].items():
        for policy_name, recent_limit in (
            ("lifetime", None),
            ("recent20", 20),
            ("recent10", 10),
        ):
            result = _model_arrival_backtest(
                list(records),
                lifetimes,
                median_lifetime,
                recent_limit=recent_limit,
            )
            if not result:
                continue

            reliability = classify_travel_reliability(
                lifetime_success_rate=result["arrival_success_rate"],
                recent20_success_rate=result["recent20_success_rate"],
                recent10_success_rate=result["recent10_success_rate"],
                optimized_predictions=result["n"],
                window_is_useful=result["window_is_useful"],
            )

            rows.append({
                "model": model_name,
                "policy": policy_name,
                **result,
                "reliability": reliability["label"],
                "drift_flag": reliability.get("drift_flag", False),
            })

    # Travel-first ranking. Do NOT let a 2-3 sample 100% result beat a model
    # with real evidence. Reliability and sample count gate the ranking first.
    reliability_rank = {
        "excellent": 4,
        "good": 3,
        "marginal": 2,
        "unreliable": 1,
        "insufficient": 0,
    }

    def key(r):
        return (
            reliability_rank.get(r.get("reliability"), 0),
            1 if r.get("n", 0) >= 8 else 0,
            -1 if r["recent10_success_rate"] is None else r["recent10_success_rate"],
            -1 if r["recent20_success_rate"] is None else r["recent20_success_rate"],
            r["arrival_success_rate"],
            r["n"],
        )

    rows.sort(key=key, reverse=True)

    return {
        "country": country.upper(),
        "item_name": item_name,
        "behavior_class": selector["behavior_class"],
        "model_evidence_tier": selector["selection_tier"],
        "current_point_model": selector["selected_model"]["name"],
        "median_stock_lifetime_seconds": median_lifetime,
        "results": rows,
        "best": rows[0] if rows else None,
    }
