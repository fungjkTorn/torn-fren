from dataclasses import asdict
import statistics

from services.medium_model_lab import analyze_advanced_item
from services.cycle_feature_lab import build_cycle_feature_rows


PROVEN_MIN_BACKTESTS = 12
PROVISIONAL_MIN_BACKTESTS = 5

# Rapid items are deliberately "frozen" to a simple robust depletion-anchored
# model unless live auditing later proves they need more complexity.
RAPID_MODEL_NAME = "baseline_all_median"


def _fmt_seconds(value):
    if value is None:
        return None
    return float(value)


def _median_lifetime(feature_rows):
    vals = [
        r.get("prev_lifetime_seconds")
        for r in feature_rows
        if r.get("prev_lifetime_seconds") is not None and r.get("prev_lifetime_seconds") > 0
    ]
    return statistics.median(vals) if vals else None


def _tier_for_predictions(predictions):
    if predictions >= PROVEN_MIN_BACKTESTS:
        return "proven"
    if predictions >= PROVISIONAL_MIN_BACKTESTS:
        return "provisional"
    return "sparse"


def _candidate_payload(model, median_lifetime_seconds):
    med = model.median_absolute_error_seconds
    p90 = model.p90_absolute_error_seconds
    mean = model.mean_absolute_error_seconds

    p90_lifetime_ratio = None
    if p90 is not None and median_lifetime_seconds:
        p90_lifetime_ratio = p90 / median_lifetime_seconds

    # Reliability-aware score.  The point is NOT to blindly choose the lowest
    # median error if the model has a terrible tail.
    #
    # p90 matters heavily because a travel departure window must survive tail
    # misses.  This score is only used to compare models with the same history.
    score = None
    if med is not None and p90 is not None:
        score = med + 0.55 * p90
        if median_lifetime_seconds and p90 > median_lifetime_seconds:
            # Strong penalty: if p90 timing error exceeds normal stock lifetime,
            # a 90%-style travel window would be hard to make useful.
            score += (p90 - median_lifetime_seconds) * 1.5

    return {
        "name": model.name,
        "predictions": model.predictions,
        "tier": _tier_for_predictions(model.predictions),
        "median_error_seconds": _fmt_seconds(med),
        "mean_error_seconds": _fmt_seconds(mean),
        "p90_error_seconds": _fmt_seconds(p90),
        "signed_bias_seconds": _fmt_seconds(model.signed_bias_seconds),
        "p90_to_lifetime_ratio": p90_lifetime_ratio,
        "reliability_score": score,
        "p90_within_stock_lifetime": (
            None if p90 is None or median_lifetime_seconds is None
            else p90 < median_lifetime_seconds
        ),
    }


def select_prediction_v2_model(country, item_name, min_train=15):
    """
    Select the model family to use for Prediction v2.

    This is a model-selection layer only.  It does not yet change the live graph
    estimate.  That separation is intentional so we can validate selector choices
    before wiring them into production prediction/Discord.
    """
    analysis = analyze_advanced_item(country, item_name, min_train=min_train)
    feature_rows, _ = build_cycle_feature_rows(country, item_name)
    median_lifetime_seconds = _median_lifetime(feature_rows)

    behavior_class = analysis["behavior_class"]
    samples = analysis["samples"]
    candidates = [
        _candidate_payload(m, median_lifetime_seconds)
        for m in analysis["models"]
    ]

    # RAPID: we already learned that complex feature models do not materially
    # improve the simple robust baseline.  Freeze it unless future auditing says
    # otherwise.
    if behavior_class == "rapid":
        baseline = next((c for c in candidates if c["name"] == RAPID_MODEL_NAME), None)
        if baseline is None:
            selected = {
                "name": "depletion/all_median",
                "predictions": 0,
                "tier": "sparse",
                "median_error_seconds": None,
                "mean_error_seconds": None,
                "p90_error_seconds": None,
                "signed_bias_seconds": None,
                "p90_to_lifetime_ratio": None,
                "reliability_score": None,
                "p90_within_stock_lifetime": None,
            }
        else:
            selected = baseline.copy()
            selected["name"] = "depletion/all_median"

        confidence = (
            "proven" if samples >= 30
            else "provisional" if samples >= 10
            else "sparse"
        )
        return {
            "country": country.upper(),
            "item_name": item_name,
            "behavior_class": behavior_class,
            "history_samples": samples,
            "selection_tier": confidence,
            "selected_model": selected,
            "median_stock_lifetime_seconds": median_lifetime_seconds,
            "reason": (
                "Rapid-cycle item: simple depletion-anchored robust timing is frozen "
                "because feature/cluster models have not materially improved point error."
            ),
            "candidates": candidates,
        }

    # SHORT / MEDIUM:
    # Prefer models with enough walk-forward evidence.  If none are proven, allow
    # provisional models.  If even those are unavailable, explicitly fall back
    # to a robust depletion-anchored baseline instead of omitting the item.
    proven = [c for c in candidates if c["tier"] == "proven" and c["reliability_score"] is not None]
    provisional = [c for c in candidates if c["tier"] == "provisional" and c["reliability_score"] is not None]

    pool = proven or provisional
    selection_tier = "proven" if proven else "provisional" if provisional else "sparse"

    if pool:
        # First preference: tail error still fits inside normal stock lifetime.
        useful = [c for c in pool if c["p90_within_stock_lifetime"] is True]
        ranked = useful or pool
        selected = min(
            ranked,
            key=lambda c: (
                float("inf") if c["reliability_score"] is None else c["reliability_score"],
                float("inf") if c["median_error_seconds"] is None else c["median_error_seconds"],
            ),
        ).copy()

        if useful:
            reason = (
                "Selected by walk-forward median + p90 reliability, while preferring "
                "models whose p90 timing error remains below normal stock lifetime."
            )
        else:
            reason = (
                "No sufficiently tested candidate keeps p90 timing error below normal "
                "stock lifetime; using the least-bad reliability-aware model for now."
            )
    else:
        selected = {
            "name": "depletion/all_median",
            "predictions": 0,
            "tier": "sparse",
            "median_error_seconds": None,
            "mean_error_seconds": None,
            "p90_error_seconds": None,
            "signed_bias_seconds": None,
            "p90_to_lifetime_ratio": None,
            "reliability_score": None,
            "p90_within_stock_lifetime": None,
        }
        reason = (
            "Too little walk-forward history to promote an advanced model.  Continue "
            "showing the best available depletion-anchored robust baseline."
        )

    return {
        "country": country.upper(),
        "item_name": item_name,
        "behavior_class": behavior_class,
        "history_samples": samples,
        "selection_tier": selection_tier,
        "selected_model": selected,
        "median_stock_lifetime_seconds": median_lifetime_seconds,
        "reason": reason,
        "candidates": candidates,
    }
