import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from services.projection_grand_tournament_v7_engine import (
    ARRIVAL_FRACTIONS,
    MIN_STOCK,
    SHORT_WAIT_SECONDS,
    GrandConfig,
    build_examples,
    config_grid,
    period_active,
    point_rows_for_base,
    rolling_folds,
    score_fraction_rows,
    summarize,
)
from services.projection_overnight_v5 import discover_items


SCHEMA = "grand-tournament-v7-safe-stock-30-v1"
DEFAULT_REPORT = Path("data/projection_grand_tournament_v7_report.json")
DEFAULT_CHECKPOINT = Path("data/projection_grand_tournament_v7_checkpoint.json")


def _rank(summary, folds):
    if not summary or summary.get("success_30_rate") is None:
        return (-1, -1, -1, -1, -1, -1)
    coverage = summary.get("coverage") or 0.0
    success = summary["success_30_rate"]
    stable = 0
    usable_folds = 0
    for f in folds:
        if (f.get("n") or 0) >= 5 and f.get("success_30_rate") is not None:
            usable_folds += 1
            if f["success_30_rate"] >= 0.80:
                stable += 1
    stability = stable / usable_folds if usable_folds else 0.0

    # No selective abstention: prefer configs that cover essentially every
    # eligible anchor. Then maximize >=30-on-arrival success.
    full_coverage = int(coverage >= 0.95)
    goal = int(full_coverage and success >= 0.90)
    return (
        goal,
        full_coverage,
        success,
        summary.get("wilson_lower_95") or 0.0,
        stability,
        summary.get("success_or_short_wait_rate") or 0.0,
    )


def run_item(country, item_name, max_depth=7, shortlist=30):
    started = time.time()
    ctx, timeline, examples = build_examples(
        country, item_name, max_depth=max_depth, min_history=8
    )
    if ctx.split_timestamp is None:
        return {
            "country": country, "item_name": item_name,
            "status": "insufficient_history",
            "valid_cycles": len(ctx.cycles),
        }

    ranked = []
    bases_tested = 0
    candidates_tested = 0

    for hm, lb, tod, dm, bm in config_grid():
        base_rows = point_rows_for_base(
            ctx, timeline, examples, hm, lb, tod, dm, bm
        )
        if not base_rows:
            continue
        bases_tested += 1

        for fraction in ARRIVAL_FRACTIONS:
            candidates_tested += 1
            rows = score_fraction_rows(ctx, timeline, base_rows, fraction)
            train_active, train_eligible = period_active(ctx, rows, "train")
            train_summary = summarize(train_active, train_eligible)
            folds = rolling_folds(ctx, rows)
            key = _rank(train_summary, folds)
            ranked.append((
                key,
                GrandConfig(hm, lb, tod, dm, fraction, bm),
                train_summary,
                folds,
                rows,
            ))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top = ranked[:max(5, shortlist)]

    finalists = []
    for key, cfg, train_summary, folds, rows in top:
        hold_active, hold_eligible = period_active(ctx, rows, "holdout")
        hold_summary = summarize(hold_active, hold_eligible)
        finalists.append({
            "config": cfg.name,
            "rank_key": list(key),
            "train": train_summary,
            "rolling_train_folds": folds,
            "holdout": hold_summary,
        })

    selected = finalists[0] if finalists else None
    return {
        "schema": SCHEMA,
        "country": country.lower(),
        "item_name": item_name,
        "status": "complete",
        "valid_cycles": len(ctx.cycles),
        "travel_seconds": ctx.travel_seconds,
        "success_definition": f"quantity_on_arrival >= {MIN_STOCK}",
        "short_wait_definition": (
            f"not success on arrival, but quantity reaches >= {MIN_STOCK} "
            f"within {SHORT_WAIT_SECONDS}s"
        ),
        "selection_rule": (
            "No confidence abstention. Select on training only; prefer >=95% "
            "anchor coverage, then >=90% stock-on-arrival success, then raw "
            "success/Wilson/stability. Holdout is reporting only."
        ),
        "base_configs_tested": bases_tested,
        "candidate_configs_tested": candidates_tested,
        "runtime_seconds": round(time.time() - started, 3),
        "selected_on_training": selected,
        "top_finalists": finalists,
    }


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


def _load(path):
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except Exception:
        return None


def _print_result(r):
    if r.get("status") != "complete":
        print(
            f"{r.get('country','?').upper()} / {r.get('item_name','?')}: "
            f"{r.get('status')}", flush=True
        )
        return
    s = r.get("selected_on_training") or {}
    tr = s.get("train") or {}
    ho = s.get("holdout") or {}
    print(
        f"{r['country'].upper()} / {r['item_name']} | "
        f"candidates={r['candidate_configs_tested']:,} | "
        f"train={100*(tr.get('success_30_rate') or 0):.1f}% "
        f"(+short={100*(tr.get('success_or_short_wait_rate') or 0):.1f}%) "
        f"cov={100*(tr.get('coverage') or 0):.1f}% | "
        f"holdout={100*(ho.get('success_30_rate') or 0):.1f}% "
        f"(+short={100*(ho.get('success_or_short_wait_rate') or 0):.1f}%) "
        f"n={ho.get('n') or 0} | {s.get('config')}",
        flush=True,
    )


def run_suite(max_depth=7, workers=6, shortlist=30, resume=True):
    checkpoint = _load(DEFAULT_CHECKPOINT) if resume else None
    if not checkpoint or checkpoint.get("schema") != SCHEMA:
        checkpoint = {
            "schema": SCHEMA,
            "started_at": int(time.time()),
            "completed": {},
        }

    items = discover_items()
    pending = [
        (c, i) for c, i in items
        if checkpoint["completed"].get(f"{c}::{i.lower()}", {}).get("status")
        != "complete"
    ]
    print(
        f"Grand Tournament V7: {len(items)} items, {len(pending)} pending, "
        f"workers={workers}, min_stock={MIN_STOCK}, short_wait={SHORT_WAIT_SECONDS}s",
        flush=True,
    )

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_item, c, i, max_depth, shortlist): (c, i)
            for c, i in pending
        }
        for future in as_completed(futures):
            c, i = futures[future]
            key = f"{c}::{i.lower()}"
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "country": c, "item_name": i,
                    "status": "error", "error": repr(exc),
                }
            checkpoint["completed"][key] = result
            _save(DEFAULT_CHECKPOINT, checkpoint)
            _print_result(result)

    checkpoint["finished_at"] = int(time.time())
    _save(DEFAULT_CHECKPOINT, checkpoint)
    _save(DEFAULT_REPORT, checkpoint)
    print(f"Saved {DEFAULT_REPORT}", flush=True)


def main():
    p = argparse.ArgumentParser(
        description="Grand V7 direct reachable >=30-stock arrival tournament"
    )
    p.add_argument("--depth", type=int, default=7)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--shortlist", type=int, default=30)
    p.add_argument("--no-resume", action="store_true")
    p.add_argument("--item-country")
    p.add_argument("--item-name")
    p.add_argument("--output")
    a = p.parse_args()

    if a.item_country or a.item_name:
        if not (a.item_country and a.item_name):
            p.error("--item-country and --item-name must be supplied together")
        result = run_item(
            a.item_country.lower(), a.item_name,
            max_depth=max(2, a.depth),
            shortlist=max(5, a.shortlist),
        )
        _print_result(result)
        out = Path(
            a.output
            or f"data/projection_grand_v7_{a.item_country.lower()}_"
               f"{a.item_name.lower().replace(' ','_')}.json"
        )
        _save(out, result)
        print(f"Saved {out}", flush=True)
        return

    run_suite(
        max_depth=max(2, a.depth),
        workers=max(1, a.workers),
        shortlist=max(5, a.shortlist),
        resume=not a.no_resume,
    )


if __name__ == "__main__":
    main()
