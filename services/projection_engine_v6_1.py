import statistics

from services.projection_engine_v6 import *  # noqa: F401,F403

DECLARATION_THRESHOLDS = (
    0.50, 0.55, 0.60, 0.65, 0.70, 0.75,
    0.80, 0.85, 0.90, 0.925, 0.95,
)


def selective_rank_key(summary, target, folds=None):
    if not summary or not summary.get("declared_n"):
        return (-1, -1, -1, -1, -1, -1, -1)

    precision = summary.get("declared_hit_rate") or 0.0
    lcb = summary.get("declared_wilson_lower_95") or 0.0
    coverage = summary.get("coverage") or 0.0
    declared_n = summary.get("declared_n") or 0

    usable_folds = [
        f for f in (folds or [])
        if f
        and f.get("declared_n", 0) >= 5
        and f.get("declared_hit_rate") is not None
    ]
    fold_precisions = [f["declared_hit_rate"] for f in usable_folds]
    fold_coverages = [f.get("coverage") or 0.0 for f in usable_folds]

    fold_floor = min(fold_precisions) if fold_precisions else 0.0
    fold_median = statistics.median(fold_precisions) if fold_precisions else 0.0
    coverage_floor = min(fold_coverages) if fold_coverages else 0.0

    enough = declared_n >= 12
    enough_folds = len(usable_folds) >= 2
    meaningful_coverage = coverage >= 0.10
    stable = (
        enough_folds
        and fold_median >= target
        and fold_floor >= max(0.0, target - 0.12)
        and coverage_floor >= 0.05
    )

    return (
        1 if enough and meaningful_coverage and precision >= target and stable else 0,
        1 if enough_folds else 0,
        fold_median,
        fold_floor,
        lcb,
        coverage,
        declared_n,
    )
