import argparse, json, statistics, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from services.projection_engine_v4 import build_item_context
from services.projection_engine_v6 import (
    DECLARATION_THRESHOLDS, evaluate_arrival_state, item_class,
    selective_rank_key, structural_configs, target_success,
)
from services.projection_overnight_v5 import (
    _baseline_stage, _rank, _spacing_stage, _top_baseline_pairs, discover_items,
)

CHECKPOINT = Path("data/projection_overnight_v6_checkpoint.json")
REPORT = Path("data/projection_overnight_v6_report.json")
SCHEMA_VERSION = "projection-overnight-v6-selective-arrival-v1"


def _key(e):
    return (e["strategy"].lifetime, e["strategy"].wait)


def _family(wait):
    if wait.startswith("direct:"): return "direct_horizon"
    if wait.startswith("spacing["): return "direct_spacing"
    if wait.startswith("hybrid"): return "hybrid"
    return "decomposition"


def _select_points(entries, shortlist, max_depth):
    chosen = {}
    per_depth = max(2, min(4, shortlist))
    for depth in range(1, max_depth + 1):
        ranked = _rank(
            entries, lambda e, d=depth: e["train_by_depth"].get(d), depth=depth
        )
        for e, _ in ranked[:per_depth]:
            chosen[_key(e)] = e
    return list(chosen.values())


def _ensemble(entries, cache, max_depth, top_n):
    out = {}
    for depth in range(1, max_depth + 1):
        ranked = _rank(
            entries, lambda e, d=depth: e["train_by_depth"].get(d), depth=depth
        )
        members = [e for e, _ in ranked[:top_n]]
        maps = [
            {(int(r["anchor_timestamp"]), int(r["depth"])): r
             for r in cache[_key(e)] if int(r["depth"]) == depth}
            for e in members
        ]
        if len(maps) < 2: continue
        common = set(maps[0])
        for m in maps[1:]: common &= set(m)
        for k in common:
            rs = [m[k] for m in maps]
            row = dict(rs[0])
            row["raw_predicted_restock_timestamp"] = statistics.median(
                float(r["raw_predicted_restock_timestamp"]) for r in rs
            )
            row["lifetime_estimate_seconds"] = statistics.median(
                float(r["lifetime_estimate_seconds"]) for r in rs
            )
            row["wait_estimate_seconds"] = statistics.median(
                float(r["wait_estimate_seconds"]) for r in rs
            )
            row["wait_component_error_seconds"] = None
            row["lifetime_component_error_seconds"] = None
            row["direct_horizon_error_seconds"] = (
                float(row["actual_restock_timestamp"])
                - float(row["raw_predicted_restock_timestamp"])
            )
            out[k] = row
    return [out[k] for k in sorted(out)]


def _brief(c, depth, threshold):
    scores = c["evaluation"]["scores_by_threshold"][str(threshold)]
    return {
        "point_model": c["point_model"],
        "forecast_family": c["family"],
        "arrival_state_config": c["config"],
        "declaration_threshold": threshold,
        "train": scores["train_by_depth"].get(depth),
        "holdout": scores["holdout_by_depth"].get(depth),
        "rolling_train_folds": scores["rolling_folds_by_depth"].get(depth) or [],
    }


def _rank_candidate(c, depth, threshold, target):
    scores = c["evaluation"]["scores_by_threshold"][str(threshold)]
    return selective_rank_key(
        scores["train_by_depth"].get(depth), target,
        scores["rolling_folds_by_depth"].get(depth) or [],
    )


def _oracle(candidates, depth):
    best = None
    for c in candidates:
        for threshold in DECLARATION_THRESHOLDS:
            s = c["evaluation"]["scores_by_threshold"][str(threshold)][
                "holdout_by_depth"
            ].get(depth)
            if not s or not s.get("declared_n"): continue
            k = (
                s.get("declared_hit_rate") or 0,
                s.get("coverage") or 0,
                s.get("declared_n") or 0,
            )
            if best is None or k > best[0]:
                best = (k, _brief(c, depth, threshold))
    return best[1] if best else None


def run_item(country, item_name, max_depth=5, min_history=8, shortlist=4):
    started = time.time()
    ctx = build_item_context(
        country, item_name, max_depth=max_depth, min_history=min_history
    )
    if ctx.split_timestamp is None:
        return {"country": country, "item_name": item_name,
                "status": "insufficient_holdout_history",
                "valid_cycles": len(ctx.cycles)}

    baseline, bc = _baseline_stage(ctx)
    seeds = _top_baseline_pairs(baseline, max(4, shortlist), max_depth)
    spacing, sc = _spacing_stage(ctx, seeds)
    combined, cache = baseline + spacing, {**bc, **sc}

    sources = []
    for e in _select_points(combined, shortlist, max_depth):
        life, wait = _key(e)
        sources.append((f"{life} + {wait}", _family(wait), cache[(life, wait)]))
    for n in (3, 5):
        rows = _ensemble(combined, cache, max_depth, n)
        if rows: sources.append((f"depthwise_ensemble{n}", "ensemble", rows))

    thresholds = (0.0,) + tuple(DECLARATION_THRESHOLDS)
    candidates = []
    for label, family, rows in sources:
        for cfg in structural_configs():
            candidates.append({
                "point_model": label, "family": family, "config": cfg.label,
                "evaluation": evaluate_arrival_state(
                    ctx, rows, cfg, thresholds=thresholds
                ),
            })

    target = target_success(item_name)
    result = {
        "country": country, "item_name": item_name,
        "item_class": item_class(item_name),
        "target_declared_success": target, "status": "complete",
        "valid_cycles": len(ctx.cycles),
        "runtime_seconds": round(time.time() - started, 3),
        "point_models_tested": len(sources),
        "arrival_state_candidates": len(candidates), "depths": {},
    }

    for depth in range(1, max_depth + 1):
        ranked = []
        for c in candidates:
            for t in DECLARATION_THRESHOLDS:
                ranked.append((_rank_candidate(c, depth, t, target), c, t))
        ranked.sort(key=lambda x: x[0], reverse=True)
        result["depths"][str(depth)] = {
            "selected_on_training": (
                _brief(ranked[0][1], depth, ranked[0][2]) if ranked else None
            ),
            "top5_selected_on_training": [
                _brief(c, depth, t) for _, c, t in ranked[:5]
            ],
            "oracle_holdout_ceiling_DIAGNOSTIC_ONLY": _oracle(candidates, depth),
        }
    return result


def _load(path):
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except Exception:
        return None


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _print(r):
    print(f"{r['country'].upper()} / {r['item_name']} cycles={r.get('valid_cycles')} "
          f"runtime={r.get('runtime_seconds',0)/60:.1f}m", flush=True)
    if r.get("status") != "complete":
        print("  " + r.get("status","error"), flush=True)
        if r.get("error"): print("  " + r["error"], flush=True)
        return
    for d, block in r["depths"].items():
        w, target = block["selected_on_training"], r["target_declared_success"]
        s = (w or {}).get("holdout") or {}
        if s.get("declared_hit_rate") is None:
            print(f"  D{d} NO HOLDOUT DECLARATIONS target={target*100:.0f}%", flush=True)
            continue
        print(
            f"  D{d} {w['forecast_family']} {w['point_model']} | "
            f"declared={s['declared_hit_rate']*100:.1f}% "
            f"coverage={s['coverage']*100:.1f}% n={s['declared_n']} "
            f"LCB95={(s['declared_wilson_lower_95'] or 0)*100:.1f}% "
            f"gate={w['declaration_threshold']*100:.1f}% "
            f"target={target*100:.0f}%", flush=True
        )


def run_suite(max_depth=5, min_history=8, shortlist=4, workers=4, resume=True):
    cp = _load(CHECKPOINT) if resume else None
    if not cp or cp.get("schema_version") != SCHEMA_VERSION:
        cp = {"schema_version": SCHEMA_VERSION, "completed": {},
              "started_at": int(time.time())}
    items = discover_items()
    pending = [
        x for x in items
        if cp["completed"].get(f"{x[0]}::{x[1].lower()}",{}).get("status")
        != "complete"
    ]
    print(f"V6 selective-arrival tournament: {len(items)} total, "
          f"{len(pending)} pending, workers={workers}", flush=True)
    print("Targets: plushies 90%, Xanax 75%, flowers 80%; holdout selection-blind.",
          flush=True)

    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {
            pool.submit(run_item, c, i, max_depth, min_history, shortlist):(c,i)
            for c,i in pending
        }
        for f in as_completed(jobs):
            c,i = jobs[f]; key=f"{c}::{i.lower()}"
            try: r=f.result()
            except Exception as exc:
                r={"country":c,"item_name":i,"status":"error",
                   "error":repr(exc),"traceback":traceback.format_exc()}
            cp["completed"][key]=r; _save(CHECKPOINT,cp); _print(r)

    cp["finished_at"]=int(time.time())
    _save(CHECKPOINT,cp); _save(REPORT,cp)
    print(f"Finished: {REPORT}", flush=True)


def main():
    p=argparse.ArgumentParser(description="V6 selective arrival-state tournament")
    p.add_argument("--depth",type=int,default=5)
    p.add_argument("--min-history",type=int,default=8)
    p.add_argument("--shortlist",type=int,default=4)
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--no-resume",action="store_true")
    p.add_argument("--item-country"); p.add_argument("--item-name")
    a=p.parse_args()
    if a.item_country or a.item_name:
        if not (a.item_country and a.item_name):
            p.error("--item-country and --item-name must be supplied together")
        r=run_item(a.item_country.lower(),a.item_name,max(2,a.depth),
                   max(3,a.min_history),max(2,a.shortlist))
        _print(r); return
    run_suite(max(2,a.depth),max(3,a.min_history),max(2,a.shortlist),
              max(1,a.workers),not a.no_resume)


if __name__=="__main__":
    main()
