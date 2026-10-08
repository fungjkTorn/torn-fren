import argparse
import json

import services.projection_v6_4_active_diagnostic as v64
from services.projection_engine_v6_1 import DECLARATION_THRESHOLDS
from services.projection_engine_v6_4 import active_declared_summary
from services.projection_engine_v6_5 import optimize_active_policy


def main():
    p = argparse.ArgumentParser(
        description="V6.5 joint active-target policy optimizer"
    )
    p.add_argument("country")
    p.add_argument("item_name")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--shortlist", type=int, default=4)
    p.add_argument("--options-per-depth", type=int, default=4)
    args = p.parse_args()

    country = args.country.lower()
    item_name = args.item_name
    max_depth = max(2, args.depth)

    ctx, candidates = v64.build_candidates(
        country,
        item_name,
        max_depth=max_depth,
        shortlist=max(2, args.shortlist),
    )
    target = v64.v63.base.target_success(item_name)

    optimized = optimize_active_policy(
        candidates,
        ctx.split_timestamp,
        max_depth,
        target,
        v64.v63.base._rank_candidate,
        DECLARATION_THRESHOLDS,
        options_per_depth=max(2, args.options_per_depth),
        passes=4,
    )

    selected = optimized["selected_by_depth"]
    holdout = active_declared_summary(
        selected,
        ctx.split_timestamp,
        "holdout",
    )

    printable = {}
    for depth, spec in selected.items():
        c = spec["candidate"]
        printable[str(depth)] = {
            "point_model": c["point_model"],
            "family": c["family"],
            "config": c["config"],
            "threshold": spec["threshold"],
            "rank_key": spec["rank_key"],
        }

    print("\n=== JOINTLY SELECTED ACTIVE POLICY ===")
    print(json.dumps(printable, indent=2))

    print("\n=== ACTIVE TARGET TRAIN ===")
    print(json.dumps(optimized["train_active"], indent=2))

    print("\n=== ACTIVE TARGET ROLLING TRAIN FOLDS ===")
    print(json.dumps(optimized["rolling_active_folds"], indent=2))

    print("\n=== ACTIVE TARGET HOLDOUT ===")
    print(json.dumps(holdout, indent=2))


if __name__ == "__main__":
    main()
