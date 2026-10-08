import statistics


SAFETY_DELAY_FRACTIONS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25)
SAFETY_DELAY_SECONDS = (0.0, 60.0, 120.0, 180.0, 300.0)


def shifted_rows(rows, fraction=0.0, seconds=0.0):
    out = []
    for r in rows:
        row = dict(r)
        life = float(row.get("lifetime_estimate_seconds") or 0.0)
        delay = max(float(seconds), float(fraction) * life)

        if row.get("recommended_arrival_timestamp") is not None:
            row["recommended_arrival_timestamp"] = (
                float(row["recommended_arrival_timestamp"]) + delay
            )
        if row.get("recommended_departure_timestamp") is not None:
            row["recommended_departure_timestamp"] = (
                float(row["recommended_departure_timestamp"]) + delay
            )

        actual_r = float(row["actual_restock_timestamp"])
        actual_d = float(row["actual_depletion_timestamp"])
        arrival = float(row["recommended_arrival_timestamp"])
        row["arrival_hit"] = int(actual_r <= arrival < actual_d)
        row["early_arrival"] = int(arrival < actual_r)
        row["late_arrival"] = int(arrival >= actual_d)
        row["safety_delay_seconds"] = delay
        out.append(row)
    return out


def _summary(rows, split_timestamp, period, threshold):
    if period == "train":
        subset = [r for r in rows if int(r["anchor_timestamp"]) < split_timestamp]
    else:
        subset = [r for r in rows if int(r["anchor_timestamp"]) >= split_timestamp]

    actionable = [r for r in subset if r.get("actionable_from_anchor")]
    declared = [
        r for r in actionable
        if r.get("predicted_arrival_success") is not None
        and float(r["predicted_arrival_success"]) >= float(threshold)
        and int(r.get("calibration_pool_n") or 0)
        >= int(r.get("calibration_min_samples") or 8)
    ]
    n = len(declared)
    hits = sum(int(r["arrival_hit"]) for r in declared)
    return {
        "declared_n": n,
        "coverage": n / len(actionable) if actionable else 0.0,
        "arrival_hit_rate": hits / n if n else None,
        "early_rate": (
            sum(int(r["early_arrival"]) for r in declared) / n if n else None
        ),
        "late_rate": (
            sum(int(r["late_arrival"]) for r in declared) / n if n else None
        ),
    }


def _recent_fold(rows, split_timestamp, threshold, fraction, seconds):
    train_anchors = sorted({
        int(r["anchor_timestamp"])
        for r in rows if int(r["anchor_timestamp"]) < split_timestamp
    })
    if len(train_anchors) < 20:
        return None
    recent = set(train_anchors[-max(10, len(train_anchors)//5):])
    shifted = shifted_rows(
        [r for r in rows if int(r["anchor_timestamp"]) in recent],
        fraction=fraction,
        seconds=seconds,
    )

    actionable = [r for r in shifted if r.get("actionable_from_anchor")]
    declared = [
        r for r in actionable
        if r.get("predicted_arrival_success") is not None
        and float(r["predicted_arrival_success"]) >= float(threshold)
        and int(r.get("calibration_pool_n") or 0)
        >= int(r.get("calibration_min_samples") or 8)
    ]
    n = len(declared)
    hits = sum(int(r["arrival_hit"]) for r in declared)
    return {
        "declared_n": n,
        "coverage": n / len(actionable) if actionable else 0.0,
        "arrival_hit_rate": hits / n if n else None,
    }


def choose_safety_delay(candidate, split_timestamp, threshold, target):
    rows = candidate["evaluation"]["rows"]
    options = []

    for fraction in SAFETY_DELAY_FRACTIONS:
        for seconds in SAFETY_DELAY_SECONDS:
            shifted = shifted_rows(rows, fraction=fraction, seconds=seconds)
            train = _summary(
                shifted, split_timestamp, "train", threshold
            )
            recent = _recent_fold(
                rows, split_timestamp, threshold, fraction, seconds
            )

            precision = train.get("arrival_hit_rate")
            n = train.get("declared_n") or 0
            coverage = train.get("coverage") or 0.0
            recent_precision = (
                recent.get("arrival_hit_rate") if recent else None
            )
            recent_n = recent.get("declared_n") if recent else 0

            valid = (
                precision is not None
                and precision >= target
                and n >= 15
                and coverage >= 0.05
                and recent_precision is not None
                and recent_precision >= max(0.0, target - 0.05)
                and recent_n >= 5
            )
            delay_cost = max(seconds, fraction * 10000.0)
            score = (
                1 if valid else 0,
                recent_precision if recent_precision is not None else -1.0,
                precision if precision is not None else -1.0,
                coverage,
                n,
                -delay_cost,
            )
            options.append((score, fraction, seconds, train, recent))

    options.sort(key=lambda x: x[0], reverse=True)
    if not options:
        return None
    score, fraction, seconds, train, recent = options[0]
    return {
        "fraction": fraction,
        "seconds": seconds,
        "train": train,
        "recent_train": recent,
        "score": score,
    }


def evaluate_safety_delay(candidate, split_timestamp, threshold, fraction, seconds):
    rows = shifted_rows(
        candidate["evaluation"]["rows"],
        fraction=fraction,
        seconds=seconds,
    )
    return {
        "train": _summary(rows, split_timestamp, "train", threshold),
        "holdout": _summary(rows, split_timestamp, "holdout", threshold),
    }
