import math
import statistics
from dataclasses import dataclass

from services.arrival_success_lab import TRAVEL_SECONDS
from services.projection_chain_lab_v2 import _interval_crosses_travel_day
from services.projection_chain_lab_v3 import (
    ARRIVAL_POLICIES,
    BASE_METHODS,
    BIAS_POLICIES,
    EXTRA_LIFETIME_METHODS,
    EXTRA_WAIT_METHODS,
    EARLY_MISS_COST,
    LATE_MISS_COST,
    V3Strategy,
    _calibrated_error_window,
    _estimate_lifetime,
    _estimate_wait,
    _qualified_series,
    _wilson_lower,
)

# Optimized offline research engine.
#
# Key difference from V3:
#   Point forecast chains depend only on (lifetime model, wait model).
#   Arrival policy and residual-bias policy are layered on afterward.
#
# Therefore a finalist pair is NOT recomputed 24 times for:
#   6 arrival policies x 4 bias policies.
#
# This module also builds the historical item context once per item instead of
# reopening / rebuilding the SQLite history for every strategy.


DIRECT_HORIZON_METHODS = (
    "all_median",
    "recent5_median",
    "weighted_recent5",
    "recent_regime",
    "same_hour_median",
    "tod_recent_blend",
)


def _direct_horizon_rows(cycles, anchor_i, depth, anchor_ts):
    """Leak-free prior samples of depletion->Nth-future-restock duration."""
    rows = []
    for source_i in range(anchor_i):
        target_i = source_i + depth
        if target_i >= len(cycles) or target_i > anchor_i:
            break
        source = cycles[source_i]
        target = cycles[target_i]
        chain = cycles[source_i : target_i + 1]
        if any(
            c.get("_excluded_regime")
            or not c.get("_valid_for_training", True)
            for c in chain
        ):
            continue
        source_dep = int(source["depletion_time"])
        target_restock = int(target["restock_time"])
        target_dep = int(target["depletion_time"])
        if target_restock >= anchor_ts:
            continue
        if _interval_crosses_travel_day(source_dep, target_dep):
            continue
        seconds = target_restock - source_dep
        if seconds <= 0:
            continue
        rows.append({
            "from_depletion": source_dep,
            "to_restock": target_restock,
            "seconds": float(seconds),
        })
    return rows


@dataclass
class ItemContext:
    country: str
    item_name: str
    cycles: list
    wait_rows: list
    travel_seconds: float | None
    split_timestamp: int | None
    max_depth: int
    min_history: int


def _holdout_split_from_cycles(cycles, holdout_fraction=0.25, min_holdout=20):
    anchors = sorted(
        int(c["depletion_time"])
        for c in cycles
        if c.get("depletion_time") is not None
        and not c.get("_excluded_regime")
        and c.get("_valid_for_training", True)
    )
    if len(anchors) < min_holdout + 20:
        return None
    cut = int(len(anchors) * (1.0 - holdout_fraction))
    cut = max(1, min(len(anchors) - min_holdout, cut))
    return anchors[cut]


def build_item_context(country, item_name, max_depth=4, min_history=8):
    cycles, wait_map = _qualified_series(
        country, item_name, exclude_travel_day=True
    )

    restock_by_prev_dep = {}
    for i in range(len(cycles) - 1):
        restock_by_prev_dep[int(cycles[i]["depletion_time"])] = int(
            cycles[i + 1]["restock_time"]
        )

    wait_rows = []
    for dep, seconds in sorted(wait_map.items()):
        to_restock = restock_by_prev_dep.get(int(dep))
        if to_restock is None:
            continue
        wait_rows.append({
            "from_depletion": int(dep),
            "to_restock": int(to_restock),
            "seconds": float(seconds),
        })

    return ItemContext(
        country=country.lower(),
        item_name=item_name,
        cycles=cycles,
        wait_rows=wait_rows,
        travel_seconds=TRAVEL_SECONDS.get(country.lower()),
        split_timestamp=_holdout_split_from_cycles(cycles),
        max_depth=max_depth,
        min_history=min_history,
    )


def point_forecast_pair(ctx, lifetime_method, wait_method):
    """
    Build the frozen raw P1..Pn chains exactly once for a lifetime/wait pair.

    No arrival policy and no residual bias is applied here.
    """
    rows = []
    cycles = ctx.cycles
    waits = ctx.wait_rows

    for anchor_i, anchor in enumerate(cycles):
        if (
            anchor.get("_excluded_regime")
            or not anchor.get("_valid_for_training", True)
        ):
            continue
        anchor_ts = int(anchor["depletion_time"])

        known_cycles = [
            c for c in cycles[: anchor_i + 1]
            if not c.get("_excluded_regime")
            and c.get("_valid_for_training", True)
        ]
        # wait_rows are chronological; avoid rebuilding from SQLite and only
        # select information genuinely available before this anchor.
        known_waits = [r for r in waits if r["from_depletion"] < anchor_ts]

        if (
            len(known_cycles) < ctx.min_history
            or len(known_waits) < ctx.min_history
        ):
            continue

        projected_restock = None
        predicted_wait_total = 0.0
        predicted_bridge_lifetime_total = 0.0

        for depth in range(1, ctx.max_depth + 1):
            target_i = anchor_i + depth
            if target_i >= len(cycles):
                break

            direct_method = (
                wait_method.split(":", 1)[1]
                if wait_method.startswith("direct:")
                else None
            )
            if direct_method:
                horizon_rows = _direct_horizon_rows(
                    cycles, anchor_i, depth, anchor_ts
                )
                if len(horizon_rows) < ctx.min_history:
                    continue
                horizon_est = _estimate_wait(
                    direct_method, horizon_rows, anchor_ts
                )
                if not horizon_est or horizon_est <= 0:
                    continue
                projected_restock = float(anchor_ts) + float(horizon_est)
                wait_est = float(horizon_est)
                predicted_wait_total = float(horizon_est)
                predicted_bridge_lifetime_total = 0.0
            elif depth == 1:
                wait_est = _estimate_wait(
                    wait_method, known_waits, anchor_ts
                )
                if not wait_est or wait_est <= 0:
                    break
                projected_restock = float(anchor_ts) + float(wait_est)
                predicted_wait_total += float(wait_est)
            else:
                life_bridge = _estimate_lifetime(
                    lifetime_method, known_cycles, projected_restock
                )
                if not life_bridge or life_bridge <= 0:
                    break

                wait_est = _estimate_wait(
                    wait_method,
                    known_waits,
                    projected_restock + float(life_bridge),
                )
                if not wait_est or wait_est <= 0:
                    break

                predicted_bridge_lifetime_total += float(life_bridge)
                predicted_wait_total += float(wait_est)
                projected_restock += float(life_bridge) + float(wait_est)

            target_lifetime = _estimate_lifetime(
                lifetime_method, known_cycles, projected_restock
            )
            if not target_lifetime or target_lifetime <= 0:
                break

            target = cycles[target_i]
            actual_restock = float(target["restock_time"])
            actual_depletion = float(target["depletion_time"])
            chain_cycles = cycles[anchor_i : target_i + 1]
            if (
                any(
                    c.get("_excluded_regime")
                    or not c.get("_valid_for_training", True)
                    for c in chain_cycles
                )
                or _interval_crosses_travel_day(anchor_ts, actual_depletion)
            ):
                break

            actual_bridge_lifetime_total = sum(
                float(cycles[j]["lifetime_seconds"])
                for j in range(anchor_i + 1, target_i)
            )
            actual_total = actual_restock - float(anchor_ts)
            actual_wait_total = actual_total - actual_bridge_lifetime_total

            rows.append({
                "anchor_timestamp": anchor_ts,
                "depth": depth,
                "raw_predicted_restock_timestamp": float(projected_restock),
                "actual_restock_timestamp": actual_restock,
                "actual_depletion_timestamp": actual_depletion,
                "actual_lifetime_seconds": actual_depletion - actual_restock,
                "lifetime_estimate_seconds": float(target_lifetime),
                "wait_estimate_seconds": float(wait_est),
                "forecast_mode": "direct_horizon" if direct_method else "recursive",
                "predicted_wait_total_seconds": (
                    None if direct_method else predicted_wait_total
                ),
                "predicted_bridge_lifetime_total_seconds": (
                    None if direct_method else predicted_bridge_lifetime_total
                ),
                "actual_wait_total_seconds": actual_wait_total,
                "actual_bridge_lifetime_total_seconds": actual_bridge_lifetime_total,
                "wait_component_error_seconds": (
                    None if direct_method
                    else actual_wait_total - predicted_wait_total
                ),
                "lifetime_component_error_seconds": (
                    None if direct_method
                    else actual_bridge_lifetime_total - predicted_bridge_lifetime_total
                ),
                "direct_horizon_error_seconds": (
                    (actual_restock - float(anchor_ts)) - float(wait_est)
                    if direct_method else None
                ),
            })

    return rows


def _median_error(prior_rows, policy):
    if policy == "none":
        return 0.0

    values = [
        float(r["signed_error_seconds"])
        for r in prior_rows
        if r.get("signed_error_seconds") is not None
    ]
    if policy == "depth_recent10":
        values = values[-10:]
    elif policy == "depth_recent20":
        values = values[-20:]
    elif policy != "depth_all":
        raise ValueError(policy)

    return statistics.median(values) if len(values) >= 5 else 0.0


def _adaptive_arrival_offset(prior_rows, policy, life_est):
    fixed_seconds = {
        "restock0": 0.0,
        "plus1m": 60.0,
        "plus2m": 120.0,
        "plus3m": 180.0,
        "plus5m": 300.0,
    }
    if policy in fixed_seconds:
        return fixed_seconds[policy]

    fixed_fractions = {
        "early35": 0.35,
        "midpoint": 0.50,
        "late65": 0.65,
        "late75": 0.75,
        "late85": 0.85,
    }
    if policy in fixed_fractions:
        return life_est * fixed_fractions[policy]

    usable = [
        r for r in prior_rows
        if r.get("signed_error_seconds") is not None
        and r.get("actual_lifetime_seconds") is not None
        and r["actual_lifetime_seconds"] > 0
    ]

    if policy.startswith("adaptive_fraction"):
        recent_limit = (
            None if policy == "adaptive_fraction_all"
            else 20 if policy == "adaptive_fraction20"
            else 10 if policy == "adaptive_fraction10"
            else None
        )
        if policy not in {
            "adaptive_fraction_all", "adaptive_fraction20", "adaptive_fraction10"
        }:
            raise ValueError(policy)
        if recent_limit:
            usable = usable[-recent_limit:]
        if len(usable) < 5:
            return life_est * 0.50

        best = None
        for fraction in [x / 20.0 for x in range(2, 20)]:
            hits = 0
            margins = []
            for r in usable:
                historical_life = float(
                    r.get("lifetime_estimate_seconds") or life_est
                )
                offset = historical_life * fraction
                lo = float(r["signed_error_seconds"])
                hi = lo + float(r["actual_lifetime_seconds"])
                if lo <= offset < hi:
                    hits += 1
                    margins.append(min(offset - lo, hi - offset))
            rate = hits / len(usable)
            margin = statistics.median(margins) if margins else -1.0
            score = (rate, margin, -abs(fraction - 0.5), fraction)
            if best is None or score > best:
                best = score
        return life_est * (best[-1] if best else 0.50)

    if policy not in {"adaptive_all", "adaptive20", "adaptive10"}:
        raise ValueError(policy)

    recent_limit = (
        None if policy == "adaptive_all"
        else 20 if policy == "adaptive20"
        else 10
    )
    if recent_limit:
        usable = usable[-recent_limit:]
    if len(usable) < 5:
        return life_est * 0.50

    # Candidate boundaries are enough to maximize interval coverage. Include
    # midpoints to prefer safer center-of-stock solutions on ties.
    boundaries = {0.0}
    for r in usable:
        lo = float(r["signed_error_seconds"])
        hi = lo + float(r["actual_lifetime_seconds"])
        boundaries.add(lo)
        boundaries.add(hi)

    ordered = sorted(boundaries)
    candidates = list(ordered)
    candidates.extend(
        (a + b) / 2.0 for a, b in zip(ordered, ordered[1:])
    )

    max_offset = max(60.0, float(life_est) * 1.5)
    best = None
    for offset in candidates:
        if abs(offset) > max_offset:
            continue

        hits = 0
        margins = []
        for r in usable:
            lo = float(r["signed_error_seconds"])
            hi = lo + float(r["actual_lifetime_seconds"])
            if lo <= offset < hi:
                hits += 1
                rel = offset - lo
                margins.append(min(rel, hi - offset))

        rate = hits / len(usable)
        margin = statistics.median(margins) if margins else -1.0
        candidate = (rate, margin, -abs(offset), offset)
        if best is None or candidate > best:
            best = candidate

    return best[-1] if best else life_est * 0.50


def apply_policy(ctx, point_rows, arrival_policy, bias_policy, window_policy="end_floor"):
    """
    Apply one arrival/bias policy to a precomputed point chain.

    This is intentionally cheap relative to rebuilding point forecasts.
    """
    prior_by_depth = {
        d: [] for d in range(1, ctx.max_depth + 1)
    }
    output = []

    # point_rows are emitted chronologically by anchor, then by depth.
    for raw in point_rows:
        depth = int(raw["depth"])
        prior = prior_by_depth[depth]

        bias = _median_error(prior, bias_policy)
        corrected = float(raw["raw_predicted_restock_timestamp"]) + bias
        actual_restock = float(raw["actual_restock_timestamp"])
        actual_depletion = float(raw["actual_depletion_timestamp"])
        error = actual_restock - corrected

        life_est = float(raw["lifetime_estimate_seconds"])
        offset = _adaptive_arrival_offset(prior, arrival_policy, life_est)

        # Use only earlier residuals at the same depth.
        window = _calibrated_error_window(
            prior, coverage=0.90, recent_limit=40
        )

        recommended_arrival = corrected + offset
        if window is not None:
            window_lo = corrected + float(window["lo"])
            window_hi = corrected + float(window["hi"])
            window_mid = (window_lo + window_hi) / 2.0
            if window_policy == "none":
                pass
            elif window_policy == "midpoint_floor":
                recommended_arrival = max(recommended_arrival, window_mid)
            elif window_policy == "end_floor":
                recommended_arrival = max(recommended_arrival, window_hi)
            else:
                raise ValueError(window_policy)

        departure = (
            recommended_arrival - ctx.travel_seconds
            if ctx.travel_seconds is not None
            else None
        )
        actionable = (
            departure is not None
            and departure >= float(raw["anchor_timestamp"])
        )

        hit = int(actual_restock <= recommended_arrival < actual_depletion)
        early = int(recommended_arrival < actual_restock)
        late = int(recommended_arrival >= actual_depletion)
        loss = (
            0.0 if hit
            else EARLY_MISS_COST if early
            else LATE_MISS_COST
        )

        row = dict(raw)
        row.update({
            "predicted_restock_timestamp": corrected,
            "bias_correction_seconds": bias,
            "signed_error_seconds": error,
            "absolute_error_seconds": abs(error),
            "arrival_offset_seconds": offset,
            "recommended_arrival_timestamp": recommended_arrival,
            "recommended_departure_timestamp": departure,
            "actionable_from_anchor": int(actionable),
            "arrival_hit": hit,
            "early_arrival": early,
            "late_arrival": late,
            "travel_loss": loss,
            "calibrated_window_lo_seconds": (
                window["lo"] if window else None
            ),
            "calibrated_window_hi_seconds": (
                window["hi"] if window else None
            ),
            "calibrated_window_width_seconds": (
                window["width"] if window else None
            ),
        })

        output.append(row)
        prior.append(row)

    return output


def _summary(rows):
    if not rows:
        return None

    actionable = [r for r in rows if r["actionable_from_anchor"]]
    population = actionable or rows
    n = len(population)
    hits = sum(r["arrival_hit"] for r in population)
    errors = [r["absolute_error_seconds"] for r in population]

    return {
        "n": len(rows),
        "actionable_n": len(actionable),
        "arrival_hit_rate": hits / n,
        "wilson_lower_95": _wilson_lower(hits, n),
        "early_rate": sum(r["early_arrival"] for r in population) / n,
        "late_rate": sum(r["late_arrival"] for r in population) / n,
        "mean_asymmetric_loss": statistics.mean(
            r["travel_loss"] for r in population
        ),
        "median_absolute_error_seconds": statistics.median(errors),
        "mean_absolute_error_seconds": statistics.mean(errors),
        "p90_absolute_error_seconds": _percentile(errors, 0.90),
        "p95_absolute_error_seconds": _percentile(errors, 0.95),
        "signed_bias_seconds": statistics.median(
            r["signed_error_seconds"] for r in population
        ),
        "median_wait_component_error_seconds": (
            statistics.median([
                r["wait_component_error_seconds"] for r in population
                if r.get("wait_component_error_seconds") is not None
            ])
            if any(r.get("wait_component_error_seconds") is not None for r in population)
            else None
        ),
        "median_lifetime_component_error_seconds": (
            statistics.median([
                r["lifetime_component_error_seconds"] for r in population
                if r.get("lifetime_component_error_seconds") is not None
            ])
            if any(r.get("lifetime_component_error_seconds") is not None for r in population)
            else None
        ),
        "median_direct_horizon_error_seconds": (
            statistics.median([
                r["direct_horizon_error_seconds"] for r in population
                if r.get("direct_horizon_error_seconds") is not None
            ])
            if any(r.get("direct_horizon_error_seconds") is not None for r in population)
            else None
        ),
    }


def _percentile(values, p):
    values = sorted(float(v) for v in values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    x = (len(values) - 1) * p
    lo = int(math.floor(x))
    hi = int(math.ceil(x))
    if lo == hi:
        return values[lo]
    f = x - lo
    return values[lo] * (1.0 - f) + values[hi] * f


def active_target_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["anchor_timestamp"], []).append(row)

    selected = []
    for group in grouped.values():
        reachable = sorted(
            (r for r in group if r["actionable_from_anchor"]),
            key=lambda r: r["depth"],
        )
        if reachable:
            selected.append(reachable[0])
    return selected


def summarize_period(ctx, rows, period, depth=None, active=False):
    split = ctx.split_timestamp
    if split is None:
        return None

    if period == "train":
        subset = [
            r for r in rows
            if int(r["anchor_timestamp"]) < split
        ]
    elif period == "holdout":
        subset = [
            r for r in rows
            if int(r["anchor_timestamp"]) >= split
        ]
    else:
        raise ValueError(period)

    if depth is not None:
        subset = [r for r in subset if r["depth"] == depth]
    if active:
        subset = active_target_rows(subset)
    return _summary(subset)


def rolling_training_folds(ctx, rows, depth, folds=4):
    if ctx.split_timestamp is None:
        return []

    training = [
        r for r in rows
        if int(r["anchor_timestamp"]) < ctx.split_timestamp
        and r["depth"] == depth
    ]
    anchors = sorted({int(r["anchor_timestamp"]) for r in training})
    if len(anchors) < 40:
        return []

    fold_size = max(10, len(anchors) // (folds + 1))
    out = []
    for fold in range(1, folds + 1):
        start = fold * fold_size
        end = min(len(anchors), start + fold_size)
        if start >= end:
            continue
        allowed = set(anchors[start:end])
        summary = _summary([
            r for r in training
            if int(r["anchor_timestamp"]) in allowed
        ])
        if summary:
            out.append(summary)
    return out


def evaluate_from_point_rows(
    ctx,
    point_rows,
    lifetime_method,
    wait_method,
    arrival_policy,
    bias_policy,
    window_policy="end_floor",
):
    rows = apply_policy(
        ctx, point_rows, arrival_policy, bias_policy, window_policy
    )

    return {
        "strategy": V3Strategy(
            lifetime_method, wait_method, arrival_policy, bias_policy,
            window_policy
        ),
        "rows": rows,
        "split_timestamp": ctx.split_timestamp,
        "train_active": summarize_period(
            ctx, rows, "train", active=True
        ),
        "holdout_active": summarize_period(
            ctx, rows, "holdout", active=True
        ),
        "train_by_depth": {
            d: summarize_period(ctx, rows, "train", depth=d)
            for d in range(1, ctx.max_depth + 1)
        },
        "holdout_by_depth": {
            d: summarize_period(ctx, rows, "holdout", depth=d)
            for d in range(1, ctx.max_depth + 1)
        },
        "rolling_folds_by_depth": {
            d: rolling_training_folds(ctx, rows, d)
            for d in range(1, ctx.max_depth + 1)
        },
    }


def all_point_pairs(ctx):
    lifetimes = tuple(BASE_METHODS) + EXTRA_LIFETIME_METHODS
    waits = tuple(BASE_METHODS) + EXTRA_WAIT_METHODS
    for life in lifetimes:
        for wait in waits:
            yield life, wait, point_forecast_pair(ctx, life, wait)

    # Direct-horizon models predict depletion->P2/P3/P4/P5 elapsed time
    # directly instead of recursively summing unobserved lifetimes and waits.
    # This is specifically intended to reduce compounded deeper-horizon error.
    for life in lifetimes:
        for method in DIRECT_HORIZON_METHODS:
            wait_label = f"direct:{method}"
            yield life, wait_label, point_forecast_pair(ctx, life, wait_label)
