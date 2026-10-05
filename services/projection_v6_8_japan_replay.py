import argparse
import json
import statistics
from pathlib import Path

from services.projection_engine_v6_8 import METHODS, build_context, evaluate_method


def _next_gap_life_pairs(ctx):
    rows = []
    cycles = ctx.cycles
    for i in range(1, len(cycles) - 1):
        prev, cur, nxt = cycles[i - 1], cycles[i], cycles[i + 1]
        required = (
            prev.get("depletion_time"), cur.get("restock_time"),
            cur.get("depletion_time"), nxt.get("restock_time"),
            nxt.get("depletion_time"),
        )
        if any(x is None for x in required):
            continue
        gap_now = float(cur["restock_time"]) - float(prev["depletion_time"])
        life_now = float(cur["depletion_time"]) - float(cur["restock_time"])
        gap_next = float(nxt["restock_time"]) - float(cur["depletion_time"])
        life_next = float(nxt["depletion_time"]) - float(nxt["restock_time"])
        if min(gap_now, life_now, gap_next, life_next) <= 0:
            continue
        rows.append((gap_now, life_now, gap_next, life_next))
    return rows


def _mae(pairs, a, b):
    vals = [abs(x[a] - x[b]) for x in pairs]
    return statistics.mean(vals) if vals else None


def _corr(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx = sum((x-mx)**2 for x in xs)
    sy = sum((y-my)**2 for y in ys)
    if sx <= 0 or sy <= 0:
        return None
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / (sx*sy) ** 0.5


def main():
    p = argparse.ArgumentParser(
        description="V6.8 literal recent-cycle replay + regime persistence test"
    )
    p.add_argument("country", nargs="?", default="jap")
    p.add_argument("item_name", nargs="?", default="Xanax")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--min-history", type=int, default=8)
    p.add_argument("--output", default="data/projection_v6_8_japan_replay.json")
    args = p.parse_args()

    ctx = build_context(
        args.country, args.item_name,
        max_depth=max(2, args.depth),
        min_history=max(3, args.min_history),
    )
    pairs = _next_gap_life_pairs(ctx)
    persistence = {
        "pairs_n": len(pairs),
        "gap_last1_to_next_correlation": _corr(
            [r[0] for r in pairs], [r[2] for r in pairs]
        ),
        "lifetime_last1_to_next_correlation": _corr(
            [r[1] for r in pairs], [r[3] for r in pairs]
        ),
        "last1_gap_next_mae_seconds": _mae(pairs, 0, 2),
        "last1_lifetime_next_mae_seconds": _mae(pairs, 1, 3),
    }

    methods = {
        method: evaluate_method(ctx, method, max_depth=max(2, args.depth))
        for method in METHODS
    }
    report = {
        "country": args.country.lower(),
        "item_name": args.item_name,
        "valid_cycles": len(ctx.cycles),
        "split_timestamp": ctx.split_timestamp,
        "literal_formula": (
            "R[n+d] = D[n] + d*gap_est + (d-1)*life_est; "
            "departure = predicted_restock - travel_time"
        ),
        "regime_persistence": persistence,
        "methods": methods,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nSaved full report to {out}")


if __name__ == "__main__":
    main()
