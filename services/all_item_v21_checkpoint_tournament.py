"""Checkpointed all-item V21 corrected-truth challenger tournament.

Conserves CPU by retaining >=90% corrected V19 incumbents unless --include-strong
is requested. Seeds the ten completed V21 items. Does not change V19, V20,
existing V21 files, production routes, or website.

Items with historical max below the configured >=30 target are not modeled as
failures: mark quantity-unreachable. Items with <6 cycles are not wastefully
retested by the same cycle model; they need an availability/sparse model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from collections import Counter
from dataclasses import replace
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from services.remaining_item_v21 import _corrected_worker

SPECIALIZED = {"jap:Xanax"}
CHECKPOINT_SCHEMA = "all-item-v21-checkpoint-v1"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _v19_rates(audit):
    reports = audit.get("masters") or []
    if not reports:
        raise ValueError("V19 truth audit has no masters")
    v19 = next((r for r in reports if "v19" in str(r.get("master", "")).lower()), reports[0])
    return {x["key"]: x for x in v19.get("items", [])}


def _max_qty(db):
    con = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return {f"{c}:{i}": int(q or 0) for c, i, q in con.execute(
            "SELECT country, item_name, MAX(quantity) FROM stock_history "
            "GROUP BY country, item_name")}
    finally:
        con.close()


def _rate(result):
    try:
        return float(result["selected_on_training"]["holdout"]["arrival_success_rate"])
    except (KeyError, TypeError, ValueError):
        return None


def plan(v19, audit, seed, quantities, threshold, min_cycles, min_qty, include_strong):
    rates = _v19_rates(audit)
    plan_rows = []
    for key, incumbent in sorted((v19.get("results") or {}).items()):
        old = rates.get(key, {})
        status = incumbent.get("status")
        cycles = int(incumbent.get("cycles") or 0)
        observed_max = quantities.get(key)
        if key in SPECIALIZED:
            category = "specialized_champion_pending"
        elif key in (seed.get("results") or {}) and (seed["results"][key].get("status") == "complete"):
            category = "existing_v21_seed"
        elif observed_max is None or observed_max < min_qty:
            category = "threshold_not_observed"
        elif cycles < min_cycles:
            category = "needs_sparse_availability_model"
        elif not include_strong and status == "complete" and old.get("corrected_rate", 0.0) >= threshold:
            category = "v19_corrected_incumbent_retained"
        else:
            category = "v21_corrected_tournament"

        plan_rows.append({
            "key": key, "country": key.split(":", 1)[0],
            "item": key.split(":", 1)[1], "category": category,
            "v19_status": status, "v19_cycles": cycles,
            "v19_corrected_rate": old.get("corrected_rate"),
            "historical_max_qty": observed_max,
        })

    # High-impact scoring repairs first, then genuine weak scoring, then new sparse.
    plan_rows.sort(key=lambda r: (
        r["category"] != "v21_corrected_tournament",
        r["v19_status"] != "complete",
        -(r["v19_corrected_rate"] if r["v19_corrected_rate"] is not None else -1),
        r["key"],
    ))
    return plan_rows


def build_leaderboard(report):
    rows = []
    for p in report["plan"]:
        k = p["key"]
        v = (report["results"].get(k) or {})
        v21 = _rate(v) if v.get("status") == "complete" else None
        before = p["v19_corrected_rate"]
        # This is a *candidate overview*, not a matched-cohort champion.
        # Different V19/V21 holdout sessions prevent automatic promotion.
        rows.append({
            "key": k,
            "category": p["category"],
            "v19_corrected_rate": before,
            "v21_rate": v21,
            "v21_status": v.get("status"),
            "v21_config": ((v.get("selected_on_training") or {}).get("config") or {}).get("name"),
            "v21_holdout_n": ((v.get("selected_on_training") or {}).get("holdout") or {}).get("valid_starts"),
            "v21_median_wait_seconds": ((v.get("selected_on_training") or {}).get("holdout") or {}).get("median_wait_seconds"),
            "v21_session_cap_count": sum(bool(r.get("session_cap")) for r in (v.get("holdout_rows") or [])),
            "winner_status": "pending_matched_comparison" if v21 is not None
                else "provisional_v19" if p["category"] == "v19_corrected_incumbent_retained"
                else "needs_different_model_or_threshold",
        })
    return {
        "schema": "all-item-v21-provisional-leaderboard-v1",
        "warning": "V19 and V21 raw holdout rates are not directly comparable. "
                   "Never promote a winner until scored on identical historical starts. "
                   "Natural restock waiting is not an arrival failure. This covers "
                   "travel success, NOT restock timing error / prediction window quality.",
        "totals": {
            "total_keys": len(rows),
            "v21_completed": sum(x["v21_status"] == "complete" for x in rows),
            "v21_ge90": sum(x["v21_rate"] is not None and x["v21_rate"] >= .90 for x in rows),
            "strong_v19_retained": sum(x["category"] == "v19_corrected_incumbent_retained" for x in rows),
            "needs_sparse_availability_model": sum(x["category"] == "needs_sparse_availability_model" for x in rows),
            "threshold_not_observed": sum(x["category"] == "threshold_not_observed" for x in rows),
        },
        "rows": rows,
    }


def _unpenalized_worker(payload):
    """Keep the V19/V20 model code untouched, but eliminate generic hours cost.

    Actual arrival success is still the main scoring objective. Restock length
    is natural; a long wait is not automatically a poor recommendation.
    """
    from services import plushie_flower_dynamic_planner_v19 as planner
    original_configs = planner.configs
    def configs_without_absolute_wait_penalty():
        return [
            replace(c, delay_penalty_per_hour=0.0)
            for c in original_configs()
        ]
    planner.configs = configs_without_absolute_wait_penalty
    try:
        return _corrected_worker(payload)
    finally:
        planner.configs = original_configs


def main():
    ap = argparse.ArgumentParser(description="All-item V21 resumable corrected-truth checkpoint run")
    ap.add_argument("--db", required=True)
    ap.add_argument("--source-master", required=True, help="original V19 master")
    ap.add_argument("--truth-audit", required=True, help="V21 audit of V19")
    ap.add_argument("--seed-master", required=True, help="already finished ten-item corrected_master.json")
    ap.add_argument("--output", default="data/all_item_v21/master.json")
    ap.add_argument("--leaderboard", default="data/all_item_v21/leaderboard.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--include-strong", action="store_true")
    ap.add_argument("--retry-errors", action="store_true")
    ap.add_argument("--threshold", type=float, default=.90)
    ap.add_argument("--min-qty", type=int, default=30)
    ap.add_argument("--grace-seconds", type=int, default=10)
    ap.add_argument("--min-cycles", type=int, default=6)
    ap.add_argument("--max-wait-hours", type=int, default=12)
    ap.add_argument("--replan-step-seconds", type=int, default=900)
    ap.add_argument("--departure-grid-seconds", type=int, default=900)
    ap.add_argument("--expected-db-sha256",
                    default="9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761")
    ap.add_argument("--limit", type=int, default=0, help="run only first N new targets (smoke/checkpoint)")
    args = ap.parse_args()
    if args.workers < 1 or args.workers > 24:
        ap.error("--workers must be in 1..24")

    paths = [Path(p).resolve() for p in
             [args.db, args.source_master, args.truth_audit, args.seed_master]]
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"Missing file: {path}")
    db, src, audit_file, seed_file = paths
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    if sha.lower() != args.expected_db_sha256.lower():
        raise SystemExit(f"Frozen database checksum mismatch: {sha}")

    source, audit, seed = _load(src), _load(audit_file), _load(seed_file)
    if audit.get("db_sha256", "").lower() != sha.lower():
        raise SystemExit("Truth audit does not match frozen database")
    if seed.get("schema") != "remaining-item-v21-corrected-challenger-v1":
        raise SystemExit("Seed is not a V21 corrected tournament master")
    opts = {
        "min_qty": args.min_qty, "grace": args.grace_seconds,
        "holdout_fraction": .25, "topn": 3, "history_step": 600,
        "replan_step": args.replan_step_seconds, "eval_step": 1800,
        "departure_grid": args.departure_grid_seconds,
        "max_wait": args.max_wait_hours * 3600, "min_cycles": args.min_cycles,
        "min_points": 60, "min_starts": 40,
    }
    settings = {
        "sha256": sha, "threshold": args.threshold,
        "min_qty": args.min_qty, "grace_seconds": args.grace_seconds,
        "min_cycles": args.min_cycles,
        "include_strong": args.include_strong, "options": opts,\n        "absolute_wait_penalty_disabled": True,
    }
    plan_rows = plan(source, audit, seed, _max_qty(db),
                     args.threshold, args.min_cycles, args.min_qty,
                     args.include_strong)
    output = Path(args.output)
    if args.resume and output.exists():
        master = _load(output)
        if master.get("schema") != CHECKPOINT_SCHEMA or master.get("settings") != settings:
            raise SystemExit("Existing checkpoint uses different settings. Don't mix runs.")
        print(f"RESUMING existing results={len(master['results'])}", flush=True)
    else:
        if output.exists():
            raise SystemExit("Output exists: specify --resume; no destructive overwrite")
        master = {
            "schema": CHECKPOINT_SCHEMA,
            "created_at": int(time.time()), "settings": settings,
            "v19_master": str(src), "v21_seed": str(seed_file),
            "truth_audit": str(audit_file), "plan": plan_rows,
            "results": {}, "last_checkpoint_timestamp": None,
            "warning": "Offline arrival-success research. No live deployment. "
                       "Forecast drop-time/window accuracy not evaluated. "
                       "12h max wait does NOT imply a natural restock wait is bad.",
        }
        for key, result in (seed.get("results") or {}).items():
            if result.get("status") == "complete":
                master["results"][key] = result
        _atomic_save(output, master)

    tally = Counter(p["category"] for p in master["plan"])
    pending = []
    for p in master["plan"]:
        if p["category"] != "v21_corrected_tournament":
            continue
        previous = master["results"].get(p["key"])
        if previous is not None and (not args.retry_errors or previous.get("status") != "error"):
            continue
        pending.append({"key": p["key"], "db": str(db), "opts": opts})
    if args.limit > 0:
        pending = pending[:args.limit]
    print(f"V21 ALL ITEMS={len(master['plan'])} CATEGORIES={dict(tally)} "
          f"SEED/COMPLETED={len(master['results'])} PENDING={len(pending)} "
          f"WORKERS={args.workers}", flush=True)

    def save(key, result):
        master["results"][key] = result
        master["last_checkpoint_timestamp"] = int(time.time())
        _atomic_save(output, master)
        _atomic_save(args.leaderboard, build_leaderboard(master))
        summary = (result.get("selected_on_training") or {}).get("holdout") or {}
        print(f"DONE {len(master['results'])}/{len(master['plan'])} {key} "
              f"status={result.get('status')} cycles={result.get('cycles')} "
              f"corrected_success={summary.get('arrival_success_rate')} "
              f"median_wait_s={summary.get('median_wait_seconds')}", flush=True)

    if not pending:
        _atomic_save(args.leaderboard, build_leaderboard(master))
        print("No new candidates to calculate; leaderboard refreshed", flush=True)
        return

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        # Submit only as many tasks as workers, so a crash loses at most
        # currently running items and next restart resumes everything else.
        inflight = {}
        cursor = iter(pending)
        def submit():
            try:
                payload = next(cursor)
            except StopIteration:
                return False
            inflight[pool.submit(_unpenalized_worker, payload)] = payload["key"]
            return True
        for _ in range(args.workers):
            if not submit():
                break
        while inflight:
            ready, _ = wait(inflight, return_when=FIRST_COMPLETED)
            for future in ready:
                key = inflight.pop(future)
                try:
                    returned_key, result = future.result()
                    if returned_key != key:
                        raise RuntimeError(f"Item mismatch: {key} != {returned_key}")
                except Exception as e:
                    result = {"status": "error", "error": repr(e)}
                save(key, result)
                submit()

    print(f"WROTE {output} and {args.leaderboard}", flush=True)


if __name__ == "__main__":
    main()
