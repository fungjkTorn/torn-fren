import statistics

from services.projection_engine_v4 import _percentile


def _key(row):
    return (int(row["anchor_timestamp"]), int(row["depth"]))


def _recent_rows(rows, before_anchor, depth, limit):
    usable = [
        r for r in rows
        if int(r["anchor_timestamp"]) < int(before_anchor)
        and int(r["depth"]) == int(depth)
    ]
    return usable[-limit:]


def _timing_score(rows):
    if not rows:
        return None
    errors = [
        abs(
            float(r["actual_restock_timestamp"])
            - float(r["raw_predicted_restock_timestamp"])
        )
        for r in rows
    ]
    signed = [
        float(r["actual_restock_timestamp"])
        - float(r["raw_predicted_restock_timestamp"])
        for r in rows
    ]
    return {
        "n": len(rows),
        "median_abs": statistics.median(errors),
        "p90_abs": _percentile(errors, 0.90),
        "bias_abs": abs(statistics.median(signed)),
    }


def adaptive_model_rows(point_models, max_depth=5, recent_window=8, min_history=5):
    """
    Build a frozen walk-forward meta-model.

    At every anchor/depth, select the point model using only that model's
    earlier realized errors at the same depth. The current/future outcome is
    never used for selection.
    """
    maps = []
    all_keys = set()

    for label, family, rows in point_models:
        mapping = {_key(r): r for r in rows}
        maps.append((label, family, rows, mapping))
        all_keys |= set(mapping)

    output = []
    for anchor, depth in sorted(all_keys):
        if depth > max_depth:
            continue

        candidates = []
        for label, family, rows, mapping in maps:
            current = mapping.get((anchor, depth))
            if current is None:
                continue
            recent = _recent_rows(rows, anchor, depth, recent_window)
            score = _timing_score(recent)
            if score is None or score["n"] < min_history:
                continue
            rank = (
                score["median_abs"],
                score["p90_abs"],
                score["bias_abs"],
            )
            candidates.append((rank, label, family, current, score))

        if not candidates:
            continue

        candidates.sort(key=lambda x: x[0])
        _, label, family, current, score = candidates[0]
        row = dict(current)
        row["forecast_mode"] = "adaptive_model_selector"
        row["adaptive_selected_model"] = label
        row["adaptive_selected_family"] = family
        row["adaptive_recent_window"] = recent_window
        row["adaptive_recent_n"] = score["n"]
        row["adaptive_recent_median_abs_error_seconds"] = score["median_abs"]
        row["adaptive_recent_p90_abs_error_seconds"] = score["p90_abs"]
        output.append(row)

    return output


def adaptive_ensemble_rows(
    point_models,
    max_depth=5,
    recent_window=8,
    min_history=5,
    top_n=3,
):
    """
    Same frozen walk-forward selector, but ensemble the best recent point
    models instead of trusting only one. This reduces winner instability.
    """
    maps = []
    all_keys = set()

    for label, family, rows in point_models:
        mapping = {_key(r): r for r in rows}
        maps.append((label, family, rows, mapping))
        all_keys |= set(mapping)

    output = []
    for anchor, depth in sorted(all_keys):
        if depth > max_depth:
            continue

        ranked = []
        for label, family, rows, mapping in maps:
            current = mapping.get((anchor, depth))
            if current is None:
                continue
            recent = _recent_rows(rows, anchor, depth, recent_window)
            score = _timing_score(recent)
            if score is None or score["n"] < min_history:
                continue
            ranked.append((
                (score["median_abs"], score["p90_abs"], score["bias_abs"]),
                label, family, current, score,
            ))

        if len(ranked) < 2:
            continue
        ranked.sort(key=lambda x: x[0])
        chosen = ranked[: min(top_n, len(ranked))]
        rs = [x[3] for x in chosen]

        row = dict(rs[0])
        row["raw_predicted_restock_timestamp"] = statistics.median(
            float(r["raw_predicted_restock_timestamp"]) for r in rs
        )
        row["lifetime_estimate_seconds"] = statistics.median(
            float(r["lifetime_estimate_seconds"]) for r in rs
        )
        row["wait_estimate_seconds"] = statistics.median(
            float(r["wait_estimate_seconds"]) for r in rs
        )
        row["wait_component_error_seconds"] = None
        row["lifetime_component_error_seconds"] = None
        row["direct_horizon_error_seconds"] = (
            float(row["actual_restock_timestamp"])
            - float(row["raw_predicted_restock_timestamp"])
        )
        row["forecast_mode"] = "adaptive_model_ensemble"
        row["adaptive_recent_window"] = recent_window
        row["adaptive_members"] = [x[1] for x in chosen]
        output.append(row)

    return output
