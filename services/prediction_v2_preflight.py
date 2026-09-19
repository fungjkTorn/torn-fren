from services.arrival_model_tournament import tournament_arrival_models
from services.recent_regime_lab import analyze_recent_regime


RELIABILITY_ORDER = {
    "insufficient": 0,
    "unreliable": 1,
    "marginal": 2,
    "good": 3,
    "excellent": 4,
}


def _best_rapid_baseline(result_rows):
    candidates = [
        r for r in result_rows
        if r.get("model") == "baseline_all_median" and r.get("n", 0) >= 8
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda r: (
            RELIABILITY_ORDER.get(r.get("reliability"), 0),
            r.get("recent10_success_rate") or -1,
            r.get("recent20_success_rate") or -1,
            r.get("arrival_success_rate") or -1,
        ),
    )


def build_prediction_v2_preflight(country, item_name):
    tourn = tournament_arrival_models(country, item_name)
    rows = tourn.get("results") or []

    if tourn.get("behavior_class") == "rapid":
        chosen = _best_rapid_baseline(rows)
        selection_reason = (
            "Rapid item: keep the frozen depletion/all_median point model and only "
            "optimize the arrival policy."
        )
    else:
        chosen = tourn.get("best")
        selection_reason = (
            "Short/medium/long item: choose the best sufficiently-tested travel-first "
            "model/policy after reliability gating."
        )

    recent_regime = None
    if country.lower() == "jap" and item_name.lower() == "xanax":
        recent_regime = analyze_recent_regime(
            country,
            item_name,
            model_name="baseline_all_median",
            policy="lifetime",
        )

    reliability = chosen.get("reliability") if chosen else "insufficient"
    ready = reliability in {"excellent", "good"}
    caution = reliability == "marginal"

    # Japan can show a best estimate, but do not promote a recent-10 streak to live
    # high-confidence guidance unless the regime diagnostic also supports it.
    if recent_regime and recent_regime.get("regime_status") not in {
        "recent_regime_candidate",
        "recent_regime_supported",
    }:
        ready = False

    return {
        "country": tourn.get("country"),
        "item_name": tourn.get("item_name"),
        "behavior_class": tourn.get("behavior_class"),
        "model_evidence_tier": tourn.get("model_evidence_tier"),
        "median_stock_lifetime_seconds": tourn.get("median_stock_lifetime_seconds"),
        "chosen": chosen,
        "travel_reliability": reliability,
        "ready_for_live_guidance": ready,
        "caution_only": caution,
        "selection_reason": selection_reason,
        "recent_regime": recent_regime,
    }
