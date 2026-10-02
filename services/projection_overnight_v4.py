import argparse
import json
import math
import os
import sqlite3
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from services.country_regime_lab import analyze_country_regime
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
    active_target_rows,
    all_point_pairs,
    apply_policy,
    build_item_context,
    evaluate_from_point_rows,
    point_forecast_pair,
)

FLOWER_NAMES = {
    "dahlia",
    "banana orchid",
    "crocus",
    "hawaiian flower",
    "heather",
    "ceibo flower",
    "edelweiss",
    "cherry blossom",
    "peony",
    "tribulus omanense",
    "african violet",
}

XANAX_COUNTRIES = ("can", "uni", "jap")
CHECKPOINT = Path("data/projection_overnight_v4_checkpoint.json")
REPORT = Path("data/projection_overnight_v4_report.json")


def discover_items(countries=None):
    """
    Research target set:
      - every plushie in every country represented in stock_history
      - every known flower in every country represented in stock_history
      - Xanax in CAN / UNI / JAP

    If countries is supplied, it acts only as an optional filter for the
    flower/plushie universe. Xanax remains limited to XANAX_COUNTRIES.
    """
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT LOWER(country), item_name
            FROM stock_history
            ORDER BY LOWER(country), item_name COLLATE NOCASE
            """
        ).fetchall()

    allowed = (
        {c.lower() for c in countries}
        if countries
        else None
    )

    out = []
    for country, item in rows:
        lower = item.lower()

        is_plushie_or_flower = (
            "plushie" in lower
            or lower in FLOWER_NAMES
        )
        if is_plushie_or_flower:
            if allowed is None or country in allowed:
                out.append((country, item))
            continue

        if lower == "xanax" and country in XANAX_COUNTRIES:
            out.append((country, item))

    return out


def _fold_floor(entry, depth):
    folds = (entry.get("rolling_folds_by_depth") or {}).get(depth) or []
    values = [
        f.get("wilson_lower_95")
        for f in folds
        if f and f.get("wilson_lower_95") is not None
    ]
    return min(values) if values else None


def _rank(entries, selector, depth=None):
    usable = []
    for entry in entries:
        summary = selector(entry)
        if not summary:
            continue
        floor = _fold_floor(entry, depth) if depth is not None else None
        usable.append((entry, summary, floor))

    def key(item):
        entry, summary, floor = item
        base = conservative_key(summary)
        stability = floor if floor is not None else -1.0
        return (base[0], stability, base[1], base[2], base[3])

    usable.sort(key=key, reverse=True)
    return [(e, s) for e, s, _ in usable]


def _brief(entry, max_depth):
    return {
        "strategy": entry["strategy"].name,
        "split_timestamp": entry["split_timestamp"],
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
        "rolling_folds_by_depth": {
            str(d): entry["rolling_folds_by_depth"].get(d) or []
            for d in range(1, max_depth + 1)
        },
    }


def _ensemble(entries, depth=None, active=False, top_n=3):
    if active:
        ranked = _rank(entries, lambda e: e["train_active"])
    else:
        ranked = _rank(
            entries,
            lambda e: e["train_by_depth"].get(depth),
            depth=depth,
        )
    members = [e for e, _ in ranked[:top_n]]
    if len(members) < 2:
        return None

    maps = []
    for entry in members:
        split = entry["split_timestamp"]
        rows = [
            r for r in entry["rows"]
            if int(r["anchor_timestamp"]) >= split
        ]
        if active:
            rows = active_target_rows(rows)
        elif depth is not None:
            rows = [r for r in rows if r["depth"] == depth]

        maps.append({
            (r["anchor_timestamp"], r["depth"]): r
            for r in rows
        })

    common = set(maps[0])
    for mapping in maps[1:]:
        common &= set(mapping)
    if not common:
        return None

    outcomes = []
    for key in sorted(common):
        rs = [m[key] for m in maps]
        arrival = statistics.median(
            r["recommended_arrival_timestamp"] for r in rs
        )
        actual_restock = rs[0]["actual_restock_timestamp"]
        actual_depletion = rs[0]["actual_depletion_timestamp"]
        hit = int(actual_restock <= arrival < actual_depletion)
        early = int(arrival < actual_restock)
        late = int(arrival >= actual_depletion)
        outcomes.append((hit, early, late))

    n = len(outcomes)
    hits = sum(x[0] for x in outcomes)
    p = hits / n
    z = 1.96
    denom = 1.0 + z*z/n
    lower = (
        p + z*z/(2*n)
        - z*math.sqrt((p*(1-p) + z*z/(4*n))/n)
    ) / denom

    return {
        "members": [e["strategy"].name for e in members],
        "n": n,
        "arrival_hit_rate": p,
        "wilson_lower_95": lower,
        "early_rate": sum(x[1] for x in outcomes) / n,
        "late_rate": sum(x[2] for x in outcomes) / n,
    }


def _select_finalist_pairs(stage1, shortlist, max_depth):
    chosen = set()

    active = _rank(stage1, lambda e: e["train_active"])
    for e, _ in active[:shortlist]:
        chosen.add((e["strategy"].lifetime, e["strategy"].wait))

    for depth in range(1, max_depth + 1):
        ranked = _rank(
            stage1,
            lambda e, d=depth: e["train_by_depth"].get(d),
            depth=depth,
        )
        for e, _ in ranked[:shortlist]:
            chosen.add((e["strategy"].lifetime, e["strategy"].wait))

    return sorted(chosen)


def run_item(country, item_name, max_depth=4, min_history=8, shortlist=10):
    started = time.time()
    ctx = build_item_context(
        country, item_name, max_depth=max_depth, min_history=min_history
    )

    if ctx.split_timestamp is None:
        return {
            "country": country,
            "item_name": item_name,
            "status": "insufficient_holdout_history",
            "valid_cycles": len(ctx.cycles),
            "runtime_seconds": round(time.time() - started, 3),
        }

    # Stage 1: each lifetime/wait point chain is built ONCE.
    point_cache = {}
    stage1 = []
    for life, wait, point_rows in all_point_pairs(ctx):
        point_cache[(life, wait)] = point_rows
        stage1.append(
            evaluate_from_point_rows(
                ctx, point_rows, life, wait, "midpoint", "none"
            )
        )

    finalists = _select_finalist_pairs(stage1, shortlist, max_depth)

    # Stage 2: reuse each finalist point chain for all 24 policy combinations.
    stage2 = []
    for life, wait in finalists:
        point_rows = point_cache[(life, wait)]
        for arrival in ARRIVAL_POLICIES:
            for bias in BIAS_POLICIES:
                stage2.append(
                    evaluate_from_point_rows(
                        ctx, point_rows, life, wait, arrival, bias
                    )
                )

    result = {
        "country": country,
        "item_name": item_name,
        "status": "complete",
        "valid_cycles": len(ctx.cycles),
        "split_timestamp": ctx.split_timestamp,
        "stage1_point_pairs": len(stage1),
        "finalist_pairs": len(finalists),
        "stage2_policy_models": len(stage2),
        "country_regime_diagnostic": analyze_country_regime(
            country, item_name
        ),
        "active": {},
        "depths": {},
    }

    active_ranked = _rank(stage2, lambda e: e["train_active"])
    result["active"]["top5_selected_on_train"] = [
        _brief(e, max_depth) for e, _ in active_ranked[:5]
    ]
    result["active"]["ensemble_top3_holdout"] = _ensemble(
        stage2, active=True, top_n=3
    )

    for depth in range(1, max_depth + 1):
        ranked = _rank(
            stage2,
            lambda e, d=depth: e["train_by_depth"].get(d),
            depth=depth,
        )
        result["depths"][str(depth)] = {
            "top5_selected_on_train": [
                _brief(e, max_depth) for e, _ in ranked[:5]
            ],
            "ensemble_top3_holdout": _ensemble(
                stage2, depth=depth, top_n=3
            ),
        }

    result["runtime_seconds"] = round(time.time() - started, 3)
    return result


def _load_checkpoint(path):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"completed": {}, "started_at": int(time.time())}


def _save_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _holdout_line(block, depth=None):
    top = block.get("top5_selected_on_train") or []
    if not top:
        return "no eligible model"
    winner = top[0]
    summary = (
        winner.get("holdout_active")
        if depth is None
        else winner.get("holdout_by_depth", {}).get(str(depth))
    )
    if not summary:
        return winner["strategy"] + " | no holdout"
    return (
        f"{winner['strategy']} | "
        f"holdout={summary['arrival_hit_rate']*100:.1f}% "
        f"LCB95={summary['wilson_lower_95']*100:.1f}% "
        f"early={summary['early_rate']*100:.1f}% "
        f"late={summary['late_rate']*100:.1f}% "
        f"MedAE={summary['median_absolute_error_seconds']/60:.1f}m"
    )


def _print_result(result, max_depth):
    print(
        f"{result['country'].upper()} / {result['item_name']} "
        f"cycles={result.get('valid_cycles')} "
        f"runtime={result.get('runtime_seconds',0)/60:.1f}m",
        flush=True,
    )
    if result.get("status") != "complete":
        print(f"  {result.get('status')}", flush=True)
        return

    print("  ACTIVE " + _holdout_line(result["active"]), flush=True)
    for depth in range(1, max_depth + 1):
        print(
            f"  D{depth} "
            + _holdout_line(result["depths"][str(depth)], depth),
            flush=True,
        )


def run_suite(
    countries,
    max_depth=4,
    min_history=8,
    shortlist=10,
    workers=1,
    resume=True,
):
    checkpoint = (
        _load_checkpoint(CHECKPOINT)
        if resume
        else {"completed": {}, "started_at": int(time.time())}
    )
    items = discover_items(countries)

    pending = [
        item for item in items
        if f"{item[0].lower()}::{item[1].lower()}"
        not in checkpoint["completed"]
    ]

    print(
        f"V4 optimized overnight suite: {len(items)} total, "
        f"{len(pending)} pending, workers={workers}",
        flush=True,
    )
    print(
        "Each item builds history once; point chains are reused across "
        "arrival/bias policies. Holdout remains selection-blind.",
        flush=True,
    )

    if workers <= 1:
        for idx, (country, item_name) in enumerate(pending, 1):
            print(
                f"[{idx}/{len(pending)}] START "
                f"{country.upper()} / {item_name}",
                flush=True,
            )
            result = run_item(
                country, item_name, max_depth, min_history, shortlist
            )
            key = f"{country.lower()}::{item_name.lower()}"
            checkpoint["completed"][key] = result
            _save_json_atomic(CHECKPOINT, checkpoint)
            _print_result(result, max_depth)
    else:
        # Item-level parallelism is deliberate: each process gets independent
        # read-only analysis state and avoids shared mutable model caches.
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    run_item,
                    country,
                    item_name,
                    max_depth,
                    min_history,
                    shortlist,
                ): (country, item_name)
                for country, item_name in pending
            }

            for future in as_completed(futures):
                country, item_name = futures[future]
                key = f"{country.lower()}::{item_name.lower()}"
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "country": country,
                        "item_name": item_name,
                        "status": "error",
                        "error": repr(exc),
                    }

                checkpoint["completed"][key] = result
                _save_json_atomic(CHECKPOINT, checkpoint)
                _print_result(result, max_depth)

    checkpoint["finished_at"] = int(time.time())
    _save_json_atomic(CHECKPOINT, checkpoint)
    _save_json_atomic(REPORT, checkpoint)

    print(f"Finished. Report: {REPORT}", flush=True)
    print(f"Checkpoint: {CHECKPOINT}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Optimized, checkpointed, parallel offline projection tournament."
    )
    parser.add_argument(
        "--countries",
        nargs="+",
        default=None,
        help=(
            "Optional filter for flower/plushie countries. "
            "Omit to test flowers and plushies from every country in the DB. "
            "Xanax is always limited to CAN/UNI/JAP."
        ),
    )
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--min-history", type=int, default=8)
    parser.add_argument("--shortlist", type=int, default=10)
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(4, (os.cpu_count() or 2) // 2)),
        help="Parallel items. Default uses at most half the CPU threads, capped at 4.",
    )
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    run_suite(
        (
            tuple(c.lower() for c in args.countries)
            if args.countries
            else None
        ),
        max_depth=max(1, args.depth),
        min_history=max(3, args.min_history),
        shortlist=max(3, args.shortlist),
        workers=max(1, args.workers),
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
