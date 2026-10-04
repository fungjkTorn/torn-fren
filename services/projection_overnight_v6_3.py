import services.projection_overnight_v6 as base
from services.projection_engine_v6_1 import DECLARATION_THRESHOLDS, selective_rank_key
from services.projection_engine_v6_3 import analog_grid

base.DECLARATION_THRESHOLDS = DECLARATION_THRESHOLDS
base.selective_rank_key = selective_rank_key


def run_item(country, item_name, max_depth=5, min_history=8, shortlist=4):
    ctx = base.build_item_context(
        country, item_name, max_depth=max_depth, min_history=min_history
    )
    if ctx.split_timestamp is None:
        return {
            "country": country,
            "item_name": item_name,
            "status": "insufficient_holdout_history",
            "valid_cycles": len(ctx.cycles),
        }

    baseline, bc = base._baseline_stage(ctx)
    seeds = base._top_baseline_pairs(baseline, max(4, shortlist), max_depth)
    spacing, sc = base._spacing_stage(ctx, seeds)
    combined, cache = baseline + spacing, {**bc, **sc}

    sources = []
    for e in base._select_points(combined, shortlist, max_depth):
        life, wait = base._key(e)
        sources.append((f"{life} + {wait}", base._family(wait), cache[(life, wait)]))

    for n in (3, 5):
        rows = base._ensemble(combined, cache, max_depth, n)
        if rows:
            sources.append((f"depthwise_ensemble{n}", "ensemble", rows))

    # Dedicated direct-horizon analogs for D2, where Monkey/long-flight
    # behavior has repeatedly failed under recursive and selector-only models.
    for label, rows in analog_grid(ctx, depth=2):
        sources.append((label, "analog_horizon", rows))

    thresholds = (0.0,) + tuple(base.DECLARATION_THRESHOLDS)
    candidates = []
    for label, family, rows in sources:
        for cfg in base.structural_configs():
            candidates.append({
                "point_model": label,
                "family": family,
                "config": cfg.label,
                "evaluation": base.evaluate_arrival_state(
                    ctx, rows, cfg, thresholds=thresholds
                ),
            })

    target = base.target_success(item_name)
    result = {
        "country": country,
        "item_name": item_name,
        "item_class": base.item_class(item_name),
        "target_declared_success": target,
        "status": "complete",
        "valid_cycles": len(ctx.cycles),
        "point_models_tested": len(sources),
        "arrival_state_candidates": len(candidates),
        "depths": {},
    }

    for depth in range(1, max_depth + 1):
        ranked = []
        for c in candidates:
            for t in base.DECLARATION_THRESHOLDS:
                ranked.append((base._rank_candidate(c, depth, t, target), c, t))
        ranked.sort(key=lambda x: x[0], reverse=True)
        result["depths"][str(depth)] = {
            "selected_on_training": (
                base._brief(ranked[0][1], depth, ranked[0][2]) if ranked else None
            ),
            "top5_selected_on_training": [
                base._brief(c, depth, t) for _, c, t in ranked[:5]
            ],
            "oracle_holdout_ceiling_DIAGNOSTIC_ONLY": base._oracle(candidates, depth),
        }
    return result


base.run_item = run_item

if __name__ == "__main__":
    base.main()
