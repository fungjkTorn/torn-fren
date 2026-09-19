def classify_travel_reliability(
    *,
    lifetime_success_rate,
    recent20_success_rate,
    recent10_success_rate,
    optimized_predictions,
    window_is_useful,
):
    """
    Reliability is deliberately separate from cycle-speed class and model-evidence tier.

    Labels describe the historical usefulness of the *travel recommendation*:
      excellent / good / marginal / unreliable / insufficient

    Recent degradation can downgrade an otherwise strong lifetime result.
    """
    if optimized_predictions is None or optimized_predictions < 8 or lifetime_success_rate is None:
        return {
            "label": "insufficient",
            "reason": "Not enough resolved walk-forward arrival recommendations yet.",
            "drift_flag": False,
        }

    effective = lifetime_success_rate

    # Recent results matter, but do not let a tiny recent sample dominate.
    if recent20_success_rate is not None and optimized_predictions >= 20:
        effective = min(effective, recent20_success_rate + 0.03)
    if recent10_success_rate is not None and optimized_predictions >= 10:
        effective = min(effective, recent10_success_rate + 0.05)

    # A useless/wider-than-lifetime window caps trust even if point estimates look good.
    if window_is_useful is False:
        effective = min(effective, 0.74)

    if effective >= 0.95:
        label = "excellent"
    elif effective >= 0.90:
        label = "good"
    elif effective >= 0.75:
        label = "marginal"
    else:
        label = "unreliable"

    drift_flag = False
    reason_bits = []

    if (
        recent10_success_rate is not None
        and lifetime_success_rate is not None
        and optimized_predictions >= 10
        and recent10_success_rate <= lifetime_success_rate - 0.15
    ):
        drift_flag = True
        reason_bits.append("recent-10 success is at least 15 points below lifetime success")

    if (
        recent20_success_rate is not None
        and lifetime_success_rate is not None
        and optimized_predictions >= 20
        and recent20_success_rate <= lifetime_success_rate - 0.12
    ):
        drift_flag = True
        reason_bits.append("recent-20 success is at least 12 points below lifetime success")

    if window_is_useful is False:
        reason_bits.append("90% restock window cannot fit inside normal stock lifetime")

    if not reason_bits:
        reason_bits.append("rating based on walk-forward arrival success and recent performance")

    return {
        "label": label,
        "reason": "; ".join(reason_bits),
        "drift_flag": drift_flag,
        "effective_success_rate": effective,
    }
