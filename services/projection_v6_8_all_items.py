import argparse
import json
from pathlib import Path

from services.projection_engine_v6 import item_class, target_success
from services.projection_engine_v6_8 import METHODS, build_context, evaluate_method
from services.projection_overnight_v5 import discover_items


def _select_on_train(method_reports, target):
    ranked = []
    for method, report in method_reports.items():
        s = report.get("train_active") or {}
        n = int(s.get("actionable_n") or 0)
        rate = s.get("hit_rate")
        lcb = s.get("wilson_lower_95")
        if rate is None:
            continue
        meets = int(rate >= target and n >= 10)
        ranked.append((
            meets,
            float(lcb or 0.0),
            float(rate),
            n,
            method,
        ))
    ranked.sort(reverse=True)
    if not ranked:
        return None
    best = ranked[0]
    return {
        "valid_policy": bool(best[0]),
        "method": best[4],
        "train_rank": list(best[:4]),
    }


def main():
    p = argparse.ArgumentParser(
        description="V6.8 literal recent-cycle replay across all tracked items"
    )
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--min-history", type=int, default=8)
    p.add_argument("--output", default="data/projection_v6_8_all_items.json")
    args = p.parse_args()

    report = {"items": {}}
    for country, item in discover_items():
        key = f"{country}::{item}"
        try:
            ctx = build_context(
                country, item, max_depth=max(2, args.depth),
                min_history=max(3, args.min_history),
            )
            method_reports = {
                m: evaluate_method(ctx, m, max_depth=max(2, args.depth))
                for m in METHODS
            }
            target = target_success(item)
            selected = _select_on_train(method_reports, target)
            block = {
                "country": country,
                "item_name": item,
                "item_class": item_class(item),
                "target": target,
                "valid_cycles": len(ctx.cycles),
                "selected_on_train": selected,
                "methods": method_reports,
            }
            if selected:
                chosen = method_reports[selected["method"]]
                block["selected_holdout_active"] = chosen["holdout_active"]
            report["items"][key] = block
            hold = block.get("selected_holdout_active") or {}
            print(
                f"{country.upper()} / {item}: "
                f"{selected['method'] if selected else 'NONE'} "
                f"valid={selected['valid_policy'] if selected else False} "
                f"holdout={hold.get('hit_rate')} n={hold.get('actionable_n')}",
                flush=True,
            )
        except Exception as exc:
            report["items"][key] = {
                "country": country, "item_name": item,
                "status": "error", "error": repr(exc),
            }
            print(f"{country.upper()} / {item}: ERROR {exc!r}", flush=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Saved full report to {out}")


if __name__ == "__main__":
    main()
