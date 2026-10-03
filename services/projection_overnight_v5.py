import argparse
import json
import math
import os
import sqlite3
import statistics
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from services.history_service import DB_PATH
from services.projection_chain_lab_v3 import (
    ARRIVAL_POLICIES,
    BIAS_POLICIES,
    BASE_METHODS,
    EXTRA_LIFETIME_METHODS,
    EXTRA_WAIT_METHODS,
    conservative_key,
)
from services.projection_engine_v4 import (
    DIRECT_HORIZON_METHODS,
    active_target_rows,
    build_item_context,
    evaluate_from_point_rows,
    point_forecast_pair as v4_point_forecast_pair,
)
from services.projection_overnight_v4 import WINDOW_POLICIES
from services.projection_engine_v5 import (
    BridgeConfig,
    SPACING_METHODS,
    bridge_point_forecast,
)

FLOWER_NAMES = {
    "dahlia", "banana orchid", "crocus", "hawaiian flower", "heather",
    "ceibo flower", "edelweiss", "cherry blossom", "peony",
    "tribulus omanense", "african violet",
}
XANAX_COUNTRIES = ("can", "uni", "jap")
CHECKPOINT = Path("data/projection_overnight_v5_checkpoint.json")
REPORT = Path("data/projection_overnight_v5_report.json")


def discover_items():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT LOWER(country), item_name
            FROM stock_history
            ORDER BY LOWER(country), item_name COLLATE NOCASE
            """
        ).fetchall()

    result = []
    for country, item in rows:
        lower = item.lower()
        if "plushie" in lower or lower in FLOWER_NAMES:
            result.append((country, item))
        elif lower == "xanax" and country in XANAX_COUNTRIES:
            result.append((country, item))
    return result


def _fold_floor(entry, depth):
    folds = (entry.get("rolling_folds_by_depth") or {}).get(depth) or []
    vals = [
        f.get("wilson_lower_95")
        for f in folds
        if f and f.get("wilson_lower_95") is not None
    ]
    return min(vals) if vals else None


def _rank(entries, selector, depth=None):
    usable = []
    for entry in entries:
        summary = selector(entry)
        if summary:
            usable.append((entry, summary, _fold_floor(entry, depth) if depth else None))

    def key(item):
        _entry, summary, floor = item
        base = conservative_key(summary)
        stability = floor if floor is not None else -1.0
        return (base[0], stability, base[1], base[2], base[3])

    usable.sort(key=key, reverse=True)
    return [(e, s) for e, s, _ in usable]


def _baseline_stage(ctx):
    lifetimes = tuple(BASE_METHODS) + tuple(EXTRA_LIFETIME_METHODS)
    waits = tuple(BASE_METHODS) + tuple(EXTRA_WAIT_METHODS)
    entries = []
    cache = {}

    for life in lifetimes:
        for wait in waits:
            rows = v4_point_forecast_pair(ctx, life, wait)
            cache[(life, wait)] = rows
            entries.append(
                evaluate_from_point_rows(
                    ctx, rows, life, wait, "midpoint", "none", "none"
                )
            )

        for direct_method in DIRECT_HORIZON_METHODS:
            label = f"direct:{direct_method}"
            rows = v4_point_forecast_pair(ctx, life, label)
            cache[(life, label)] = rows
            entries.append(
                evaluate_from_point_rows(
                    ctx, rows, life, label, "midpoint", "none", "none"
                )
            )
    return entries, cache


def _top_baseline_pairs(entries, shortlist, max_depth):
    selected = set()
    for depth in range(1, max_depth + 1):
        ranked = _rank(
            entries,
            lambda e, d=depth: e["train_by_depth"].get(d),
            depth=depth,
        )
        for entry, _ in ranked[:shortlist]:
            wait = entry["strategy"].wait
            if not wait.startswith("direct:"):
                selected.add((entry["strategy"].lifetime, wait))
    active = _rank(entries, lambda e: e["train_active"])
    for entry, _ in active[:shortlist]:
        wait = entry["strategy"].wait
        if not wait.startswith("direct:"):
            selected.add((entry["strategy"].lifetime, wait))
    return sorted(selected)


def _spacing_stage(ctx, baseline_pairs):
    entries = []
    cache = {}
    for life, wait in baseline_pairs:
        for spacing in SPACING_METHODS:
            configs = [
                BridgeConfig("direct_spacing", wait, spacing),
                BridgeConfig("hybrid", wait, spacing, 0.25),
                BridgeConfig("hybrid", wait, spacing, 0.50),
                BridgeConfig("hybrid", wait, spacing, 0.75),
            ]
            for config in configs:
                rows = bridge_point_forecast(ctx, life, config)
                key = (life, config.label)
                cache[key] = rows
                entries.append(
                    evaluate_from_point_rows(
                        ctx, rows, life, config.label,
                        "midpoint", "none", "none"
                    )
                )
    return entries, cache


def _select_point_finalists(entries, shortlist, max_depth):
    chosen = {}
    for depth in range(1, max_depth + 1):
        ranked = _rank(
            entries,
            lambda e, d=depth: e["train_by_depth"].get(d),
            depth=depth,
        )
        for e, _ in ranked[:shortlist]:
            chosen[(e["strategy"].lifetime, e["strategy"].wait)] = e
    active = _rank(entries, lambda e: e["train_active"])
    for e, _ in active[:shortlist]:
        chosen[(e["strategy"].lifetime, e["strategy"].wait)] = e
    return list(chosen.values())


def _policy_expand(ctx, point_entries, point_cache):
    result = []
    for point in point_entries:
        life = point["strategy"].lifetime
        label = point["strategy"].wait
        rows = point_cache[(life, label)]
        for arrival in ARRIVAL_POLICIES:
            for bias in BIAS_POLICIES:
                for window in WINDOW_POLICIES:
                    result.append(
                        evaluate_from_point_rows(
                            ctx, rows, life, label,
                            arrival, bias, window
                        )
                    )
    return result


def _brief(entry, max_depth):
    return {
        "strategy": entry["strategy"].name,
        "forecast_family": (
            "direct_horizon" if entry["strategy"].wait.startswith("direct:")
            else "direct_spacing" if entry["strategy"].wait.startswith("spacing[")
            else "hybrid" if entry["strategy"].wait.startswith("hybrid")
            else "decomposition"
        ),
        "train_active": entry["train_active"],
        "holdout_active": entry["holdout_active"],
        "train_by_depth": {
            str(d): entry["train_by_depth"].get(d)
            for d in range(1, max_depth + 1)
        },
        "holdout_by_depth": {
            str(d): entry["holdout_by_depth"].get(d)
            for d in range(1, max_depth + 1)
        },
    }


def _ensemble(entries, depth, top_n=3):
    ranked = _rank(
        entries,
        lambda e: e["train_by_depth"].get(depth),
        depth=depth,
    )
    members = [e for e, _ in ranked[:top_n]]
    if len(members) < 2:
        return None

    maps = []
    for e in members:
        split = e["split_timestamp"]
        rows = [
            r for r in e["rows"]
            if int(r["anchor_timestamp"]) >= split
            and r["depth"] == depth
        ]
        maps.append({
            (r["anchor_timestamp"], r["depth"]): r for r in rows
        })

    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)
    if not common:
        return None

    hits = early = late = 0
    for key in common:
        rs = [m[key] for m in maps]
        arrival = statistics.median(
            r["recommended_arrival_timestamp"] for r in rs
        )
        actual_r = rs[0]["actual_restock_timestamp"]
        actual_d = rs[0]["actual_depletion_timestamp"]
        if actual_r <= arrival < actual_d:
            hits += 1
        elif arrival < actual_r:
            early += 1
        else:
            late += 1

    n = len(common)
    p = hits / n
    z = 1.96
    denom = 1 + z*z/n
    lower = (
        p + z*z/(2*n)
        - z*math.sqrt((p*(1-p)+z*z/(4*n))/n)
    ) / denom
    return {
        "members": [e["strategy"].name for e in members],
        "n": n,
        "arrival_hit_rate": p,
        "wilson_lower_95": lower,
        "early_rate": early/n,
        "late_rate": late/n,
    }


def run_item(country, item_name, max_depth=5, min_history=8, shortlist=8):
    started = time.time()
    ctx = build_item_context(
        country, item_name, max_depth=max_depth,
        min_history=min_history
    )
    if ctx.split_timestamp is None:
        return {
            "country": country, "item_name": item_name,
            "status": "insufficient_holdout_history",
            "valid_cycles": len(ctx.cycles),
        }

    baseline, baseline_cache = _baseline_stage(ctx)
    seed_pairs = _top_baseline_pairs(
        baseline, shortlist, max_depth
    )

    spacing, spacing_cache = _spacing_stage(ctx, seed_pairs)

    combined_points = baseline + spacing
    combined_cache = {**baseline_cache, **spacing_cache}

    finalists = _select_point_finalists(
        combined_points, shortlist, max_depth
    )
    expanded = _policy_expand(
        ctx, finalists, combined_cache
    )

    output = {
        "country": country,
        "item_name": item_name,
        "status": "complete",
        "valid_cycles": len(ctx.cycles),
        "runtime_seconds": round(time.time()-started, 3),
        "seed_baseline_pairs": len(seed_pairs),
        "point_candidates": len(combined_points),
        "policy_candidates": len(expanded),
        "depths": {},
    }

    for depth in range(1, max_depth+1):
        ranked = _rank(
            expanded,
            lambda e, d=depth: e["train_by_depth"].get(d),
            depth=depth,
        )
        output["depths"][str(depth)] = {
            "top5_selected_on_train": [
                _brief(e, max_depth) for e, _ in ranked[:5]
            ],
            "ensemble_top3_holdout": _ensemble(
                expanded, depth, top_n=3
            ),
        }
    return output


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except Exception:
        return None


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _print_item(result):
    print(
        f"{result['country'].upper()} / {result['item_name']} "
        f"cycles={result.get('valid_cycles')} "
        f"runtime={result.get('runtime_seconds',0)/60:.1f}m",
        flush=True,
    )
    if result.get("status") != "complete":
        print("  " + result.get("status","error"), flush=True)
        if result.get("error"):
            print("  " + result["error"], flush=True)
        if result.get("traceback"):
            print(result["traceback"], flush=True)
        return

    for d, block in result["depths"].items():
        top = block.get("top5_selected_on_train") or []
        if not top:
            continue
        winner = top[0]
        s = winner["holdout_by_depth"].get(d)
        if not s:
            continue
        print(
            f"  D{d} {winner['forecast_family']} "
            f"{winner['strategy']} | "
            f"holdout={s['arrival_hit_rate']*100:.1f}% "
            f"LCB95={s['wilson_lower_95']*100:.1f}% "
            f"early={s['early_rate']*100:.1f}% "
            f"late={s['late_rate']*100:.1f}% "
            f"MedAE={s['median_absolute_error_seconds']/60:.1f}m",
            flush=True,
        )


def run_suite(max_depth=5, min_history=8, shortlist=8, workers=4, resume=True):
    checkpoint = _load(CHECKPOINT) if resume else None
    if not checkpoint:
        checkpoint = {"completed": {}, "started_at": int(time.time())}

    items = discover_items()
    pending = []
    for x in items:
        key = f"{x[0]}::{x[1].lower()}"
        existing = checkpoint["completed"].get(key)
        if existing is None or existing.get("status") != "complete":
            pending.append(x)
    print(
        f"V5 bridge-family tournament: {len(items)} total, "
        f"{len(pending)} pending, workers={workers}",
        flush=True,
    )

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_item, c, i, max_depth, min_history, shortlist
            ): (c, i)
            for c, i in pending
        }
        for future in as_completed(futures):
            c, i = futures[future]
            key = f"{c}::{i.lower()}"
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "country": c,
                    "item_name": i,
                    "status": "error",
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                }
            checkpoint["completed"][key] = result
            _save(CHECKPOINT, checkpoint)
            _print_item(result)

    checkpoint["finished_at"] = int(time.time())
    _save(CHECKPOINT, checkpoint)
    _save(REPORT, checkpoint)
    print(f"Finished: {REPORT}", flush=True)


def main():
    p = argparse.ArgumentParser(
        description="V5 direct-spacing/hybrid/direct-horizon projection tournament."
    )
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--min-history", type=int, default=8)
    p.add_argument("--shortlist", type=int, default=8)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--item-country", default=None)
    p.add_argument("--item-name", default=None)
    args = p.parse_args()

    if args.item_country or args.item_name:
        if not (args.item_country and args.item_name):
            p.error("--item-country and --item-name must be supplied together")
        result = run_item(
            args.item_country.lower(),
            args.item_name,
            max_depth=max(2, args.depth),
            min_history=max(3, args.min_history),
            shortlist=max(3, args.shortlist),
        )
        _print_item(result)
        return

    run_suite(
        max_depth=max(2,args.depth),
        min_history=max(3,args.min_history),
        shortlist=max(3,args.shortlist),
        workers=max(1,args.workers),
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
