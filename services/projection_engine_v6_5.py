import itertools
import statistics

from services.projection_engine_v6_4 import active_declared_summary


def _active_fold_summaries(selected_by_depth, split_timestamp, folds=4):
    # Use anchor ranges implied by each candidate's rows. We evaluate the same
    # frozen combined policy over chronological training slices.
    anchors = set()
    for spec in selected_by_depth.values():
        rows = spec["candidate"]["evaluation"]["rows"]
        for r in rows:
            a = int(r["anchor_timestamp"])
            if a < split_timestamp:
                anchors.add(a)
    anchors = sorted(anchors)
    if len(anchors) < 40:
        return []

    fold_size = max(10, len(anchors) // (folds + 1))
    summaries = []
    for fold in range(1, folds + 1):
        start = fold * fold_size
        end = min(len(anchors), start + fold_size)
        if start >= end:
            continue
        lo, hi = anchors[start], anchors[end - 1]
        summaries.append(
            active_declared_summary_range(
                selected_by_depth, lo, hi
            )
        )
    return summaries


def active_declared_summary_range(selected_by_depth, lo, hi):
    maps = {}
    anchors = set()

    for depth, selected in selected_by_depth.items():
        evaluation = selected["candidate"]["evaluation"]
        mapping = {
            (int(r["anchor_timestamp"]), int(r["depth"])): r
            for r in evaluation["rows"]
        }
        maps[depth] = mapping
        for anchor, d in mapping:
            if d == depth and lo <= anchor <= hi:
                anchors.add(anchor)

    issued = []
    reachable_anchor_count = 0

    for anchor in sorted(anchors):
        any_reachable = False
        chosen = None
        for depth in sorted(selected_by_depth):
            spec = selected_by_depth[depth]
            row = maps[depth].get((anchor, depth))
            if not row:
                continue
            if row.get("actionable_from_anchor"):
                any_reachable = True

            threshold = float(spec["threshold"])
            prob = row.get("predicted_arrival_success")
            min_samples = int(row.get("calibration_min_samples") or 8)
            pool_n = int(row.get("calibration_pool_n") or 0)
            declared = (
                row.get("actionable_from_anchor")
                and prob is not None
                and float(prob) >= threshold
                and pool_n >= min_samples
            )
            if declared:
                chosen = row
                break

        if any_reachable:
            reachable_anchor_count += 1
        if chosen:
            issued.append(chosen)

    n = len(issued)
    hits = sum(int(r["arrival_hit"]) for r in issued)
    return {
        "reachable_anchors": reachable_anchor_count,
        "declared_n": n,
        "coverage": n / reachable_anchor_count if reachable_anchor_count else 0.0,
        "arrival_hit_rate": hits / n if n else None,
    }


def _policy_score(summary, target, folds):
    if not summary or not summary.get("declared_n"):
        return (-1, -1, -1, -1, -1)

    precision = summary.get("arrival_hit_rate") or 0.0
    coverage = summary.get("coverage") or 0.0
    n = summary.get("declared_n") or 0

    usable = [
        f for f in folds
        if f and f.get("declared_n", 0) >= 5
        and f.get("arrival_hit_rate") is not None
    ]
    fold_rates = [f["arrival_hit_rate"] for f in usable]
    fold_floor = min(fold_rates) if fold_rates else 0.0
    fold_median = statistics.median(fold_rates) if fold_rates else 0.0

    stable = (
        len(usable) >= 2
        and fold_median >= target
        and fold_floor >= max(0.0, target - 0.12)
    )
    meets = (
        n >= 15
        and precision >= target
        and coverage >= 0.05
        and stable
    )

    return (
        1 if meets else 0,
        fold_median,
        fold_floor,
        precision,
        coverage,
        n,
    )


def _top_options(candidates, depth, target, rank_fn, thresholds, limit=4):
    ranked = []
    for candidate in candidates:
        for threshold in thresholds:
            key = rank_fn(candidate, depth, threshold, target)
            ranked.append((key, candidate, threshold))
    ranked.sort(key=lambda x: x[0], reverse=True)

    out = [None]  # explicit abstention / disable this depth
    seen = set()
    for key, candidate, threshold in ranked:
        sig = (
            candidate["point_model"],
            candidate["family"],
            candidate["config"],
            float(threshold),
        )
        if sig in seen:
            continue
        seen.add(sig)
        out.append({
            "rank_key": key,
            "candidate": candidate,
            "threshold": threshold,
        })
        if len(out) >= limit + 1:
            break
    return out


def optimize_active_policy(
    candidates,
    split_timestamp,
    max_depth,
    target,
    rank_fn,
    thresholds,
    options_per_depth=4,
    passes=3,
):
    options = {
        d: _top_options(
            candidates, d, target, rank_fn, thresholds,
            limit=options_per_depth,
        )
        for d in range(1, max_depth + 1)
    }

    # Start with the strongest independent non-disabled option.
    selected = {}
    for d in range(1, max_depth + 1):
        if len(options[d]) > 1:
            selected[d] = options[d][1]

    def evaluate(policy):
        if not policy:
            return None, [], (-1, -1, -1, -1, -1)
        train = active_declared_summary(
            policy, split_timestamp, "train"
        )
        folds = _active_fold_summaries(
            policy, split_timestamp, folds=4
        )
        return train, folds, _policy_score(train, target, folds)

    train, folds, best_score = evaluate(selected)

    for _ in range(passes):
        changed = False
        for depth in range(1, max_depth + 1):
            local_best = (best_score, selected.get(depth), train, folds)
            for option in options[depth]:
                trial = dict(selected)
                if option is None:
                    trial.pop(depth, None)
                else:
                    trial[depth] = option
                t, f, score = evaluate(trial)
                if score > local_best[0]:
                    local_best = (score, option, t, f)

            score, option, t, f = local_best
            if score > best_score:
                changed = True
                best_score = score
                train, folds = t, f
                if option is None:
                    selected.pop(depth, None)
                else:
                    selected[depth] = option
        if not changed:
            break

    return {
        "selected_by_depth": selected,
        "train_active": train,
        "rolling_active_folds": folds,
        "score": best_score,
    }
