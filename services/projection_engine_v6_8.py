import math
import statistics

from services.projection_engine_v4 import build_item_context


METHODS = (
    "last1",
    "last2_mean",
    "last3_mean",
    "last3_median",
    "last5_mean",
    "last5_median",
)


def _valid(c):
    return (
        c.get("restock_time") is not None
        and c.get("depletion_time") is not None
        and float(c["depletion_time"]) > float(c["restock_time"])
        and not c.get("_excluded_regime")
        and c.get("_valid_for_training", True)
    )


def _estimate(values, method):
    if not values:
        return None
    if method == "last1":
        return float(values[-1])
    if method == "last2_mean":
        vals = values[-2:]
        return float(statistics.mean(vals))
    if method == "last3_mean":
        vals = values[-3:]
        return float(statistics.mean(vals))
    if method == "last3_median":
        vals = values[-3:]
        return float(statistics.median(vals))
    if method == "last5_mean":
        vals = values[-5:]
        return float(statistics.mean(vals))
    if method == "last5_median":
        vals = values[-5:]
        return float(statistics.median(vals))
    raise ValueError(method)


def _wilson_lower(hits, n, z=1.959963984540054):
    if n <= 0:
        return None
    p = hits / n
    den = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return (center - margin) / den


def literal_replay_rows(ctx, method="last1", max_depth=5):
    """
    Literal version of the user's heuristic.

    At completed cycle n:
      gap_n  = restock_n - depletion_(n-1)
      life_n = depletion_n - restock_n

    Estimate gap/life from the requested recent method, then recursively repeat:
      R_(n+1) = D_n + gap
      D_(n+1) = R_(n+1) + life
      R_(n+2) = D_(n+1) + gap
      ...

    Equivalently:
      predicted_R(n+d) = D_n + d*gap + (d-1)*life

    The recommended departure targets the predicted restock exactly:
      leave = predicted_R - travel_time

    We score the actual arrival time (predicted_R) directly against the true
    stock window. No residual calibration, confidence gating, or holdout tuning.
    """
    cycles = ctx.cycles
    rows = []

    for anchor_i, anchor in enumerate(cycles):
        if anchor_i < 1 or not _valid(anchor):
            continue

        known = [c for c in cycles[: anchor_i + 1] if _valid(c)]
        if len(known) < max(ctx.min_history, 2):
            continue

        gaps = []
        lives = []
        for j in range(1, anchor_i + 1):
            prev = cycles[j - 1]
            cur = cycles[j]
            if not (_valid(prev) and _valid(cur)):
                continue
            gap = float(cur["restock_time"]) - float(prev["depletion_time"])
            life = float(cur["depletion_time"]) - float(cur["restock_time"])
            if gap > 0 and life > 0:
                gaps.append(gap)
                lives.append(life)

        gap_est = _estimate(gaps, method)
        life_est = _estimate(lives, method)
        if not gap_est or not life_est or gap_est <= 0 or life_est <= 0:
            continue

        anchor_ts = float(anchor["depletion_time"])
        for depth in range(1, max_depth + 1):
            target_i = anchor_i + depth
            if target_i >= len(cycles):
                break
            target = cycles[target_i]
            if not _valid(target):
                continue

            predicted_r = anchor_ts + depth * gap_est + (depth - 1) * life_est
            predicted_d = predicted_r + life_est
            departure = (
                predicted_r - float(ctx.travel_seconds)
                if ctx.travel_seconds is not None else None
            )
            actionable = departure is not None and departure >= anchor_ts

            actual_r = float(target["restock_time"])
            actual_d = float(target["depletion_time"])
            hit = actual_r <= predicted_r < actual_d
            early = predicted_r < actual_r
            late = predicted_r >= actual_d

            rows.append({
                "anchor_timestamp": int(anchor_ts),
                "depth": depth,
                "method": method,
                "gap_estimate_seconds": gap_est,
                "lifetime_estimate_seconds": life_est,
                "predicted_restock_timestamp": predicted_r,
                "predicted_depletion_timestamp": predicted_d,
                "recommended_departure_timestamp": departure,
                "recommended_arrival_timestamp": predicted_r,
                "actionable_from_anchor": int(actionable),
                "actual_restock_timestamp": actual_r,
                "actual_depletion_timestamp": actual_d,
                "arrival_hit": int(hit),
                "early_arrival": int(early),
                "late_arrival": int(late),
                "restock_error_seconds": actual_r - predicted_r,
                "actual_lifetime_seconds": actual_d - actual_r,
            })
    return rows


def _period_rows(ctx, rows, period):
    if ctx.split_timestamp is None:
        return []
    if period == "train":
        return [r for r in rows if r["anchor_timestamp"] < ctx.split_timestamp]
    if period == "holdout":
        return [r for r in rows if r["anchor_timestamp"] >= ctx.split_timestamp]
    raise ValueError(period)


def summarize(rows):
    actionable = [r for r in rows if r["actionable_from_anchor"]]
    n = len(actionable)
    hits = sum(r["arrival_hit"] for r in actionable)
    if n == 0:
        return {
            "rows_n": len(rows), "actionable_n": 0, "hit_rate": None,
            "wilson_lower_95": None, "early_rate": None, "late_rate": None,
            "median_abs_restock_error_seconds": None,
        }
    return {
        "rows_n": len(rows),
        "actionable_n": n,
        "hit_rate": hits / n,
        "wilson_lower_95": _wilson_lower(hits, n),
        "early_rate": sum(r["early_arrival"] for r in actionable) / n,
        "late_rate": sum(r["late_arrival"] for r in actionable) / n,
        "median_abs_restock_error_seconds": statistics.median(
            abs(float(r["restock_error_seconds"])) for r in actionable
        ),
    }


def active_earliest(rows):
    grouped = {}
    for r in rows:
        grouped.setdefault(r["anchor_timestamp"], []).append(r)
    out = []
    for group in grouped.values():
        reachable = sorted(
            (r for r in group if r["actionable_from_anchor"]),
            key=lambda r: r["depth"],
        )
        if reachable:
            out.append(reachable[0])
    return out


def evaluate_method(ctx, method, max_depth=5):
    rows = literal_replay_rows(ctx, method=method, max_depth=max_depth)
    report = {"method": method, "train_by_depth": {}, "holdout_by_depth": {}}
    for period in ("train", "holdout"):
        subset = _period_rows(ctx, rows, period)
        report[f"{period}_active"] = summarize(active_earliest(subset))
        for depth in range(1, max_depth + 1):
            report[f"{period}_by_depth"][str(depth)] = summarize(
                [r for r in subset if r["depth"] == depth]
            )
    return report


def build_context(country, item_name, max_depth=5, min_history=8):
    return build_item_context(
        country.lower(), item_name, max_depth=max_depth, min_history=min_history
    )
