import argparse
import json

from services.projection_engine_v4 import build_item_context
from services.projection_engine_v6_1 import DECLARATION_THRESHOLDS
from services.projection_engine_v6_7 import persistence_rows
import services.projection_overnight_v6 as base


def main():
    p = argparse.ArgumentParser(
        description="Exact recent-cycle persistence diagnostic for Japan Xanax."
    )
    p.add_argument("--country", default="jap")
    p.add_argument("--item-name", default="Xanax")
    p.add_argument("--depth", type=int, default=5)
    args = p.parse_args()

    ctx = build_item_context(
        args.country.lower(),
        args.item_name,
        max_depth=max(2, args.depth),
        min_history=8,
    )
    target = base.target_success(args.item_name)
    thresholds = (0.0,) + tuple(DECLARATION_THRESHOLDS)

    baselines = (
        ("manual_last1_depletion_spacing", "depletion_spacing", "last1"),
        ("manual_last1_restock_spacing", "restock_spacing", "last1"),
        ("manual_last2_depletion_mean", "depletion_spacing", "last2_mean"),
        ("manual_last3_depletion_median", "depletion_spacing", "last3_median"),
    )

    report = {}
    for label, basis, method in baselines:
        report[label] = {}
        for depth in range(1, max(2, args.depth) + 1):
            rows = persistence_rows(ctx, depth, basis, method)
            if not rows:
                continue

            best = None
            for cfg in base.structural_configs():
                evaluation = base.evaluate_arrival_state(
                    ctx, rows, cfg, thresholds=thresholds
                )
                candidate = {
                    "point_model": f"{basis}|{method}",
                    "family": "manual_persistence",
                    "config": cfg.label,
                    "evaluation": evaluation,
                }
                for threshold in DECLARATION_THRESHOLDS:
                    key = base._rank_candidate(
                        candidate, depth, threshold, target
                    )
                    if best is None or key > best[0]:
                        best = (key, candidate, threshold)

            if best:
                key, candidate, threshold = best
                scores = candidate["evaluation"]["scores_by_threshold"][
                    str(threshold)
                ]
                report[label][str(depth)] = {
                    "threshold": threshold,
                    "rank_key": key,
                    "train": scores["train_by_depth"].get(depth),
                    "holdout": scores["holdout_by_depth"].get(depth),
                }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
