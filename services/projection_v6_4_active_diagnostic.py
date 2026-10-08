import argparse
import json

import services.projection_overnight_v6_3 as v63
from services.projection_engine_v6_1 import DECLARATION_THRESHOLDS
from services.projection_engine_v6_4 import (
    active_declared_summary,
    choose_depth_candidate,
)


def build_candidates(country, item_name, max_depth=5, shortlist=4):
    ctx = v63.base.build_item_context(
        country, item_name, max_depth=max_depth, min_history=8
    )

    baseline, bc = v63.base._baseline_stage(ctx)
    seeds = v63.base._top_baseline_pairs(
        baseline, max(4, shortlist), max_depth
    )
    spacing, sc = v63.base._spacing_stage(ctx, seeds)
    combined, cache = baseline + spacing, {**bc, **sc}

    sources = []
    for e in v63.base._select_points(combined, shortlist, max_depth):
        life, wait = v63.base._key(e)
        sources.append((
            f"{life} + {wait}",
            v63.base._family(wait),
            cache[(life, wait)],
        ))

    for n in (3, 5):
        rows = v63.base._ensemble(combined, cache, max_depth, n)
        if rows:
            sources.append((f"depthwise_ensemble{n}", "ensemble", rows))

    for label, rows in v63.analog_grid(ctx, depth=2):
        sources.append((label, "analog_horizon", rows))

    thresholds = (0.0,) + tuple(DECLARATION_THRESHOLDS)
    candidates = []
    for label, family, rows in sources:
        for cfg in v63.base.structural_configs():
            candidates.append({
                "point_model": label,
                "family": family,
                "config": cfg.label,
                "evaluation": v63.base.evaluate_arrival_state(
                    ctx, rows, cfg, thresholds=thresholds
                ),
            })
    return ctx, candidates


def main():
    p = argparse.ArgumentParser(
        description="V6.4 active-target diagnostic"
    )
    p.add_argument("country")
    p.add_argument("item_name")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--shortlist", type=int, default=4)
    args = p.parse_args()

    country = args.country.lower()
    item_name = args.item_name
    max_depth = max(2, args.depth)

    ctx, candidates = build_candidates(
        country, item_name, max_depth=max_depth,
        shortlist=max(2, args.shortlist)
    )
    target = v63.base.target_success(item_name)

    selected = {}
    for depth in range(1, max_depth + 1):
        choice = choose_depth_candidate(
            candidates,
            depth,
            target,
            v63.base._rank_candidate,
            DECLARATION_THRESHOLDS,
        )
        if choice:
            selected[depth] = choice

    train = active_declared_summary(
        selected, ctx.split_timestamp, "train"
    )
    holdout = active_declared_summary(
        selected, ctx.split_timestamp, "holdout"
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

    print("\n=== TRAINING-SELECTED MODEL BY DEPTH ===")
    print(json.dumps(printable, indent=2))

    print("\n=== ACTIVE TARGET TRAIN ===")
    print(json.dumps(train, indent=2))

    print("\n=== ACTIVE TARGET HOLDOUT ===")
    print(json.dumps(holdout, indent=2))


if __name__ == "__main__":
    main()
