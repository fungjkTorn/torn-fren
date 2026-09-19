import math
import statistics
from dataclasses import dataclass

from services.history_service import (
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)


@dataclass
class FeatureModelResult:
    name: str
    predictions: int
    median_absolute_error_seconds: float | None
    mean_absolute_error_seconds: float | None
    p90_absolute_error_seconds: float | None
    signed_bias_seconds: float | None


def _percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _median_or_none(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _mean_or_none(values):
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _rank(values):
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        average_rank = (i + j - 1) / 2 + 1
        for k in range(i, j):
            ranks[indexed[k][0]] = average_rank
        i = j
    return ranks


def _pearson(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    if denom == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def _spearman(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    return _pearson(_rank(xs), _rank(ys))


def build_cycle_feature_rows(country: str, item_name: str):
    """
    Build one row per VALID depletion -> next qualified restock wait.

    Every feature is information that was already known at the moment the prior
    cycle depleted. The target is the subsequent zero->restock wait. That keeps
    the dataset safe for walk-forward prediction experiments.
    """
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, bounces = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    if not rows:
        return [], bounces

    cycles, _active, wait_samples = _build_validated_cycles(rows)
    completed = [c for c in cycles if c.get("complete")]
    normal = [c for c in completed if not c.get("tiny_restock")]

    cycle_by_depletion = {c.get("depletion_time"): c for c in normal if c.get("depletion_time")}
    cycle_by_restock = {c.get("restock_time"): c for c in normal if c.get("restock_time")}

    valid_wait_by_to = {
        s["to_restock"]: s
        for s in wait_samples
        if s.get("valid")
    }

    feature_rows = []
    prior_valid_waits = []
    prior_valid_lifetimes = []
    prior_valid_peaks = []

    for sample in sorted(valid_wait_by_to.values(), key=lambda s: s["to_restock"]):
        previous = cycle_by_depletion.get(sample["from_depletion"])
        incoming = cycle_by_restock.get(sample["to_restock"])
        if previous is None or incoming is None:
            continue

        lifetime = previous.get("lifetime_seconds")
        peak = previous.get("peak_quantity")
        first_seen = previous.get("first_seen_quantity")
        peak_delay = None
        if previous.get("peak_time") and previous.get("restock_time"):
            peak_delay = previous["peak_time"] - previous["restock_time"]

        depletion_rate_per_minute = None
        if lifetime and lifetime > 0 and peak is not None:
            depletion_rate_per_minute = peak / (lifetime / 60)

        depletion_ts = previous["depletion_time"]
        depletion_hour = (depletion_ts % 86400) / 3600
        hour_angle = 2 * math.pi * depletion_hour / 24

        recent5_peak_median = _median_or_none(prior_valid_peaks[-5:])
        recent5_lifetime_median = _median_or_none(prior_valid_lifetimes[-5:])

        feature_rows.append({
            "anchor_timestamp": depletion_ts,
            "actual_restock_timestamp": sample["to_restock"],
            "target_wait_seconds": sample["seconds"],
            "prev_peak_quantity": peak,
            "prev_first_seen_quantity": first_seen,
            "prev_lifetime_seconds": lifetime,
            "prev_peak_delay_seconds": peak_delay,
            "prev_depletion_rate_per_minute": depletion_rate_per_minute,
            "previous_wait_seconds": prior_valid_waits[-1] if prior_valid_waits else None,
            "recent3_wait_median_seconds": _median_or_none(prior_valid_waits[-3:]),
            "recent5_wait_median_seconds": _median_or_none(prior_valid_waits[-5:]),
            "recent10_wait_median_seconds": _median_or_none(prior_valid_waits[-10:]),
            "recent3_lifetime_median_seconds": _median_or_none(prior_valid_lifetimes[-3:]),
            "recent5_lifetime_median_seconds": recent5_lifetime_median,
            "peak_vs_recent5_ratio": (peak / recent5_peak_median) if peak and recent5_peak_median else None,
            "lifetime_vs_recent5_ratio": (lifetime / recent5_lifetime_median) if lifetime and recent5_lifetime_median else None,
            "depletion_hour_sin": math.sin(hour_angle),
            "depletion_hour_cos": math.cos(hour_angle),
            "depletion_weekday": int((depletion_ts // 86400 + 3) % 7),  # Unix epoch was Thursday.
            "bridged_tiny_restock_count": sample.get("bridged_tiny_restock_count", 0),
        })

        prior_valid_waits.append(sample["seconds"])
        if lifetime is not None and previous.get("valid_lifetime"):
            prior_valid_lifetimes.append(lifetime)
        if peak is not None and previous.get("valid_lifetime"):
            prior_valid_peaks.append(peak)

    return feature_rows, bounces


def feature_correlations(feature_rows):
    target_key = "target_wait_seconds"
    feature_keys = [
        "prev_peak_quantity",
        "prev_first_seen_quantity",
        "prev_lifetime_seconds",
        "prev_peak_delay_seconds",
        "prev_depletion_rate_per_minute",
        "previous_wait_seconds",
        "recent3_wait_median_seconds",
        "recent5_wait_median_seconds",
        "recent10_wait_median_seconds",
        "recent3_lifetime_median_seconds",
        "recent5_lifetime_median_seconds",
        "peak_vs_recent5_ratio",
        "lifetime_vs_recent5_ratio",
        "depletion_hour_sin",
        "depletion_hour_cos",
    ]
    output = []
    for key in feature_keys:
        pairs = [
            (row.get(key), row.get(target_key))
            for row in feature_rows
            if row.get(key) is not None and row.get(target_key) is not None
        ]
        if len(pairs) < 5:
            continue
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        output.append({
            "feature": key,
            "n": len(pairs),
            "pearson": _pearson(xs, ys),
            "spearman": _spearman(xs, ys),
        })
    output.sort(key=lambda row: abs(row["spearman"] or 0), reverse=True)
    return output


def _kmeans_1d(values, k, iterations=100):
    ordered = sorted(values)
    if not ordered or k < 1:
        return None
    if k == 1:
        centers = [statistics.mean(ordered)]
    else:
        centers = [ordered[round(i * (len(ordered) - 1) / (k - 1))] for i in range(k)]

    assignments = [0] * len(values)
    for _ in range(iterations):
        new_assignments = [min(range(k), key=lambda j: abs(v - centers[j])) for v in values]
        new_centers = []
        for j in range(k):
            members = [v for v, a in zip(values, new_assignments) if a == j]
            new_centers.append(statistics.mean(members) if members else centers[j])
        if new_assignments == assignments and all(abs(a - b) < 1e-9 for a, b in zip(new_centers, centers)):
            break
        assignments = new_assignments
        centers = new_centers

    clusters = []
    for j in range(k):
        members = sorted(v for v, a in zip(values, assignments) if a == j)
        if not members:
            return None
        clusters.append({
            "center": statistics.mean(members),
            "count": len(members),
            "stddev": statistics.pstdev(members) if len(members) > 1 else 0,
            "min": min(members),
            "max": max(members),
        })
    clusters.sort(key=lambda c: c["center"])
    sse = sum((v - centers[a]) ** 2 for v, a in zip(values, assignments))
    return {"k": k, "clusters": clusters, "sse": sse}


def _silhouette_1d(values, fit):
    if not fit or fit["k"] < 2:
        return None
    centers = [c["center"] for c in fit["clusters"]]
    assignments = [min(range(len(centers)), key=lambda j: abs(v - centers[j])) for v in values]
    scores = []
    for i, value in enumerate(values):
        same = [abs(value - other) for j, other in enumerate(values) if j != i and assignments[j] == assignments[i]]
        a = statistics.mean(same) if same else 0
        other_means = []
        for cluster_index in range(len(centers)):
            if cluster_index == assignments[i]:
                continue
            members = [abs(value - other) for j, other in enumerate(values) if assignments[j] == cluster_index]
            if members:
                other_means.append(statistics.mean(members))
        b = min(other_means) if other_means else 0
        denom = max(a, b)
        scores.append((b - a) / denom if denom else 0)
    return statistics.mean(scores) if scores else None


def wait_cluster_analysis(feature_rows, max_k=4):
    raw_values = [row["target_wait_seconds"] for row in feature_rows]
    n = len(raw_values)
    if n < 6:
        return {"selected_k": 1, "clusters": [], "reason": "insufficient samples", "outliers_ignored": 0}

    # Clustering is diagnostic only. Remove extreme isolated waits with a robust
    # MAD fence so a provider blip or rare drought cannot force the cluster fit.
    median = statistics.median(raw_values)
    mad = statistics.median(abs(v - median) for v in raw_values)
    fence = max(60, mad * 6)
    values = [v for v in raw_values if abs(v - median) <= fence]
    outliers_ignored = n - len(values)

    if len(values) < 6:
        values = raw_values
        outliers_ignored = 0

    candidates = []
    max_allowed = min(max_k, max(2, len(values) // 3))
    min_cluster = max(3, math.ceil(len(values) * 0.08))
    for k in range(2, max_allowed + 1):
        fit = _kmeans_1d(values, k)
        if fit is None or any(c["count"] < min_cluster for c in fit["clusters"]):
            continue
        fit["silhouette"] = _silhouette_1d(values, fit)
        candidates.append(fit)

    if not candidates:
        one = _kmeans_1d(values, 1)
        return {
            "selected_k": 1,
            "clusters": one["clusters"] if one else [],
            "reason": "no stable multi-cluster fit",
            "outliers_ignored": outliers_ignored,
        }

    selected = max(candidates, key=lambda c: c.get("silhouette") or -1)
    # Below ~0.55, separation is weak enough that one broad regime is the safer
    # interpretation. Rounded modes are still printed separately for quantization.
    if (selected.get("silhouette") or 0) < 0.55:
        one = _kmeans_1d(values, 1)
        return {
            "selected_k": 1,
            "clusters": one["clusters"] if one else [],
            "reason": "cluster separation weak",
            "outliers_ignored": outliers_ignored,
            "best_silhouette": selected.get("silhouette"),
        }

    return {
        "selected_k": selected["k"],
        "clusters": selected["clusters"],
        "silhouette": selected.get("silhouette"),
        "outliers_ignored": outliers_ignored,
        "candidates": candidates,
    }

def rounded_wait_modes(feature_rows, bucket_minutes=None):
    waits = [row["target_wait_seconds"] for row in feature_rows]
    if not waits:
        return []
    median_minutes = statistics.median(waits) / 60
    if bucket_minutes is None:
        bucket_minutes = 1 if median_minutes <= 30 else 5 if median_minutes <= 360 else 15
    bucket_seconds = bucket_minutes * 60
    counts = {}
    for value in waits:
        bucket = round(value / bucket_seconds) * bucket_seconds
        counts[bucket] = counts.get(bucket, 0) + 1
    return sorted(
        ({"seconds": sec, "count": count, "bucket_minutes": bucket_minutes} for sec, count in counts.items()),
        key=lambda row: (-row["count"], row["seconds"]),
    )


def _tertile_prediction(training_rows, feature_key, current_row):
    pairs = [(r.get(feature_key), r["target_wait_seconds"]) for r in training_rows if r.get(feature_key) is not None]
    value = current_row.get(feature_key)
    if value is None or len(pairs) < 9:
        return None
    feature_values = sorted(v for v, _ in pairs)
    q1 = _percentile(feature_values, 1 / 3)
    q2 = _percentile(feature_values, 2 / 3)
    if value <= q1:
        bucket = [target for fv, target in pairs if fv <= q1]
    elif value <= q2:
        bucket = [target for fv, target in pairs if q1 < fv <= q2]
    else:
        bucket = [target for fv, target in pairs if fv > q2]
    return statistics.median(bucket) if len(bucket) >= 3 else None


def _knn_prediction(training_rows, current_row, feature_keys, k):
    usable = []
    for key in feature_keys:
        vals = [r.get(key) for r in training_rows if r.get(key) is not None]
        if current_row.get(key) is None or len(vals) < 5:
            continue
        std = statistics.pstdev(vals)
        if std > 0:
            usable.append((key, statistics.mean(vals), std))
    if len(usable) < 2:
        return None

    distances = []
    for row in training_rows:
        pieces = []
        for key, mean, std in usable:
            if row.get(key) is None:
                break
            pieces.append((row[key] - current_row[key]) / std)
        else:
            distance = math.sqrt(sum(v * v for v in pieces) / len(pieces))
            distances.append((distance, row["target_wait_seconds"]))
    if len(distances) < max(3, k):
        return None
    nearest = [target for _, target in sorted(distances)[:k]]
    return statistics.median(nearest)


def walk_forward_feature_models(feature_rows, min_train=10):
    records = {}
    core_features = [
        "prev_lifetime_seconds",
        "prev_peak_quantity",
        "prev_depletion_rate_per_minute",
        "previous_wait_seconds",
        "recent3_wait_median_seconds",
    ]

    for i, current in enumerate(feature_rows):
        training = feature_rows[:i]
        if len(training) < min_train:
            continue

        estimates = {
            "baseline_all_median": statistics.median(r["target_wait_seconds"] for r in training),
            "lifetime_tertile_median": _tertile_prediction(training, "prev_lifetime_seconds", current),
            "peak_tertile_median": _tertile_prediction(training, "prev_peak_quantity", current),
            "knn_core_5": _knn_prediction(training, current, core_features, 5),
            "knn_core_10": _knn_prediction(training, current, core_features, 10),
        }

        for name, estimate in estimates.items():
            if estimate is None:
                continue
            error = current["target_wait_seconds"] - estimate
            records.setdefault(name, []).append({
                "actual_restock_timestamp": current["actual_restock_timestamp"],
                "estimate_seconds": estimate,
                "actual_seconds": current["target_wait_seconds"],
                "signed_error_seconds": error,
                "absolute_error_seconds": abs(error),
            })

    summaries = []
    for name, model_records in records.items():
        absolute = [r["absolute_error_seconds"] for r in model_records]
        signed = [r["signed_error_seconds"] for r in model_records]
        summaries.append(FeatureModelResult(
            name=name,
            predictions=len(model_records),
            median_absolute_error_seconds=statistics.median(absolute) if absolute else None,
            mean_absolute_error_seconds=statistics.mean(absolute) if absolute else None,
            p90_absolute_error_seconds=_percentile(absolute, 0.90),
            signed_bias_seconds=statistics.median(signed) if signed else None,
        ))
    summaries.sort(key=lambda r: (float("inf") if r.median_absolute_error_seconds is None else r.median_absolute_error_seconds, r.name))
    return summaries, records



@dataclass
class ClusterClassifierResult:
    name: str
    predictions: int
    cluster_accuracy: float | None
    median_absolute_error_seconds: float | None
    mean_absolute_error_seconds: float | None
    p90_absolute_error_seconds: float | None
    signed_bias_seconds: float | None


def _fit_training_clusters(training_rows, max_k=4):
    """Fit wait clusters using ONLY training rows for walk-forward safety."""
    if len(training_rows) < 12:
        return None
    analysis = wait_cluster_analysis(training_rows, max_k=max_k)
    clusters = analysis.get("clusters") or []
    if analysis.get("selected_k", 1) < 2 or len(clusters) < 2:
        return None
    return analysis


def _nearest_cluster_index(wait_seconds, centers):
    return min(range(len(centers)), key=lambda idx: abs(wait_seconds - centers[idx]))


def _cluster_training_labels(training_rows, cluster_analysis):
    centers = [c["center"] for c in cluster_analysis["clusters"]]
    return [
        _nearest_cluster_index(row["target_wait_seconds"], centers)
        for row in training_rows
    ], centers


def _cluster_feature_centroid_prediction(training_rows, current_row, cluster_analysis, feature_keys):
    """
    Predict a timing regime by comparing the current cycle's known features to
    historical feature centroids for each wait cluster. No target information
    from the current row is used.
    """
    labels, centers = _cluster_training_labels(training_rows, cluster_analysis)
    usable = []
    for key in feature_keys:
        current = current_row.get(key)
        vals = [r.get(key) for r in training_rows if r.get(key) is not None]
        if current is None or len(vals) < 8:
            continue
        std = statistics.pstdev(vals)
        if std > 0:
            usable.append((key, std))
    if len(usable) < 2:
        return None

    scores = []
    for cluster_idx in range(len(centers)):
        members = [r for r, label in zip(training_rows, labels) if label == cluster_idx]
        if len(members) < 3:
            continue
        pieces = []
        for key, std in usable:
            member_vals = [r.get(key) for r in members if r.get(key) is not None]
            if len(member_vals) < 3:
                continue
            centroid = statistics.median(member_vals)
            pieces.append(((current_row[key] - centroid) / std) ** 2)
        if pieces:
            scores.append((statistics.mean(pieces), cluster_idx))

    if not scores:
        return None
    _, predicted_cluster = min(scores)
    cluster_waits = [
        r["target_wait_seconds"]
        for r, label in zip(training_rows, labels)
        if label == predicted_cluster
    ]
    if not cluster_waits:
        return None
    return predicted_cluster, statistics.median(cluster_waits), centers


def _cluster_knn_prediction(training_rows, current_row, cluster_analysis, feature_keys, k=7):
    """
    Classify the current cycle into a learned wait cluster by KNN in feature
    space, then use that cluster's historical median wait as the estimate.
    """
    labels, centers = _cluster_training_labels(training_rows, cluster_analysis)
    usable = []
    for key in feature_keys:
        current = current_row.get(key)
        vals = [r.get(key) for r in training_rows if r.get(key) is not None]
        if current is None or len(vals) < 8:
            continue
        std = statistics.pstdev(vals)
        if std > 0:
            usable.append((key, std))
    if len(usable) < 2:
        return None

    distances = []
    for row, label in zip(training_rows, labels):
        pieces = []
        for key, std in usable:
            if row.get(key) is None:
                break
            pieces.append(((row[key] - current_row[key]) / std) ** 2)
        else:
            distances.append((math.sqrt(statistics.mean(pieces)), label))
    if len(distances) < max(k, 5):
        return None

    neighbors = sorted(distances)[:k]
    votes = {}
    for distance, label in neighbors:
        # Distance weighting keeps a very close analogous cycle from being
        # drowned out by several merely-near neighbors.
        weight = 1.0 / max(distance, 0.10)
        votes[label] = votes.get(label, 0.0) + weight
    predicted_cluster = max(votes, key=votes.get)

    cluster_waits = [
        r["target_wait_seconds"]
        for r, label in zip(training_rows, labels)
        if label == predicted_cluster
    ]
    if not cluster_waits:
        return None
    return predicted_cluster, statistics.median(cluster_waits), centers


def _peak_bucket_cluster_prediction(training_rows, current_row, cluster_analysis):
    """
    A deliberately simple classifier for the Japan result we observed: bucket
    previous peak into tertiles, learn which wait cluster most often follows
    each tertile, then predict that cluster's median wait.
    """
    pairs = [
        (r.get("prev_peak_quantity"), r)
        for r in training_rows
        if r.get("prev_peak_quantity") is not None
    ]
    current_peak = current_row.get("prev_peak_quantity")
    if current_peak is None or len(pairs) < 12:
        return None

    labels, centers = _cluster_training_labels(training_rows, cluster_analysis)
    label_by_id = {id(r): label for r, label in zip(training_rows, labels)}
    peaks = sorted(v for v, _ in pairs)
    q1 = _percentile(peaks, 1 / 3)
    q2 = _percentile(peaks, 2 / 3)

    def bucket(value):
        if value <= q1:
            return 0
        if value <= q2:
            return 1
        return 2

    current_bucket = bucket(current_peak)
    votes = {}
    for peak, row in pairs:
        if bucket(peak) != current_bucket:
            continue
        label = label_by_id[id(row)]
        votes[label] = votes.get(label, 0) + 1
    if not votes:
        return None
    predicted_cluster = max(votes, key=votes.get)
    cluster_waits = [
        r["target_wait_seconds"]
        for r, label in zip(training_rows, labels)
        if label == predicted_cluster
    ]
    return predicted_cluster, statistics.median(cluster_waits), centers


def walk_forward_cluster_classifiers(feature_rows, min_train=18):
    """
    Walk-forward regime classifier. At each historical prediction point, wait
    clusters are refit using past data only, then the next cluster is predicted
    from features known at depletion time.
    """
    records = {}
    feature_sets = {
        "cluster_peak_tertile": None,
        "cluster_centroid_core": [
            "prev_peak_quantity",
            "prev_lifetime_seconds",
            "prev_depletion_rate_per_minute",
            "previous_wait_seconds",
            "recent3_wait_median_seconds",
        ],
        "cluster_knn_core_7": [
            "prev_peak_quantity",
            "prev_lifetime_seconds",
            "prev_depletion_rate_per_minute",
            "previous_wait_seconds",
            "recent3_wait_median_seconds",
            "recent5_wait_median_seconds",
        ],
    }

    for i, current in enumerate(feature_rows):
        training = feature_rows[:i]
        if len(training) < min_train:
            continue
        cluster_analysis = _fit_training_clusters(training)
        if not cluster_analysis:
            continue
        centers = [c["center"] for c in cluster_analysis["clusters"]]
        actual_cluster = _nearest_cluster_index(current["target_wait_seconds"], centers)

        predictions = {}
        predictions["cluster_peak_tertile"] = _peak_bucket_cluster_prediction(
            training, current, cluster_analysis
        )
        predictions["cluster_centroid_core"] = _cluster_feature_centroid_prediction(
            training, current, cluster_analysis, feature_sets["cluster_centroid_core"]
        )
        predictions["cluster_knn_core_7"] = _cluster_knn_prediction(
            training, current, cluster_analysis, feature_sets["cluster_knn_core_7"], k=7
        )

        for name, prediction in predictions.items():
            if prediction is None:
                continue
            predicted_cluster, estimate, fitted_centers = prediction
            error = current["target_wait_seconds"] - estimate
            records.setdefault(name, []).append({
                "predicted_cluster": predicted_cluster,
                "actual_cluster": actual_cluster,
                "cluster_correct": predicted_cluster == actual_cluster,
                "cluster_count": len(fitted_centers),
                "estimate_seconds": estimate,
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
        summaries.append(ClusterClassifierResult(
            name=name,
            predictions=len(rows),
            cluster_accuracy=sum(1 for r in rows if r["cluster_correct"]) / len(rows),
            median_absolute_error_seconds=statistics.median(absolute),
            mean_absolute_error_seconds=statistics.mean(absolute),
            p90_absolute_error_seconds=_percentile(absolute, 0.90),
            signed_bias_seconds=statistics.median(signed),
        ))

    summaries.sort(key=lambda r: (
        float("inf") if r.median_absolute_error_seconds is None else r.median_absolute_error_seconds,
        -(r.cluster_accuracy or 0),
        r.name,
    ))
    return summaries, records

def analyze_cycle_features(country: str, item_name: str):
    rows, bounces = build_cycle_feature_rows(country, item_name)
    waits = [row["target_wait_seconds"] for row in rows]
    lifetimes = [row["prev_lifetime_seconds"] for row in rows if row.get("prev_lifetime_seconds") is not None]
    return {
        "country": country,
        "item_name": item_name,
        "samples": len(rows),
        "median_wait_seconds": statistics.median(waits) if waits else None,
        "median_lifetime_seconds": statistics.median(lifetimes) if lifetimes else None,
        "provider_bounces_suppressed": len(bounces),
        "correlations": feature_correlations(rows),
        "clusters": wait_cluster_analysis(rows),
        "rounded_modes": rounded_wait_modes(rows)[:10],
        "feature_models": walk_forward_feature_models(rows)[0],
        "cluster_classifiers": walk_forward_cluster_classifiers(rows)[0],
        "rows": rows,
    }
