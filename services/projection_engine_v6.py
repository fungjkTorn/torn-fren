import math
import statistics
from dataclasses import dataclass

from services.projection_engine_v4 import _median_error, _percentile

TARGET_DECLARED_SUCCESS = {
    "plushie": 0.90,
    "xanax": 0.75,
    "flower": 0.80,
}

DECLARATION_THRESHOLDS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.925, 0.95)
RESIDUAL_WINDOWS = (5, 10, 20, 40, 80)
WEIGHTING_MODES = ("uniform", "linear")
TOD_CONTEXT_HOURS = (None, 6.0)
BIAS_POLICIES_V6 = ("none", "depth_recent20")


@dataclass(frozen=True)
class ArrivalStateConfig:
    residual_window: int | None
    weighting: str
    tod_hours: float | None
    bias_policy: str
    declare_threshold: float
    min_samples: int = 8

    @property
    def label(self):
        window = "all" if self.residual_window is None else str(self.residual_window)
        tod = "all" if self.tod_hours is None else f"{int(self.tod_hours)}h"
        return (
            f"arrival_state[w={window},weight={self.weighting},tod={tod},"
            f"bias={self.bias_policy},declare={self.declare_threshold:.3f}]"
        )


def item_class(item_name):
    lower = item_name.lower()
    if "plushie" in lower:
        return "plushie"
    if lower == "xanax":
        return "xanax"
    return "flower"


def target_success(item_name):
    return TARGET_DECLARED_SUCCESS[item_class(item_name)]


def _hour_distance(a_ts, b_ts):
    a = (float(a_ts) % 86400.0) / 3600.0
    b = (float(b_ts) % 86400.0) / 3600.0
    d = abs(a - b)
    return min(d, 24.0 - d)


def _weighted_wilson_lower(p, effective_n, z=1.96):
    if effective_n <= 0:
        return None
    n = float(effective_n)
    denom = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return max(0.0, (center - margin) / denom)


def _residual_pool(prior_rows, config, target_ts):
    rows = [
        r for r in prior_rows
        if r.get("signed_error_seconds") is not None
        and r.get("actual_lifetime_seconds") is not None
        and float(r["actual_lifetime_seconds"]) > 0
    ]
    if config.tod_hours is not None:
        nearby = [
            r for r in rows
            if _hour_distance(
                r.get("actual_restock_timestamp", r["anchor_timestamp"]),
                target_ts,
            ) <= float(config.tod_hours)
        ]
        if len(nearby) >= max(config.min_samples, 10):
            rows = nearby
    if config.residual_window is not None:
        rows = rows[-int(config.residual_window):]
    return rows


def _weights(n, mode):
    if mode == "uniform":
        return [1.0] * n
    if mode == "linear":
        return [float(i + 1) for i in range(n)]
    raise ValueError(mode)


def _interval_score(pool, config, offset_seconds):
    weights = _weights(len(pool), config.weighting)
    total = sum(weights)
    hit_weight = 0.0
    margins = []
    for row, weight in zip(pool, weights):
        lo = float(row["signed_error_seconds"])
        hi = lo + float(row["actual_lifetime_seconds"])
        if lo <= offset_seconds < hi:
            hit_weight += weight
            margins.append(min(offset_seconds - lo, hi - offset_seconds))
    p = hit_weight / total if total else 0.0
    sum_sq = sum(w * w for w in weights)
    effective_n = (total * total / sum_sq) if sum_sq else 0.0
    return {
        "probability": p,
        "confidence_lower_95": _weighted_wilson_lower(p, effective_n),
        "effective_n": effective_n,
        "median_margin_seconds": statistics.median(margins) if margins else -1.0,
    }


def _best_overlap_offset(pool, config, life_est):
    weights = _weights(len(pool), config.weighting)
    total = sum(weights)
    if not total:
        return None

    cap = max(1800.0, 3.0 * float(life_est))
    events = {}
    for row, weight in zip(pool, weights):
        lo = max(-cap, float(row["signed_error_seconds"]))
        hi = min(
            cap,
            float(row["signed_error_seconds"]) + float(row["actual_lifetime_seconds"]),
        )
        if hi <= lo:
            continue
        events.setdefault(lo, [0.0, 0.0])[0] += weight
        events.setdefault(hi, [0.0, 0.0])[1] += weight

    coords = sorted(events)
    if len(coords) < 2:
        return None

    current = 0.0
    best = None
    best_offset = None
    target = 0.50 * float(life_est)

    for i, x in enumerate(coords[:-1]):
        starts, ends = events[x]
        current -= ends
        current += starts
        next_x = coords[i + 1]
        if next_x <= x or current <= 0:
            continue
        offset = (x + next_x) / 2.0
        probability = current / total
        key = (probability, next_x - x, -abs(offset - target))
        if best is None or key > best:
            best = key
            best_offset = offset

    if best_offset is None:
        return None
    return best_offset, _interval_score(pool, config, best_offset)


def choose_arrival_offset(prior_rows, config, predicted_restock, life_est):
    pool = _residual_pool(prior_rows, config, predicted_restock)
    if len(pool) < config.min_samples:
        return {
            "offset_seconds": 0.50 * life_est,
            "probability": None,
            "confidence_lower_95": None,
            "effective_n": float(len(pool)),
            "median_margin_seconds": None,
            "pool_n": len(pool),
        }

    chosen = _best_overlap_offset(pool, config, life_est)
    if chosen is None:
        return {
            "offset_seconds": 0.50 * life_est,
            "probability": None,
            "confidence_lower_95": None,
            "effective_n": float(len(pool)),
            "median_margin_seconds": None,
            "pool_n": len(pool),
        }

    offset, stats = chosen
    return {"offset_seconds": offset, "pool_n": len(pool), **stats}


def apply_arrival_state_policy(ctx, point_rows, config):
    prior_by_depth = {d: [] for d in range(1, ctx.max_depth + 1)}
    output = []

    for raw in point_rows:
        depth = int(raw["depth"])
        prior = prior_by_depth[depth]

        bias = _median_error(prior, config.bias_policy)
        predicted_restock = float(raw["raw_predicted_restock_timestamp"]) + bias
        life_est = float(raw["lifetime_estimate_seconds"])
        choice = choose_arrival_offset(prior, config, predicted_restock, life_est)
        arrival = predicted_restock + float(choice["offset_seconds"])
        departure = (
            arrival - float(ctx.travel_seconds)
            if ctx.travel_seconds is not None else None
        )
        actionable = (
            departure is not None
            and departure >= float(raw["anchor_timestamp"])
        )

        probability = choice.get("probability")
        declared = bool(
            actionable
            and choice.get("pool_n", 0) >= config.min_samples
            and probability is not None
            and probability >= config.declare_threshold
        )

        actual_r = float(raw["actual_restock_timestamp"])
        actual_d = float(raw["actual_depletion_timestamp"])
        signed_error = actual_r - predicted_restock
        hit = int(actual_r <= arrival < actual_d)
        early = int(arrival < actual_r)
        late = int(arrival >= actual_d)

        row = dict(raw)
        row.update({
            "predicted_restock_timestamp": predicted_restock,
            "bias_correction_seconds": bias,
            "signed_error_seconds": signed_error,
            "absolute_error_seconds": abs(signed_error),
            "arrival_offset_seconds": float(choice["offset_seconds"]),
            "recommended_arrival_timestamp": arrival,
            "recommended_departure_timestamp": departure,
            "actionable_from_anchor": int(actionable),
            "declared_arrival": int(declared),
            "predicted_arrival_success": probability,
            "predicted_arrival_lcb95": choice.get("confidence_lower_95"),
            "calibration_pool_n": choice.get("pool_n", 0),
            "calibration_min_samples": config.min_samples,
            "calibration_effective_n": choice.get("effective_n"),
            "arrival_hit": hit,
            "early_arrival": early,
            "late_arrival": late,
        })
        output.append(row)
        prior.append(row)

    return output


def _wilson_lower(hits, n, z=1.96):
    if not n:
        return None
    p = hits / n
    denom = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4.0 * n)) / n)
    return (center - margin) / denom


def selective_summary(rows, threshold=None):
    if not rows:
        return None

    actionable = [r for r in rows if r.get("actionable_from_anchor")]
    declared = [
        r for r in actionable
        if (
            r.get("declared_arrival")
            if threshold is None
            else (
                r.get("predicted_arrival_success") is not None
                and float(r["predicted_arrival_success"]) >= float(threshold)
                and int(r.get("calibration_pool_n") or 0)
                >= int(r.get("calibration_min_samples") or 8)
            )
        )
    ]

    hits = sum(r["arrival_hit"] for r in declared)
    n = len(declared)
    errors = [float(r["absolute_error_seconds"]) for r in declared]
    predicted = [
        float(r["predicted_arrival_success"])
        for r in actionable
        if r.get("predicted_arrival_success") is not None
    ]
    outcomes = [
        float(r["arrival_hit"])
        for r in actionable
        if r.get("predicted_arrival_success") is not None
    ]

    return {
        "rows_n": len(rows),
        "actionable_n": len(actionable),
        "declared_n": n,
        "coverage": n / len(actionable) if actionable else 0.0,
        "declared_hit_rate": hits / n if n else None,
        "declared_wilson_lower_95": _wilson_lower(hits, n) if n else None,
        "declared_early_rate": (
            sum(r["early_arrival"] for r in declared) / n if n else None
        ),
        "declared_late_rate": (
            sum(r["late_arrival"] for r in declared) / n if n else None
        ),
        "median_absolute_error_seconds": (
            statistics.median(errors) if errors else None
        ),
        "p90_absolute_error_seconds": (
            _percentile(errors, 0.90) if errors else None
        ),
        "brier_score_all_actionable": (
            statistics.mean((p - y) ** 2 for p, y in zip(predicted, outcomes))
            if predicted else None
        ),
        "mean_predicted_success": (
            statistics.mean(predicted) if predicted else None
        ),
    }


def summarize_period(ctx, rows, period, depth, threshold=None):
    split = ctx.split_timestamp
    if split is None:
        return None
    if period == "train":
        subset = [r for r in rows if int(r["anchor_timestamp"]) < split]
    elif period == "holdout":
        subset = [r for r in rows if int(r["anchor_timestamp"]) >= split]
    else:
        raise ValueError(period)
    subset = [r for r in subset if int(r["depth"]) == int(depth)]
    return selective_summary(subset, threshold=threshold)


def rolling_selective_folds(ctx, rows, depth, folds=4, threshold=None):
    training = [
        r for r in rows
        if int(r["anchor_timestamp"]) < ctx.split_timestamp
        and int(r["depth"]) == int(depth)
    ]
    anchors = sorted({int(r["anchor_timestamp"]) for r in training})
    if len(anchors) < 40:
        return []
    fold_size = max(10, len(anchors) // (folds + 1))
    result = []
    for fold in range(1, folds + 1):
        start = fold * fold_size
        end = min(len(anchors), start + fold_size)
        if start >= end:
            continue
        allowed = set(anchors[start:end])
        s = selective_summary(
            [r for r in training if int(r["anchor_timestamp"]) in allowed],
            threshold=threshold,
        )
        if s:
            result.append(s)
    return result


def evaluate_arrival_state(ctx, point_rows, config, thresholds=None):
    rows = apply_arrival_state_policy(ctx, point_rows, config)
    thresholds = tuple(thresholds or (config.declare_threshold,))
    scored = {}
    for threshold in thresholds:
        scored[str(threshold)] = {
            "train_by_depth": {
                d: summarize_period(ctx, rows, "train", d, threshold=threshold)
                for d in range(1, ctx.max_depth + 1)
            },
            "holdout_by_depth": {
                d: summarize_period(ctx, rows, "holdout", d, threshold=threshold)
                for d in range(1, ctx.max_depth + 1)
            },
            "rolling_folds_by_depth": {
                d: rolling_selective_folds(
                    ctx, rows, d, threshold=threshold
                )
                for d in range(1, ctx.max_depth + 1)
            },
        }
    return {"config": config, "rows": rows, "scores_by_threshold": scored}


def structural_configs():
    for window in RESIDUAL_WINDOWS:
        for weighting in WEIGHTING_MODES:
            for tod in TOD_CONTEXT_HOURS:
                for bias in BIAS_POLICIES_V6:
                    yield ArrivalStateConfig(
                        residual_window=window,
                        weighting=weighting,
                        tod_hours=tod,
                        bias_policy=bias,
                        declare_threshold=0.0,
                        min_samples=5 if window == 5 else 8,
                    )


def selective_rank_key(summary, target, folds=None):
    if not summary or not summary.get("declared_n"):
        return (-1, -1, -1, -1, -1)

    precision = summary.get("declared_hit_rate") or 0.0
    lcb = summary.get("declared_wilson_lower_95") or 0.0
    coverage = summary.get("coverage") or 0.0
    declared_n = summary.get("declared_n") or 0

    fold_precisions = [
        f.get("declared_hit_rate")
        for f in (folds or [])
        if f and f.get("declared_n", 0) >= 5
        and f.get("declared_hit_rate") is not None
    ]
    fold_floor = min(fold_precisions) if fold_precisions else 0.0

    enough = declared_n >= 10
    meets = enough and precision >= target
    stable = fold_floor >= max(0.0, target - 0.10)

    return (
        1 if meets and stable else 0,
        lcb,
        precision,
        coverage,
        declared_n,
    )
