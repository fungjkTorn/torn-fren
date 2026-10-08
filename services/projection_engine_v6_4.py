import statistics


def _row_map(evaluation):
    return {
        (int(r["anchor_timestamp"]), int(r["depth"])): r
        for r in evaluation["rows"]
    }


def active_declared_summary(selected_by_depth, split_timestamp, period):
    """
    Score what the product would actually tell the player to fly for.

    Each depth's model/config/threshold must have been selected using training
    data only. At each historical anchor choose the earliest depth that is:
      1) reachable from that anchor, and
      2) confident enough to declare.
    """
    maps = {}
    anchors = set()

    for depth, selected in selected_by_depth.items():
        evaluation = selected["candidate"]["evaluation"]
        mapping = _row_map(evaluation)
        maps[depth] = mapping
        for anchor, d in mapping:
            if d == depth:
                if period == "train" and anchor < split_timestamp:
                    anchors.add(anchor)
                elif period == "holdout" and anchor >= split_timestamp:
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
                chosen = dict(row)
                chosen["selected_depth"] = depth
                chosen["declaration_threshold"] = threshold
                chosen["selected_point_model"] = spec["candidate"]["point_model"]
                chosen["selected_family"] = spec["candidate"]["family"]
                break

        if any_reachable:
            reachable_anchor_count += 1
        if chosen:
            issued.append(chosen)

    n = len(issued)
    hits = sum(int(r["arrival_hit"]) for r in issued)
    early = sum(int(r["early_arrival"]) for r in issued)
    late = sum(int(r["late_arrival"]) for r in issued)

    depth_counts = {}
    for r in issued:
        d = int(r["selected_depth"])
        depth_counts[d] = depth_counts.get(d, 0) + 1

    return {
        "reachable_anchors": reachable_anchor_count,
        "declared_n": n,
        "coverage": (
            n / reachable_anchor_count if reachable_anchor_count else 0.0
        ),
        "arrival_hit_rate": hits / n if n else None,
        "early_rate": early / n if n else None,
        "late_rate": late / n if n else None,
        "depth_counts": depth_counts,
    }


def choose_depth_candidate(candidates, depth, target, rank_fn, thresholds):
    ranked = []
    for candidate in candidates:
        for threshold in thresholds:
            key = rank_fn(candidate, depth, threshold, target)
            ranked.append((key, candidate, threshold))
    ranked.sort(key=lambda x: x[0], reverse=True)
    if not ranked:
        return None
    key, candidate, threshold = ranked[0]
    return {
        "rank_key": key,
        "candidate": candidate,
        "threshold": threshold,
    }
