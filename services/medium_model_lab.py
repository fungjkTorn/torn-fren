import math
import sqlite3
import statistics
from dataclasses import dataclass

from services.history_service import DB_PATH
from services.cycle_feature_lab import build_cycle_feature_rows, _percentile, _tertile_prediction


@dataclass
class AdvancedModelResult:
    name: str
    predictions: int
    median_absolute_error_seconds: float | None
    mean_absolute_error_seconds: float | None
    p90_absolute_error_seconds: float | None
    signed_bias_seconds: float | None


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _weighted_recent(values, decay=0.72, limit=10):
    vals = list(values[-limit:])
    if not vals:
        return None
    weights = [decay ** (len(vals) - 1 - i) for i in range(len(vals))]
    return sum(v * w for v, w in zip(vals, weights)) / sum(weights)


def _solve_linear_system(a, b):
    """Small Gaussian-elimination solver; avoids adding numpy/sklearn dependencies."""
    n = len(b)
    m = [list(map(float, a[i])) + [float(b[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-10:
            return None
        if pivot != col:
            m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col]
        for j in range(col, n + 1):
            m[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col]
            if factor == 0:
                continue
            for j in range(col, n + 1):
                m[r][j] -= factor * m[col][j]
    return [m[i][n] for i in range(n)]


def _ridge_prediction(training_rows, current_row, feature_keys, ridge_lambda=1.0, residual_base_key=None):
    if len(training_rows) < 12:
        return None

    prepared = []
    stats = {}
    for key in feature_keys:
        vals = [r.get(key) for r in training_rows if r.get(key) is not None]
        if len(vals) < max(8, len(training_rows) // 2):
            continue
        med = statistics.median(vals)
        std = statistics.pstdev(vals)
        if std <= 1e-9:
            continue
        stats[key] = (med, std)

    if len(stats) < 2:
        return None

    active_keys = list(stats)
    for row in training_rows:
        x = [1.0]
        for key in active_keys:
            med, std = stats[key]
            value = row.get(key)
            if value is None:
                value = med
            x.append((value - med) / std)
        target = row["target_wait_seconds"]
        if residual_base_key:
            base = row.get(residual_base_key)
            if base is None:
                continue
            target -= base
        prepared.append((x, target))

    if len(prepared) < max(10, len(active_keys) + 4):
        return None

    p = len(active_keys) + 1
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for x, y in prepared:
        for i in range(p):
            xty[i] += x[i] * y
            for j in range(p):
                xtx[i][j] += x[i] * x[j]
    # Do not regularize intercept.
    for i in range(1, p):
        xtx[i][i] += ridge_lambda

    coeff = _solve_linear_system(xtx, xty)
    if coeff is None:
        return None

    current_x = [1.0]
    for key in active_keys:
        med, std = stats[key]
        value = current_row.get(key)
        if value is None:
            value = med
        current_x.append((value - med) / std)
    estimate = sum(c * x for c, x in zip(coeff, current_x))
    if residual_base_key:
        base = current_row.get(residual_base_key)
        if base is None:
            return None
        estimate += base
    return estimate


def _bucket2_prediction(training_rows, current_row, key1, key2):
    pairs = [r for r in training_rows if r.get(key1) is not None and r.get(key2) is not None]
    if len(pairs) < 18 or current_row.get(key1) is None or current_row.get(key2) is None:
        return None
    vals1 = sorted(r[key1] for r in pairs)
    vals2 = sorted(r[key2] for r in pairs)
    q11, q12 = _percentile(vals1, 1/3), _percentile(vals1, 2/3)
    q21, q22 = _percentile(vals2, 1/3), _percentile(vals2, 2/3)

    def bucket(v, q1, q2):
        return 0 if v <= q1 else 1 if v <= q2 else 2

    b1 = bucket(current_row[key1], q11, q12)
    b2 = bucket(current_row[key2], q21, q22)
    targets = [
        r["target_wait_seconds"] for r in pairs
        if bucket(r[key1], q11, q12) == b1 and bucket(r[key2], q21, q22) == b2
    ]
    return statistics.median(targets) if len(targets) >= 3 else None


def _tree_leaf_prediction(training_rows, current_row, feature_keys, max_depth=2, min_leaf=5):
    """Tiny regression tree built fresh from historical rows only."""
    usable_keys = []
    for key in feature_keys:
        vals = [r.get(key) for r in training_rows if r.get(key) is not None]
        if len(vals) >= max(10, min_leaf * 2) and len(set(vals)) >= 4 and current_row.get(key) is not None:
            usable_keys.append(key)
    if not usable_keys:
        return None

    def node_predict(rows, depth):
        if len(rows) < min_leaf * 2 or depth >= max_depth:
            return statistics.median(r["target_wait_seconds"] for r in rows)
        best = None
        parent_sse = sum((r["target_wait_seconds"] - statistics.mean(x["target_wait_seconds"] for x in rows)) ** 2 for r in rows)
        for key in usable_keys:
            vals = sorted({r[key] for r in rows if r.get(key) is not None})
            if len(vals) < 4:
                continue
            # Quantile-ish candidate thresholds keep the tree small and stable.
            indexes = sorted(set([len(vals)//4, len(vals)//3, len(vals)//2, (2*len(vals))//3, (3*len(vals))//4]))
            for idx in indexes:
                if idx <= 0 or idx >= len(vals):
                    continue
                threshold = (vals[idx-1] + vals[idx]) / 2
                left = [r for r in rows if r.get(key) is not None and r[key] <= threshold]
                right = [r for r in rows if r.get(key) is not None and r[key] > threshold]
                if len(left) < min_leaf or len(right) < min_leaf:
                    continue
                sse = 0.0
                for group in (left, right):
                    mean = statistics.mean(r["target_wait_seconds"] for r in group)
                    sse += sum((r["target_wait_seconds"] - mean) ** 2 for r in group)
                gain = parent_sse - sse
                if best is None or gain > best[0]:
                    best = (gain, key, threshold, left, right)
        if best is None or best[0] <= 0:
            return statistics.median(r["target_wait_seconds"] for r in rows)
        _, key, threshold, left, right = best
        chosen = left if current_row[key] <= threshold else right
        return node_predict(chosen, depth + 1)

    return node_predict(training_rows, 0)


def walk_forward_advanced_models(feature_rows, min_train=15):
    records = {}
    core = [
        "prev_peak_quantity",
        "prev_lifetime_seconds",
        "prev_depletion_rate_per_minute",
        "previous_wait_seconds",
        "recent3_wait_median_seconds",
        "recent5_wait_median_seconds",
    ]
    expanded = core + [
        "peak_vs_recent5_ratio",
        "lifetime_vs_recent5_ratio",
        "depletion_hour_sin",
        "depletion_hour_cos",
    ]
    tree_features = [
        "prev_peak_quantity",
        "prev_lifetime_seconds",
        "prev_depletion_rate_per_minute",
        "previous_wait_seconds",
        "recent3_wait_median_seconds",
        "peak_vs_recent5_ratio",
        "depletion_hour_sin",
        "depletion_hour_cos",
    ]

    for i, current in enumerate(feature_rows):
        training = feature_rows[:i]
        if len(training) < min_train:
            continue
        waits = [r["target_wait_seconds"] for r in training]
        estimates = {
            "baseline_all_median": statistics.median(waits),
            "recent10_median": statistics.median(waits[-10:]),
            "weighted_recent10": _weighted_recent(waits),
            "peak_tertile_median": _tertile_prediction(training, "prev_peak_quantity", current),
            "peak_x_prevwait_bucket": _bucket2_prediction(training, current, "prev_peak_quantity", "previous_wait_seconds"),
            "peak_x_lifetime_bucket": _bucket2_prediction(training, current, "prev_peak_quantity", "prev_lifetime_seconds"),
            "ridge_core_l1": _ridge_prediction(training, current, core, ridge_lambda=1.0),
            "ridge_core_l10": _ridge_prediction(training, current, core, ridge_lambda=10.0),
            "ridge_expanded_l10": _ridge_prediction(training, current, expanded, ridge_lambda=10.0),
            "ridge_residual_recent5": _ridge_prediction(training, current, expanded, ridge_lambda=10.0, residual_base_key="recent5_wait_median_seconds"),
            "tree_depth2": _tree_leaf_prediction(training, current, tree_features, max_depth=2, min_leaf=5),
        }
        for name, estimate in estimates.items():
            if estimate is None or not math.isfinite(estimate) or estimate <= 0:
                continue
            error = current["target_wait_seconds"] - estimate
            records.setdefault(name, []).append({
                "anchor_timestamp": current.get("anchor_timestamp"),
                "actual_restock_timestamp": current.get("actual_restock_timestamp"),
                "estimate_seconds": estimate,
                "predicted_restock_timestamp": (
                    current.get("anchor_timestamp") + estimate
                    if current.get("anchor_timestamp") is not None else None
                ),
                "actual_seconds": current["target_wait_seconds"],
                "signed_error_seconds": error,
                "absolute_error_seconds": abs(error),
            })

    summaries = []
    for name, rows in records.items():
        if not rows:
            continue
        absolute = [r["absolute_error_seconds"] for r in rows]
        signed = [r["signed_error_seconds"] for r in rows]
        summaries.append(AdvancedModelResult(
            name=name,
            predictions=len(rows),
            median_absolute_error_seconds=statistics.median(absolute),
            mean_absolute_error_seconds=statistics.mean(absolute),
            p90_absolute_error_seconds=_percentile(absolute, 0.90),
            signed_bias_seconds=statistics.median(signed),
        ))
    summaries.sort(key=lambda r: (
        float("inf") if r.median_absolute_error_seconds is None else r.median_absolute_error_seconds,
        float("inf") if r.p90_absolute_error_seconds is None else r.p90_absolute_error_seconds,
        r.name,
    ))
    return summaries, records


def _behavior_class(median_wait):
    if median_wait is None:
        return "unknown"
    minutes = median_wait / 60
    if minutes <= 30:
        return "rapid"
    if minutes <= 120:
        return "short"
    if minutes <= 360:
        return "medium"
    if minutes <= 720:
        return "long"
    return "very_long"


def analyze_advanced_item(country, item_name, min_train=15):
    rows, bounces = build_cycle_feature_rows(country, item_name)
    waits = [r["target_wait_seconds"] for r in rows]
    median_wait = statistics.median(waits) if waits else None
    models, records = walk_forward_advanced_models(rows, min_train=min_train)
    return {
        "country": country,
        "item_name": item_name,
        "samples": len(rows),
        "median_wait_seconds": median_wait,
        "behavior_class": _behavior_class(median_wait),
        "provider_bounces_suppressed": len(bounces),
        "models": models,
        "records_by_model": records,
    }


def list_tracked_items(min_rows=20):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT country, item_name, COUNT(*)
            FROM stock_history
            GROUP BY country, item_name
            HAVING COUNT(*) >= ?
            ORDER BY country, item_name
            """,
            (min_rows,),
        ).fetchall()


def run_short_medium_tournament(min_samples=15, min_predictions=12, min_rows=20):
    items = []
    class_wins = {"short": {}, "medium": {}}
    for country, item_name, row_count in list_tracked_items(min_rows=min_rows):
        result = analyze_advanced_item(country, item_name, min_train=min_samples)
        if result["behavior_class"] not in ("short", "medium"):
            continue
        eligible = [m for m in result["models"] if m.predictions >= min_predictions]
        winner = eligible[0] if eligible else None
        result["winner"] = winner
        result["row_count"] = row_count
        items.append(result)
        if winner:
            wins = class_wins[result["behavior_class"]]
            wins[winner.name] = wins.get(winner.name, 0) + 1
    return {"items": items, "class_wins": class_wins}
