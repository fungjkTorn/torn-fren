import argparse
import math
import statistics
from dataclasses import dataclass

from services.arrival_success_lab import TRAVEL_SECONDS
from services.projection_chain_lab_v2 import (
    ARRIVAL_POLICIES,
    BASE_METHODS,
    Strategy,
    _active_target_rows,
    _fmt_minutes,
    _fmt_rate,
    _qualified_series,
    _simulate_strategy,
    _summarize,
    _summarize_depth,
)

# Research-only V3. Nothing here is used by the live predictor.
#
# Goals:
# - select on older history and judge on untouched newer history
# - preserve frozen P2/P3/P4 forecasts
# - report projection-depth-specific performance
# - penalize early/late misses asymmetrically
# - learn residual bias only from earlier predictions
# - detect recent timing regimes
# - test time-of-day and quantity-informed lifetime estimates
# - rank by conservative confidence, not raw percentage alone

HOLDOUT_FRACTION = 0.25
MIN_HOLDOUT_ROWS = 20
EARLY_MISS_COST = 1.25
LATE_MISS_COST = 1.0


@dataclass(frozen=True)
class V3Strategy:
    lifetime: str
    wait: str
    arrival_policy: str
    bias_policy: str = "none"

    @property
    def name(self):
        return (
            f"{self.lifetime} + {self.wait} + {self.arrival_policy}"
            f" + bias:{self.bias_policy}"
        )


EXTRA_LIFETIME_METHODS = (
    "recent_regime",
    "same_hour_median",
    "tod_recent_blend",
    "quantity_rate",
)

EXTRA_WAIT_METHODS = (
    "recent_regime",
    "same_hour_median",
    "tod_recent_blend",
)

BIAS_POLICIES = (
    "none",
    "depth_recent10",
    "depth_recent20",
    "depth_all",
)


def _vals(values):
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def _median(values):
    values = _vals(values)
    return statistics.median(values) if values else None


def _mean(values):
    values = _vals(values)
    return statistics.mean(values) if values else None


def _mad(values):
    values = _vals(values)
    if not values:
        return None
    med = statistics.median(values)
    return statistics.median(abs(v - med) for v in values)


def _hour_distance(a_ts, b_ts):
    a = (float(a_ts) % 86400) / 3600.0
    b = (float(b_ts) % 86400) / 3600.0
    return abs(((a - b + 12.0) % 24.0) - 12.0)


def _recent_regime(values):
    values = _vals(values)
    if not values:
        return None
    broad = statistics.median(values)
    recent = values[-5:]
    if len(recent) < 3:
        return broad
    rmed = statistics.median(recent)
    mad = _mad(values)
    scale = max(60.0, 1.4826 * mad) if mad is not None else 60.0
    shift = abs(rmed - broad) / scale
    # Only jump to the recent regime when the recent shift is materially larger
    # than normal robust dispersion. Otherwise retain a stable blended estimate.
    recent_weight = 0.80 if shift >= 1.25 else 0.60 if shift >= 0.75 else 0.35
    return recent_weight * rmed + (1.0 - recent_weight) * broad


def _same_hour(values, timestamps, target_ts, hours=3.0):
    pairs = [
        (float(v), int(ts))
        for v, ts in zip(values, timestamps)
        if v is not None and ts is not None
    ]
    nearby = [v for v, ts in pairs if _hour_distance(ts, target_ts) <= hours]
    if len(nearby) >= 5:
        return statistics.median(nearby)
    return _median(v for v, _ in pairs)


def _tod_recent_blend(values, timestamps, target_ts):
    tod = _same_hour(values, timestamps, target_ts, hours=3.0)
    recent = _median(_vals(values)[-5:])
    broad = _median(values)
    parts = []
    if tod is not None:
        parts.append((0.45, tod))
    if recent is not None:
        parts.append((0.35, recent))
    if broad is not None:
        parts.append((0.20, broad))
    if not parts:
        return None
    weight = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / weight


def _quantity_rate_lifetime(cycles, target_ts):
    usable = [
        c for c in cycles
        if c.get("peak_quantity")
        and c.get("lifetime_seconds")
        and c.get("lifetime_seconds") > 0
        and c.get("restock_time") is not None
    ]
    if len(usable) < 8:
        return _median(c.get("lifetime_seconds") for c in usable)

    expected_peak = _median(c.get("peak_quantity") for c in usable[-5:])
    if not expected_peak:
        return _median(c.get("lifetime_seconds") for c in usable)

    nearby = [
        c for c in usable
        if _hour_distance(c["restock_time"], target_ts) <= 3.0
    ]
    if len(nearby) < 5:
        nearby = usable[-30:]

    rates = [
        float(c["peak_quantity"]) / (float(c["lifetime_seconds"]) / 60.0)
        for c in nearby
        if c.get("peak_quantity") and c.get("lifetime_seconds")
    ]
    rate = _median(rates)
    if not rate or rate <= 0:
        return _median(c.get("lifetime_seconds") for c in usable)
    return float(expected_peak) / (float(rate) / 60.0)


def _base_estimate(values, method):
    # Reuse V2's tested estimators without importing its private dispatch.
    values = _vals(values)
    if not values:
        return None
    if method == "all_median":
        return statistics.median(values)
    if method == "recent3_mean":
        return statistics.mean(values[-3:])
    if method == "recent5_mean":
        return statistics.mean(values[-5:])
    if method == "recent5_median":
        return statistics.median(values[-5:])
    if method == "recent10_median":
        return statistics.median(values[-10:])
    if method == "weighted_recent5":
        vals = values[-5:]
        weights = list(range(1, len(vals) + 1))
        return sum(v * w for v, w in zip(vals, weights)) / sum(weights)
    if method in {"ewma35", "ewma55"}:
        alpha = 0.35 if method == "ewma35" else 0.55
        out = values[0]
        for v in values[1:]:
            out = alpha * v + (1.0 - alpha) * out
        return out
    if method == "trimmed10_mean":
        vals = sorted(values[-10:])
        if len(vals) >= 5:
            trim = max(1, int(len(vals) * 0.10))
            if len(vals) - 2 * trim >= 3:
                vals = vals[trim:-trim]
        return statistics.mean(vals)
    if method == "blend_recent5_all":
        return 0.70 * statistics.median(values[-5:]) + 0.30 * statistics.median(values)
    if method == "trend5_clipped":
        recent = values[-5:]
        if len(recent) < 3:
            return statistics.median(values)
        xs = list(range(len(recent)))
        xb, yb = statistics.mean(xs), statistics.mean(recent)
        denom = sum((x - xb) ** 2 for x in xs)
        slope = sum((x - xb) * (y - yb) for x, y in zip(xs, recent)) / denom if denom else 0
        pred = yb + slope * (len(recent) - xb)
        ordered = sorted(values)
        lo = ordered[max(0, int((len(ordered) - 1) * 0.10))]
        hi = ordered[min(len(ordered) - 1, int(math.ceil((len(ordered) - 1) * 0.90)))]
        return min(hi, max(lo, pred))
    raise ValueError(method)


def _estimate_lifetime(method, known_cycles, target_ts):
    values = [c.get("lifetime_seconds") for c in known_cycles]
    timestamps = [c.get("restock_time") for c in known_cycles]
    if method in BASE_METHODS:
        return _base_estimate(values, method)
    if method == "recent_regime":
        return _recent_regime(values)
    if method == "same_hour_median":
        return _same_hour(values, timestamps, target_ts)
    if method == "tod_recent_blend":
        return _tod_recent_blend(values, timestamps, target_ts)
    if method == "quantity_rate":
        return _quantity_rate_lifetime(known_cycles, target_ts)
    raise ValueError(method)


def _estimate_wait(method, known_wait_rows, target_ts):
    values = [r["seconds"] for r in known_wait_rows]
    timestamps = [r["to_restock"] for r in known_wait_rows]
    if method in BASE_METHODS:
        return _base_estimate(values, method)
    if method == "recent_regime":
        return _recent_regime(values)
    if method == "same_hour_median":
        return _same_hour(values, timestamps, target_ts)
    if method == "tod_recent_blend":
        return _tod_recent_blend(values, timestamps, target_ts)
    raise ValueError(method)


def _wilson_lower(hits, n, z=1.96):
    if not n:
        return None
    p = hits / n
    denom = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4.0 * n)) / n)
    return (center - margin) / denom


def _depth_bias(prior_rows, policy):
    if policy == "none":
        return 0.0
    usable = [float(r["signed_error_seconds"]) for r in prior_rows if r.get("signed_error_seconds") is not None]
    if not usable:
        return 0.0
    if policy == "depth_recent10":
        usable = usable[-10:]
    elif policy == "depth_recent20":
        usable = usable[-20:]
    elif policy != "depth_all":
        raise ValueError(policy)
    if len(usable) < 5:
        return 0.0
    # Positive signed error means actual restock was later than predicted.
    return statistics.median(usable)


def _arrival_offset(policy, life_est, prior_rows):
    if policy == "midpoint":
        return life_est * 0.50
    if policy == "late65":
        return life_est * 0.65
    if policy == "late75":
        return life_est * 0.75

    limit = None if policy == "adaptive_all" else 20 if policy == "adaptive20" else 10
    usable = [
        r for r in prior_rows
        if r.get("signed_error_seconds") is not None
        and r.get("actual_lifetime_seconds") is not None
        and r["actual_lifetime_seconds"] > 0
    ]
    if limit:
        usable = usable[-limit:]
    if len(usable) < 5:
        return life_est * 0.50

    candidates = {0.0}
    for r in usable:
        lo = float(r["signed_error_seconds"])
        hi = lo + float(r["actual_lifetime_seconds"])
        candidates.add(lo)
        candidates.add(hi)
        candidates.add((lo + hi) / 2.0)

    best = None
    for offset in candidates:
        if abs(offset) > max(60.0, life_est * 1.5):
            continue
        hits = 0
        margins = []
        for r in usable:
            lo = float(r["signed_error_seconds"])
            hi = lo + float(r["actual_lifetime_seconds"])
            if lo <= offset < hi:
                hits += 1
                margins.append(min(offset - lo, hi - offset))
        rate = hits / len(usable)
        margin = statistics.median(margins) if margins else -1
        score = (rate, margin, -abs(offset), offset)
        if best is None or score > best:
            best = score
    return best[-1] if best else life_est * 0.50


def _simulate_v3(cycles, wait_map, strategy, travel_seconds, max_depth=4, min_history=8):
    rows = []
    prior_by_depth = {d: [] for d in range(1, max_depth + 1)}

    wait_rows_all = [
        {"from_depletion": int(dep), "to_restock": None, "seconds": float(sec)}
        for dep, sec in wait_map.items()
    ]
    # Recover to_restock from the next cycle boundary where possible.
    restock_by_prev_dep = {}
    for i in range(len(cycles) - 1):
        restock_by_prev_dep[int(cycles[i]["depletion_time"])] = int(cycles[i + 1]["restock_time"])
    for row in wait_rows_all:
        row["to_restock"] = restock_by_prev_dep.get(row["from_depletion"])

    for anchor_i, anchor in enumerate(cycles):
        anchor_ts = int(anchor["depletion_time"])
        known_cycles = [
            c for c in cycles[: anchor_i + 1]
            if int(c["depletion_time"]) <= anchor_ts
        ]
        known_waits = [
            r for r in wait_rows_all
            if r["from_depletion"] < anchor_ts and r["to_restock"] is not None
        ]
        if len(known_cycles) < min_history or len(known_waits) < min_history:
            continue

        projected_restock = None
        anchor_rows = []

        for depth in range(1, max_depth + 1):
            target_i = anchor_i + depth
            if target_i >= len(cycles):
                break

            if depth == 1:
                wait_est = _estimate_wait(strategy.wait, known_waits, anchor_ts)
                if not wait_est:
                    break
                projected_restock = anchor_ts + wait_est
            else:
                life_est_prev = _estimate_lifetime(
                    strategy.lifetime, known_cycles, projected_restock
                )
                wait_est = _estimate_wait(
                    strategy.wait, known_waits, projected_restock + (life_est_prev or 0)
                )
                if not life_est_prev or not wait_est:
                    break
                projected_restock += life_est_prev + wait_est

            life_est = _estimate_lifetime(
                strategy.lifetime, known_cycles, projected_restock
            )
            if not life_est or life_est <= 0:
                break

            prior = prior_by_depth[depth]
            bias = _depth_bias(prior, strategy.bias_policy)
            corrected_restock = projected_restock + bias

            target = cycles[target_i]
            actual_restock = float(target["restock_time"])
            actual_depletion = float(target["depletion_time"])
            actual_lifetime = actual_depletion - actual_restock
            error = actual_restock - corrected_restock

            arrival_offset = _arrival_offset(strategy.arrival_policy, life_est, prior)
            recommended_arrival = corrected_restock + arrival_offset
            recommended_departure = (
                recommended_arrival - travel_seconds if travel_seconds is not None else None
            )
            actionable = (
                recommended_departure is not None and recommended_departure >= anchor_ts
            )

            hit = int(actual_restock <= recommended_arrival < actual_depletion)
            early = int(recommended_arrival < actual_restock)
            late = int(recommended_arrival >= actual_depletion)
            loss = 0.0 if hit else EARLY_MISS_COST if early else LATE_MISS_COST

            row = {
                "anchor_timestamp": anchor_ts,
                "depth": depth,
                "predicted_restock_timestamp": corrected_restock,
                "raw_predicted_restock_timestamp": projected_restock,
                "bias_correction_seconds": bias,
                "actual_restock_timestamp": actual_restock,
                "actual_depletion_timestamp": actual_depletion,
                "actual_lifetime_seconds": actual_lifetime,
                "signed_error_seconds": error,
                "absolute_error_seconds": abs(error),
                "lifetime_estimate_seconds": life_est,
                "wait_estimate_seconds": wait_est,
                "recommended_arrival_timestamp": recommended_arrival,
                "recommended_departure_timestamp": recommended_departure,
                "actionable_from_anchor": int(actionable),
                "arrival_hit": hit,
                "early_arrival": early,
                "late_arrival": late,
                "travel_loss": loss,
            }
            rows.append(row)
            anchor_rows.append(row)

        for row in anchor_rows:
            prior_by_depth[row["depth"]].append(row)

    return rows


def _summary(rows):
    if not rows:
        return None
    actionable = [r for r in rows if r["actionable_from_anchor"]]
    population = actionable or rows
    hits = sum(r["arrival_hit"] for r in population)
    n = len(population)
    errors = [r["absolute_error_seconds"] for r in population]
    signed = [r["signed_error_seconds"] for r in population]
    return {
        "n": len(rows),
        "actionable_n": len(actionable),
        "arrival_hit_rate": hits / n,
        "wilson_lower_95": _wilson_lower(hits, n),
        "early_rate": sum(r["early_arrival"] for r in population) / n,
        "late_rate": sum(r["late_arrival"] for r in population) / n,
        "mean_asymmetric_loss": statistics.mean(r["travel_loss"] for r in population),
        "median_absolute_error_seconds": statistics.median(errors),
        "p90_absolute_error_seconds": sorted(errors)[min(len(errors)-1, int(math.ceil(.90*(len(errors)-1))))],
        "signed_bias_seconds": statistics.median(signed),
    }


def _split_timestamp(rows, holdout_fraction=HOLDOUT_FRACTION):
    anchors = sorted({int(r["anchor_timestamp"]) for r in rows})
    if len(anchors) < MIN_HOLDOUT_ROWS + 20:
        return None
    cut_index = max(1, min(len(anchors)-MIN_HOLDOUT_ROWS, int(len(anchors)*(1-holdout_fraction))))
    return anchors[cut_index]


def _evaluate_rows(rows, split_ts, depth=None, active_only=False):
    subset = [r for r in rows if int(r["anchor_timestamp"]) >= split_ts]
    if depth is not None:
        subset = [r for r in subset if r["depth"] == depth]
    if active_only:
        grouped = {}
        for r in subset:
            grouped.setdefault(r["anchor_timestamp"], []).append(r)
        chosen = []
        for group in grouped.values():
            reachable = sorted((r for r in group if r["actionable_from_anchor"]), key=lambda r:r["depth"])
            if reachable:
                chosen.append(reachable[0])
        subset = chosen
    return _summary(subset)


def _selection_rows(rows, split_ts, depth=None, active_only=False):
    subset = [r for r in rows if int(r["anchor_timestamp"]) < split_ts]
    if depth is not None:
        subset = [r for r in subset if r["depth"] == depth]
    if active_only:
        grouped = {}
        for r in subset:
            grouped.setdefault(r["anchor_timestamp"], []).append(r)
        chosen = []
        for group in grouped.values():
            reachable = sorted((r for r in group if r["actionable_from_anchor"]), key=lambda r:r["depth"])
            if reachable:
                chosen.append(reachable[0])
        subset = chosen
    return _summary(subset)


def conservative_key(summary):
    if not summary:
        return (-1, -999, -999, -999)
    return (
        summary.get("wilson_lower_95") if summary.get("wilson_lower_95") is not None else -1,
        -summary.get("mean_asymmetric_loss", 999),
        -summary.get("median_absolute_error_seconds", 1e18),
        -summary.get("p90_absolute_error_seconds", 1e18),
    )


def candidate_strategies():
    lifetimes = tuple(BASE_METHODS) + EXTRA_LIFETIME_METHODS
    waits = tuple(BASE_METHODS) + EXTRA_WAIT_METHODS
    for life in lifetimes:
        for wait in waits:
            for arrival in ARRIVAL_POLICIES:
                for bias in BIAS_POLICIES:
                    yield V3Strategy(life, wait, arrival, bias)


def evaluate_strategy(country, item_name, strategy, max_depth=4, min_history=8):
    cycles, waits = _qualified_series(country, item_name, exclude_travel_day=True)
    rows = _simulate_v3(
        cycles, waits, strategy, TRAVEL_SECONDS.get(country.lower()),
        max_depth=max_depth, min_history=min_history,
    )
    split_ts = _split_timestamp(rows)
    if split_ts is None:
        return None
    return {
        "strategy": strategy,
        "rows": rows,
        "split_timestamp": split_ts,
        "train_active": _selection_rows(rows, split_ts, active_only=True),
        "holdout_active": _evaluate_rows(rows, split_ts, active_only=True),
        "train_by_depth": {
            d: _selection_rows(rows, split_ts, depth=d)
            for d in range(1, max_depth + 1)
        },
        "holdout_by_depth": {
            d: _evaluate_rows(rows, split_ts, depth=d)
            for d in range(1, max_depth + 1)
        },
    }


def rolling_fold_score(rows, depth, folds=4):
    anchors = sorted({int(r["anchor_timestamp"]) for r in rows})
    if len(anchors) < 40:
        return []
    fold_size = max(10, len(anchors) // (folds + 1))
    outputs = []
    for fold in range(1, folds + 1):
        start_i = min(len(anchors)-1, fold * fold_size)
        end_i = min(len(anchors), start_i + fold_size)
        if start_i >= end_i:
            continue
        lo, hi = anchors[start_i], anchors[end_i-1]
        subset = [
            r for r in rows
            if r["depth"] == depth and lo <= int(r["anchor_timestamp"]) <= hi
        ]
        s = _summary(subset)
        if s:
            outputs.append(s)
    return outputs


def print_evaluation(entry, max_depth=4):
    print(entry["strategy"].name)
    a = entry["holdout_active"]
    if a:
        print(
            f"  HOLDOUT ACTIVE: hit={_fmt_rate(a['arrival_hit_rate'])} "
            f"LCB95={_fmt_rate(a['wilson_lower_95'])} "
            f"early={_fmt_rate(a['early_rate'])} late={_fmt_rate(a['late_rate'])} "
            f"MedAE={_fmt_minutes(a['median_absolute_error_seconds'])} "
            f"P90={_fmt_minutes(a['p90_absolute_error_seconds'])}"
        )
    for d in range(1, max_depth + 1):
        s = entry["holdout_by_depth"].get(d)
        if s:
            print(
                f"  D{d}: hit={_fmt_rate(s['arrival_hit_rate'])} "
                f"LCB95={_fmt_rate(s['wilson_lower_95'])} "
                f"early={_fmt_rate(s['early_rate'])} late={_fmt_rate(s['late_rate'])} "
                f"MedAE={_fmt_minutes(s['median_absolute_error_seconds'])}"
            )


def main():
    parser = argparse.ArgumentParser(description="Research-only V3 frozen projection evaluator.")
    parser.add_argument("country")
    parser.add_argument("item_name")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--min-history", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="For smoke tests only.")
    args = parser.parse_args()

    count = 0
    for strategy in candidate_strategies():
        result = evaluate_strategy(
            args.country, args.item_name, strategy,
            max_depth=max(1, args.depth), min_history=max(3, args.min_history),
        )
        if result:
            print_evaluation(result, max_depth=max(1, args.depth))
        count += 1
        if args.limit and count >= args.limit:
            break


if __name__ == "__main__":
    main()
