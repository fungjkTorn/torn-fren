import argparse
import json

import services.projection_v6_4_active_diagnostic as v64
from services.projection_engine_v6_1 import DECLARATION_THRESHOLDS
from services.projection_engine_v6_5 import optimize_active_policy
from services.projection_engine_v6_6 import (
    choose_safety_delay,
    evaluate_safety_delay,
)


def main():
    p = argparse.ArgumentParser(
        description="V6.6 focused safety-delay calibration"
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
    print("\n=== V6.5 SELECTED DEPTHS ===")
    print(sorted(selected))

    results = {}
    for depth, spec in selected.items():
        candidate = spec["candidate"]
        threshold = spec["threshold"]
        delay = choose_safety_delay(
            candidate,
            ctx.split_timestamp,
            threshold,
            target,
        )
        if delay is None:
            continue
        evaluation = evaluate_safety_delay(
            candidate,
            ctx.split_timestamp,
            threshold,
            delay["fraction"],
            delay["seconds"],
        )
        results[str(depth)] = {
            "point_model": candidate["point_model"],
            "family": candidate["family"],
            "threshold": threshold,
            "chosen_delay_fraction": delay["fraction"],
            "chosen_delay_seconds": delay["seconds"],
            "selection_train": delay["train"],
            "selection_recent_train": delay["recent_train"],
            "evaluation": evaluation,
        }

    print("\n=== V6.6 SAFETY-DELAY RESULTS ===")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
