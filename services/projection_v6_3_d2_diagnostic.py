import argparse
import json

import services.projection_overnight_v6_3 as v63


def main():
    p = argparse.ArgumentParser(
        description="Focused V6.3 D2 diagnostic: selected model vs holdout oracle ceiling."
    )
    p.add_argument("country")
    p.add_argument("item_name")
    p.add_argument("--shortlist", type=int, default=4)
    args = p.parse_args()

    result = v63.run_item(
        args.country.lower(),
        args.item_name,
        max_depth=2,
        min_history=8,
        shortlist=max(2, args.shortlist),
    )

    block = result.get("depths", {}).get("2", {})
    selected = block.get("selected_on_training")
    oracle = block.get("oracle_holdout_ceiling_DIAGNOSTIC_ONLY")

    print("\n=== D2 SELECTED ON TRAINING ===")
    print(json.dumps(selected, indent=2))

    print("\n=== D2 HOLDOUT ORACLE CEILING (DIAGNOSTIC ONLY) ===")
    print(json.dumps(oracle, indent=2))

    top = block.get("top5_selected_on_training") or []
    print("\n=== TOP 5 TRAINING-SELECTED D2 CANDIDATES ===")
    for i, row in enumerate(top, 1):
        s = row.get("holdout") or {}
        print(
            f"{i}. {row.get('forecast_family')} | {row.get('point_model')} | "
            f"gate={row.get('declaration_threshold')} | "
            f"holdout_hit={s.get('declared_hit_rate')} | "
            f"coverage={s.get('coverage')} | n={s.get('declared_n')}"
        )


if __name__ == "__main__":
    main()
