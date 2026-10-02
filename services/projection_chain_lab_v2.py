import argparse
import math
import statistics
from dataclasses import dataclass
from itertools import product

from services.arrival_success_lab import TRAVEL_SECONDS
from services.history_service import (
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)


# Travel Day materially changed depletion behavior. Keep it out of the primary
# model-selection score while still allowing an explicit all-history comparison.
TRAVEL_DAY_START_TS = 1790308800
TRAVEL_DAY_END_TS = 1790568000


@dataclass(frozen=True)
class Strategy:
    lifetime: str
    wait: str
    arrival_policy: str

    @property
    def name(self):
        return f"{self.lifetime} + {self.wait} + {self.arrival_policy}"


BASE_METHODS = (
    "all_median",
    "recent3_mean",
    "recent5_mean",
    "recent5_median",
    "recent10_median",
    "weighted_recent5",
    "ewma35",
    "ewma55",
    "trimmed10_mean",
    "blend_recent5_all",
    "trend5_clipped",
)

ARRIVAL_POLICIES = (
    "early35",
    "midpoint",
    "late65",
    "late75",
    "late85",
    "adaptive_fraction_all",
    "adaptive_fraction20",
    "adaptive_fraction10",
    "adaptive_all",
    "adaptive20",
    "adaptive10",
)


def _vals(values):
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def _mean(values):
    values = _vals(values)
    return statistics.mean(values) if values else None


def _median(values):
    values = _vals(values)
    return statistics.median(values) if values else None


def _percentile(values, p):
    values = sorted(_vals(values))
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    x = (len(values) - 1) * float(p)
    lo = int(math.floor(x))
    hi = int(math.ceil(x))
    if lo == hi:
        return values[lo]
    frac = x - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def _weighted_recent(values, n=5):
    values = _vals(values)[-n:]
    if not values:
        return None
    weights = list(range(1, len(values) + 1))
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def _ewma(values, alpha):
    values = _vals(values)
    if not values:
        return None
    value = values[0]
    for current in values[1:]:
        value = alpha * current + (1.0 - alpha) * value
    return value


def _trimmed_mean(values, n=10):
    values = sorted(_vals(values)[-n:])
    if not values:
        return None
    if len(values) >= 5:
        trim = max(1, int(len(values) * 0.10))
        if len(values) - 2 * trim >= 3:
            values = values[trim:-trim]
    return statistics.mean(values)


def _trend5(values):
    values = _vals(values)
    recent = values[-5:]
    if len(recent) < 3:
        return _median(values)

    xs = list(range(len(recent)))
    xbar = statistics.mean(xs)
    ybar = statistics.mean(recent)
    denom = sum((x - xbar) ** 2 for x in xs)
    slope = (
        sum((x - xbar) * (y - ybar) for x, y in zip(xs, recent)) / denom
        if denom else 0.0
    )
    predicted = ybar + slope * (len(recent) - xbar)

    lo = _percentile(values, 0.10)
    hi = _percentile(values, 0.90)
    if lo is not None and hi is not None:
        predicted = min(hi, max(lo, predicted))
    return predicted


def _estimate(values, method):
    values = _vals(values)
    if not values:
        return None

    if method == "all_median":
        return _median(values)
    if method == "recent3_mean":
        return _mean(values[-3:])
    if method == "recent5_mean":
        return _mean(values[-5:])
    if method == "recent5_median":
        return _median(values[-5:])
    if method == "recent10_median":
        return _median(values[-10:])
    if method == "weighted_recent5":
        return _weighted_recent(values, 5)
    if method == "ewma35":
        return _ewma(values, 0.35)
    if method == "ewma55":
        return _ewma(values, 0.55)
    if method == "trimmed10_mean":
        return _trimmed_mean(values, 10)
    if method == "blend_recent5_all":
        recent = _median(values[-5:])
        broad = _median(values)
        return 0.70 * recent + 0.30 * broad
    if method == "trend5_clipped":
        return _trend5(values)

    raise ValueError(f"Unknown estimator: {method}")


def _qualified_series(country, item_name, exclude_travel_day=True):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, _ = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    cycles, _active, wait_samples = _build_validated_cycles(rows, country, item_name)

    valid_cycles = []
    for c in cycles:
        if not (
            c.get("complete")
            and not c.get("tiny_restock")
            and c.get("valid_lifetime")
            and c.get("restock_time") is not None
            and c.get("depletion_time") is not None
            and c.get("lifetime_seconds") is not None
        ):
            continue
        if (
            exclude_travel_day
            and TRAVEL_DAY_START_TS <= int(c["restock_time"]) < TRAVEL_DAY_END_TS
        ):
            continue
        valid_cycles.append(c)

    wait_by_from_depletion = {}
    for s in wait_samples:
        if not (
            s.get("valid")
            and s.get("from_depletion") is not None
            and s.get("to_restock") is not None
            and s.get("seconds") is not None
        ):
            continue
        if (
            exclude_travel_day
            and (
                TRAVEL_DAY_START_TS <= int(s["from_depletion"]) < TRAVEL_DAY_END_TS
                or TRAVEL_DAY_START_TS <= int(s["to_restock"]) < TRAVEL_DAY_END_TS
            )
        ):
            continue
        wait_by_from_depletion[int(s["from_depletion"])] = float(s["seconds"])

    return valid_cycles, wait_by_from_depletion


def _adaptive_offset(prior_rows, recent_limit=None, max_offset=None):
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
        error = float(r["signed_error_seconds"])
        lifetime = float(r["actual_lifetime_seconds"])
        boundaries.add(error)
        boundaries.add(error + lifetime)

    ordered = sorted(boundaries)
    candidates = set(ordered)
    for a, b in zip(ordered, ordered[1:]):
        candidates.add((a + b) / 2.0)

    if max_offset:
        candidates = {x for x in candidates if -max_offset <= x <= max_offset}

    best = None
    for offset in candidates:
        hits = []
        margins = []
        for r in usable:
            error = float(r["signed_error_seconds"])
            lifetime = float(r["actual_lifetime_seconds"])
            hit = error <= offset < error + lifetime
            hits.append(hit)
            if hit:
                rel = offset - error
                margins.append(min(rel, lifetime - rel))
        rate = sum(hits) / len(hits)
        margin = statistics.median(margins) if margins else -1.0
        candidate = (rate, margin, -abs(offset), offset)
        if best is None or candidate > best:
            best = candidate

    return best[-1] if best else None


def _adaptive_landing_fraction(prior_rows, recent_limit=None):
    """
    Learn WHERE inside the predicted stock lifetime to land.

    Unlike adaptive_offset (absolute seconds), this scales the target to the
    predicted lifetime at each historical issuance.  Every candidate is scored
    only on already-resolved prior forecasts at the same projection depth.
    """
    usable = [
        r for r in prior_rows
        if r.get("actual_restock_timestamp") is not None
        and r.get("actual_depletion_timestamp") is not None
        and r.get("predicted_restock_timestamp") is not None
        and r.get("lifetime_estimate_seconds")
        and r["lifetime_estimate_seconds"] > 0
    ]
    if recent_limit:
        usable = usable[-recent_limit:]
    if len(usable) < 5:
        return None

    # Fine enough to discover the useful region without overfitting to seconds.
    candidates = [x / 20.0 for x in range(2, 20)]  # 10% .. 95%
    scored = []
    for fraction in candidates:
        hits = 0
        margins = []
        early_seconds = []
        late_seconds = []

        for r in usable:
            arrival = (
                float(r["predicted_restock_timestamp"])
                + float(r["lifetime_estimate_seconds"]) * fraction
            )

            # Reproduce the same conservative late-window floor that was known
            # at the time of the historical recommendation.
            historical_window_end = r.get("window_end_timestamp")
            if historical_window_end is not None:
                arrival = max(arrival, float(historical_window_end))

            actual_start = float(r["actual_restock_timestamp"])
            actual_end = float(r["actual_depletion_timestamp"])

            if actual_start <= arrival < actual_end:
                hits += 1
                margins.append(min(arrival - actual_start, actual_end - arrival))
            elif arrival < actual_start:
                early_seconds.append(actual_start - arrival)
            else:
                late_seconds.append(arrival - actual_end)

        rate = hits / len(usable)
        median_margin = statistics.median(margins) if margins else -1.0
        # Tie-break toward lower miss severity and then a central landing point.
        miss_severity = (
            (statistics.median(early_seconds) if early_seconds else 0.0)
            + (statistics.median(late_seconds) if late_seconds else 0.0)
        )
        scored.append(
            (rate, median_margin, -miss_severity, -abs(fraction - 0.5), fraction)
        )

    return max(scored)[-1] if scored else None


def _arrival_offset(policy, life_est, prior_depth_rows):
    fixed_fractions = {
        "early35": 0.35,
        "midpoint": 0.50,
        "late65": 0.65,
        "late75": 0.75,
        "late85": 0.85,
    }
    if policy in fixed_fractions:
        return life_est * fixed_fractions[policy]

    if policy.startswith("adaptive_fraction"):
        recent_limit = None
        if policy == "adaptive_fraction20":
            recent_limit = 20
        elif policy == "adaptive_fraction10":
            recent_limit = 10
        elif policy != "adaptive_fraction_all":
            raise ValueError(f"Unknown arrival policy: {policy}")

        fraction = _adaptive_landing_fraction(
            prior_depth_rows,
            recent_limit=recent_limit,
        )
        if fraction is None:
            fraction = 0.50
        return life_est * fraction

    limit = None
    if policy == "adaptive20":
        limit = 20
    elif policy == "adaptive10":
        limit = 10
    elif policy != "adaptive_all":
        raise ValueError(f"Unknown arrival policy: {policy}")

    learned = _adaptive_offset(
        prior_depth_rows,
        recent_limit=limit,
        max_offset=max(life_est * 1.5, 60.0),
    )
    return learned if learned is not None else life_est * 0.50


def _restock_window(prior_depth_rows, target=0.90, max_width=None):
    errors = sorted(
        float(r["signed_error_seconds"])
        for r in prior_depth_rows
        if r.get("signed_error_seconds") is not None
    )
    if len(errors) < 8:
        return None

    # Shortest historical error interval covering target fraction. This is
    # walk-forward: only earlier issued forecasts are present in prior_depth_rows.
    need = max(1, int(math.ceil(len(errors) * target)))
    best = None
    for i in range(0, len(errors) - need + 1):
        lo = errors[i]
        hi = errors[i + need - 1]
        width = hi - lo
        if best is None or width < best[2]:
            best = (lo, hi, width)

    if best and max_width is not None and best[2] > max_width:
        return None
    return best


def _simulate_strategy(
    cycles,
    waits_by_depletion,
    strategy,
    travel_seconds,
    max_depth=4,
    min_history=8,
):
    rows = []
    prior_by_depth = {depth: [] for depth in range(1, max_depth + 1)}

    for anchor_i, anchor_cycle in enumerate(cycles):
        anchor_ts = int(anchor_cycle["depletion_time"])

        known_lifetimes = [
            float(c["lifetime_seconds"])
            for c in cycles[: anchor_i + 1]
            if int(c["depletion_time"]) <= anchor_ts
        ]
        known_waits = [
            float(waits_by_depletion[int(c["depletion_time"])])
            for c in cycles[:anchor_i]
            if int(c["depletion_time"]) in waits_by_depletion
            and int(c["depletion_time"]) < anchor_ts
        ]

        if len(known_lifetimes) < min_history or len(known_waits) < min_history:
            continue

        life_est = _estimate(known_lifetimes, strategy.lifetime)
        wait_est = _estimate(known_waits, strategy.wait)
        if not life_est or not wait_est or life_est <= 0 or wait_est <= 0:
            continue

        projected_restock = float(anchor_ts) + float(wait_est)
        anchor_rows = []

        for depth in range(1, max_depth + 1):
            target_i = anchor_i + depth
            if target_i >= len(cycles):
                break

            if depth > 1:
                projected_restock += float(life_est) + float(wait_est)

            target_cycle = cycles[target_i]
            actual_restock = float(target_cycle["restock_time"])
            actual_depletion = float(target_cycle["depletion_time"])
            actual_lifetime = actual_depletion - actual_restock
            error = actual_restock - projected_restock

            prior = prior_by_depth[depth]
            offset = _arrival_offset(strategy.arrival_policy, life_est, prior)
            window = _restock_window(
                prior,
                target=0.90,
                max_width=life_est,
            )

            # Mirror the website's conservative policy: never intentionally land
            # before the late side of the calibrated restock window.
            calibrated_arrival = projected_restock + offset
            if window:
                window_start = projected_restock + window[0]
                window_end = projected_restock + window[1]
                recommended_arrival = max(calibrated_arrival, window_end)
            else:
                window_start = window_end = None
                recommended_arrival = calibrated_arrival

            recommended_departure = (
                recommended_arrival - travel_seconds
                if travel_seconds is not None else None
            )
            actionable_from_anchor = (
                recommended_departure is not None
                and recommended_departure >= anchor_ts
            )

            arrival_hit = int(
                actual_restock <= recommended_arrival < actual_depletion
            )
            early = int(recommended_arrival < actual_restock)
            late = int(recommended_arrival >= actual_depletion)

            row = {
                "anchor_timestamp": anchor_ts,
                "depth": depth,
                "predicted_restock_timestamp": projected_restock,
                "actual_restock_timestamp": actual_restock,
                "actual_depletion_timestamp": actual_depletion,
                "actual_lifetime_seconds": actual_lifetime,
                "signed_error_seconds": error,
                "absolute_error_seconds": abs(error),
                "lifetime_estimate_seconds": life_est,
                "wait_estimate_seconds": wait_est,
                "arrival_offset_seconds": offset,
                "window_start_timestamp": window_start,
                "window_end_timestamp": window_end,
                "recommended_arrival_timestamp": recommended_arrival,
                "recommended_departure_timestamp": recommended_departure,
                "actionable_from_anchor": int(actionable_from_anchor),
                "arrival_hit": arrival_hit,
                "early_arrival": early,
                "late_arrival": late,
                "predicted_landing_fraction": (
                    (recommended_arrival - projected_restock) / life_est
                    if life_est > 0 else None
                ),
                "actual_landing_fraction": (
                    (recommended_arrival - actual_restock) / actual_lifetime
                    if actual_lifetime > 0 else None
                ),
                "arrival_margin_seconds": (
                    min(
                        recommended_arrival - actual_restock,
                        actual_depletion - recommended_arrival,
                    )
                    if arrival_hit else None
                ),
                "early_miss_seconds": (
                    actual_restock - recommended_arrival if early else 0.0
                ),
                "late_miss_seconds": (
                    recommended_arrival - actual_depletion if late else 0.0
                ),
            }
            rows.append(row)
            anchor_rows.append(row)

        # Only after scoring this issuance may it become history for later
        # issuances. This prevents the current target from leaking into itself.
        for row in anchor_rows:
            prior_by_depth[row["depth"]].append(row)

    return rows


def _summarize_depth(rows):
    if not rows:
        return None
    absolute = [r["absolute_error_seconds"] for r in rows]
    signed = [r["signed_error_seconds"] for r in rows]

    actionable = [r for r in rows if r["actionable_from_anchor"]]
    return {
        "n": len(rows),
        "actionable_n": len(actionable),
        "arrival_hit_rate": sum(r["arrival_hit"] for r in rows) / len(rows),
        "actionable_arrival_hit_rate": (
            sum(r["arrival_hit"] for r in actionable) / len(actionable)
            if actionable else None
        ),
        "early_rate": sum(r["early_arrival"] for r in rows) / len(rows),
        "late_rate": sum(r["late_arrival"] for r in rows) / len(rows),
        "median_absolute_error_seconds": statistics.median(absolute),
        "mean_absolute_error_seconds": statistics.mean(absolute),
        "p75_absolute_error_seconds": _percentile(absolute, 0.75),
        "p90_absolute_error_seconds": _percentile(absolute, 0.90),
        "p95_absolute_error_seconds": _percentile(absolute, 0.95),
        "signed_bias_seconds": statistics.median(signed),
        "median_predicted_landing_fraction": _median(
            r.get("predicted_landing_fraction") for r in rows
        ),
        "median_actual_landing_fraction_on_hits": _median(
            r.get("actual_landing_fraction") for r in rows if r["arrival_hit"]
        ),
        "median_arrival_margin_seconds": _median(
            r.get("arrival_margin_seconds") for r in rows if r["arrival_hit"]
        ),
        "median_early_miss_seconds": _median(
            r.get("early_miss_seconds") for r in rows if r["early_arrival"]
        ),
        "median_late_miss_seconds": _median(
            r.get("late_miss_seconds") for r in rows if r["late_arrival"]
        ),
    }


def _summarize(rows, max_depth):
    return {
        depth: _summarize_depth([r for r in rows if r["depth"] == depth])
        for depth in range(1, max_depth + 1)
    }


def _active_target_rows(rows):
    # For each frozen issuance, select exactly the earliest projection that was
    # still reachable from the observed depletion anchor using the real flight.
    grouped = {}
    for row in rows:
        grouped.setdefault(row["anchor_timestamp"], []).append(row)

    selected = []
    for anchor_rows in grouped.values():
        reachable = sorted(
            (r for r in anchor_rows if r["actionable_from_anchor"]),
            key=lambda r: r["depth"],
        )
        if reachable:
            selected.append(reachable[0])
    return selected


def tournament(
    country,
    item_name,
    max_depth=4,
    min_history=8,
    exclude_travel_day=True,
    arrival_policies=ARRIVAL_POLICIES,
):
    cycles, waits = _qualified_series(
        country,
        item_name,
        exclude_travel_day=exclude_travel_day,
    )
    travel_seconds = TRAVEL_SECONDS.get(country.lower())

    results = []
    for life_method, wait_method, arrival_policy in product(
        BASE_METHODS,
        BASE_METHODS,
        arrival_policies,
    ):
        strategy = Strategy(life_method, wait_method, arrival_policy)
        rows = _simulate_strategy(
            cycles,
            waits,
            strategy,
            travel_seconds=travel_seconds,
            max_depth=max_depth,
            min_history=min_history,
        )
        active_rows = _active_target_rows(rows)
        results.append({
            "strategy": strategy,
            "rows": rows,
            "by_depth": _summarize(rows, max_depth),
            "active_target": _summarize_depth(active_rows),
        })

    return {
        "country": country.lower(),
        "item_name": item_name,
        "valid_cycles": len(cycles),
        "travel_seconds": travel_seconds,
        "exclude_travel_day": exclude_travel_day,
        "strategies": results,
    }


def _rank_key(summary):
    if not summary:
        return (1, 1, float("inf"), float("inf"))
    actionable = summary.get("actionable_arrival_hit_rate")
    arrival = summary.get("arrival_hit_rate")
    return (
        -(actionable if actionable is not None else -1.0),
        -arrival,
        summary["median_absolute_error_seconds"],
        summary["p90_absolute_error_seconds"],
    )


def rank_for_depth(result, depth):
    ranked = []
    for entry in result["strategies"]:
        summary = entry["by_depth"].get(depth)
        if summary:
            ranked.append((entry["strategy"], summary))
    ranked.sort(key=lambda x: _rank_key(x[1]))
    return ranked


def rank_active_target(result):
    ranked = [
        (entry["strategy"], entry["active_target"])
        for entry in result["strategies"]
        if entry["active_target"]
    ]
    ranked.sort(key=lambda x: _rank_key(x[1]))
    return ranked


def _fmt_minutes(seconds):
    return "—" if seconds is None else f"{float(seconds) / 60.0:.1f}m"


def _fmt_rate(rate):
    return "—" if rate is None else f"{rate * 100:.1f}%"


def _line(strategy, s):
    return (
        f"  {strategy.name:<62} "
        f"n={s['n']:<4} act={s['actionable_n']:<4} "
        f"trip={_fmt_rate(s['actionable_arrival_hit_rate']):>6} "
        f"all={_fmt_rate(s['arrival_hit_rate']):>6} "
        f"early={_fmt_rate(s['early_rate']):>6} "
        f"late={_fmt_rate(s['late_rate']):>6} "
        f"MedAE={_fmt_minutes(s['median_absolute_error_seconds']):>7} "
        f"P90={_fmt_minutes(s['p90_absolute_error_seconds']):>7} "
        f"P95={_fmt_minutes(s['p95_absolute_error_seconds']):>7} "
        f"bias={_fmt_minutes(s['signed_bias_seconds']):>7} "
        f"landPred={('—' if s['median_predicted_landing_fraction'] is None else f\"{s['median_predicted_landing_fraction']*100:.0f}%\"):>4} "
        f"landActual={('—' if s['median_actual_landing_fraction_on_hits'] is None else f\"{s['median_actual_landing_fraction_on_hits']*100:.0f}%\"):>4} "
        f"margin={_fmt_minutes(s['median_arrival_margin_seconds']):>6}"
    )


def _print_worst(entry, depth, count=5):
    rows = [r for r in entry["rows"] if r["depth"] == depth]
    rows.sort(key=lambda r: r["absolute_error_seconds"], reverse=True)
    if not rows:
        return
    print(f"  Worst {min(count, len(rows))} frozen misses:")
    for r in rows[:count]:
        direction = "late actual" if r["signed_error_seconds"] > 0 else "early actual"
        print(
            f"    anchor={int(r['anchor_timestamp'])} "
            f"error={_fmt_minutes(r['absolute_error_seconds'])} {direction} "
            f"arrival={'HIT' if r['arrival_hit'] else 'MISS'}"
        )


def print_report(result, top=8, max_depth=4, worst=0):
    travel = (
        f"{result['travel_seconds'] / 60:.0f}m"
        if result["travel_seconds"] is not None else "unknown"
    )
    print(
        f"Projection-chain V2: {result['country'].upper()} / "
        f"{result['item_name']} ({result['valid_cycles']} valid cycles, "
        f"flight {travel})"
    )
    print(
        "Frozen walk-forward history only; original P2/P3/P4 never re-anchor. "
        f"Travel Day excluded={result['exclude_travel_day']}."
    )
    print(
        "trip = success among forecasts reachable from that historical anchor; "
        "all = all frozen forecasts at that depth."
    )
    print()

    active = rank_active_target(result)
    print("REAL-FLIGHT ACTIVE-TARGET SIMULATION")
    for strategy, s in active[:top]:
        print(_line(strategy, s))
    print()

    for depth in range(1, max_depth + 1):
        ranked = rank_for_depth(result, depth)
        print(f"DEPTH {depth}")
        if not ranked:
            print("  insufficient samples")
            print()
            continue
        for strategy, s in ranked[:top]:
            print(_line(strategy, s))
        if worst and ranked:
            winner = next(
                entry for entry in result["strategies"]
                if entry["strategy"] == ranked[0][0]
            )
            _print_worst(winner, depth, worst)
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Leak-free multi-horizon travel simulation and projection tournament."
    )
    parser.add_argument("country")
    parser.add_argument("item_name")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--min-history", type=int, default=8)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--worst", type=int, default=5)
    parser.add_argument(
        "--include-travel-day",
        action="store_true",
        help="Include the 2026 doubled-capacity Travel Day regime.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Test adaptive landing-position and midpoint policies for quicker iteration.",
    )
    args = parser.parse_args()

    policies = ("adaptive_fraction20", "adaptive20", "midpoint", "late65", "late75") if args.fast else ARRIVAL_POLICIES
    result = tournament(
        args.country,
        args.item_name,
        max_depth=max(1, args.depth),
        min_history=max(3, args.min_history),
        exclude_travel_day=not args.include_travel_day,
        arrival_policies=policies,
    )
    print_report(
        result,
        top=max(1, args.top),
        max_depth=max(1, args.depth),
        worst=max(0, args.worst),
    )


if __name__ == "__main__":
    main()
