import argparse
import json

import services.projection_v6_4_active_diagnostic as v64
from services.projection_engine_v6_1 import DECLARATION_THRESHOLDS
from services.projection_engine_v6_7 import persistence_grid


def main():
    p = argparse.ArgumentParser(
        description="V6.7 simple persistence benchmark"
    )
    p.add_argument("country")
    p.add_argument("item_name")
    p.add_argument("--depth", type=int, default=5)
    args = p.parse_args()

    country = args.country.lower()
    item = args.item_name
    max_depth = max(2, args.depth)
    ctx = v64.v63.base.build_item_context(
        country, item, max_depth=max_depth, min_history=8
    )
    target = v64.v63.base.target_success(item)

    candidates = []
    thresholds = (0.0,) + tuple(DECLARATION_THRESHOLDS)

    for label, rows in persistence_grid(ctx, max_depth=max_depth):
        for cfg in v64.v63.base.structural_configs():
            candidates.append({
                "point_model": label,
                "family": "persistence",
                "config": cfg.label,
                "evaluation": v64.v63.base.evaluate_arrival_state(
                    ctx, rows, cfg, thresholds=thresholds
                ),
            })

    report = {}
    for depth in range(1, max_depth + 1):
        ranked = []
        for c in candidates:
            for t in DECLARATION_THRESHOLDS:
                key = v64.v63.base._rank_candidate(
                    c, depth, t, target
                )
                ranked.append((key, c, t))
        ranked.sort(key=lambda x: x[0], reverse=True)

        top = []
        for key, c, t in ranked[:10]:
            s = c["evaluation"]["scores_by_threshold"][str(t)]
            top.append({
                "point_model": c["point_model"],
                "config": c["config"],
                "threshold": t,
                "rank_key": key,
                "train": s["train_by_depth"].get(depth),
                "holdout": s["holdout_by_depth"].get(depth),
            })
        report[str(depth)] = top

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
