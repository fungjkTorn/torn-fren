"""Resumable all-country V21 research tournament, seeded by corrected V19/V21.

This script NEVER modifies V19, V20, existing V21, live API, or Discord.
Historical holdout is for provisional candidate comparison, NOT an unbiased
estimate after champion selection. Genuine natural restock waits are free;
do not rank models by raw delay at the expense of successful arrivals.

Usage: python -u -m services.all_item_v21_checkpoint run --db ... --v19 ... --audit ... --seed-v21 ... --workers 2 --resume
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from dataclasses import replace

from services.remaining_item_v21 import (
    _corrected_worker, load_clean_item, load_gaps, observed_arrival_success,
)
from services.arrival_success_lab import TRAVEL_SECONDS

SCHEMA = "all-item-v21-corrected-checkpoint-v1"
DEFAULT_OUTPUT = "data/all_item_v21/full_master.json"
SPECIALIZED_EXCLUDED = {"jap:Xanax"}
# The legacy and V21 training-selected models have different validation regimes.
# Comparing on common dates does not create an unbiased final model score.
MIN_PAIRED = 30


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic(path, data):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".writing")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, dest)


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sources(args):
    db = Path(args.db).resolve()
    v19 = Path(args.v19).resolve()
    audit = Path(args.audit).resolve()
    for p in (db, v19, audit):
        if not p.is_file():
            raise SystemExit(f"Required input not found: {p}")
    prior = _json(v19)
    truth = _json(audit)
    expected = truth.get("db_sha256")
    actual = _digest(db)
    if actual != expected:
        raise SystemExit("STOP: database is different from V19 corrected audit. "
                         f"DB={actual} AUDIT={expected}")
    if truth.get("quantity_threshold") != args.min_qty or truth.get("grace_seconds") != args.grace_seconds:
        raise SystemExit("STOP: threshold/grace must match the V19 truth audit")
    seeds = {}
    if args.seed_v21 and Path(args.seed_v21).exists():
        seeds = (_json(args.seed_v21).get("results") or {})
    return db, prior, truth, seeds, actual


def _truth_map(audit):
    return {
        item["key"]: item
        for master in audit.get("masters", [])
        for item in master.get("items", [])
    }


def _catalog(db, prior, truth, seeds, args):
    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    try:
        catalog = {}
        corrected = _truth_map(truth)
        for key, old in sorted((prior.get("results") or {}).items()):
            if ":" not in key:
                continue
            country, item = key.split(":", 1)
            max_qty = conn.execute(
                "SELECT MAX(quantity) FROM stock_history WHERE country=? AND item_name=?",
                (country, item),
            ).fetchone()[0]
            baseline = corrected.get(key)
            rate = baseline.get("corrected_rate") if baseline else None
            scarce_qty = max_qty is not None and max_qty < args.min_qty
            strong = old.get("status") == "complete" and rate is not None and rate >= .90
            if key in SPECIALIZED_EXCLUDED:
                phase, reason = "specialist", "Japan Xanax has its own model research"
            elif scarce_qty:
                phase, reason = "quantity_limited", f"Recorded max {max_qty} < target {args.min_qty}"
            elif key in seeds and seeds[key].get("status") == "complete":
                phase, reason = "seeded", "Previously completed corrected V21 challenger"
            elif strong and not args.retest_strong:
                phase, reason = "incumbent", "Corrected V19 >=90%; skip redundant retest"
            elif old.get("status") != "complete":
                phase, reason = "sparse", "V19 insufficient; attempt lower-cycle V21"
            elif rate is not None and rate < .60:
                phase, reason = "weak", "Corrected V19 <60%"
            elif rate is not None and rate < .90:
                phase, reason = "moderate", "Corrected V19 60–90%"
            else:
                phase, reason = "strong_retest", "Optional corrected re-selection"
            catalog[key] = {
                "phase": phase, "reason": reason,
                "v19_status": old.get("status"), "v19_corrected_rate": rate,
                "v19_cycles": old.get("cycles"),
                "observed_max_quantity": max_qty,
                "target_quantity": args.min_qty,
            }
        return catalog
    finally:
        conn.close()


def _clean_truth(conn, gaps, key, cache):
    if key not in cache:
        country, item = key.split(":", 1)
        rows = load_clean_item(conn, country, item)
        cache[key] = ([r[0] for r in rows], [r[1] for r in rows])
    return cache[key]


def _rows_by_start(result):
    return {int(r["start"]): r for r in result.get("holdout_rows", [])}


def _observations(result, times, qtys, gaps, min_qty, grace):
    ret = {}
    for t, r in _rows_by_start(result).items():
        val = observed_arrival_success(times, qtys, gaps, r["arrival"], min_qty, grace)
        if val is None:
            continue
        ret[t] = {"success": bool(val), "wait_seconds": max(0., float(r["departure"])-t),
                  "departure": float(r["departure"]), "arrival": float(r["arrival"])}
    return ret


def _head_to_head(old, new, *, min_paired=MIN_PAIRED):
    common = sorted(set(old) & set(new))
    if not common:
        return {"matched": 0, "eligible": False}
    old_hits = sum(old[t]["success"] for t in common)
    new_hits = sum(new[t]["success"] for t in common)
    old_wait = statistics.median(old[t]["wait_seconds"] for t in common)
    new_wait = statistics.median(new[t]["wait_seconds"] for t in common)
    return {
        "matched": len(common),
        "eligible": len(common) >= min_paired,
        "v19_hits": old_hits, "v21_hits": new_hits,
        "v19_rate": old_hits / len(common), "v21_rate": new_hits / len(common),
        "v19_median_wait_seconds": old_wait,
        "v21_median_wait_seconds": new_wait,
        "v21_only_successes": sum(new[t]["success"] and not old[t]["success"] for t in common),
        "v19_only_successes": sum(old[t]["success"] and not new[t]["success"] for t in common),
    }


def _immediate_baseline(times, qtys, gaps, travel, min_qty, grace, starts):
    valid = hits = 0
    for start in starts:
        ans = observed_arrival_success(times, qtys, gaps, start + travel, min_qty, grace)
        if ans is None:
            continue
        valid += 1
        hits += bool(ans)
    return {"sessions": valid, "successes": hits, "rate": hits/valid if valid else None,
            "method": "depart_immediately; does not forecast next restock",
            "causal_decision": True, "selection_status": "research_only"}


def _sparse_starts(times, travel):
    if not times:
        return []
    lower = times[0] + int(.75 * (times[-1] - times[0]))
    upper = times[-1] - travel - 10
    if upper <= lower:
        return []
    # Same half-hour decision grid, chronologically final quarter.
    starts = list(range(((lower+1799)//1800)*1800, upper+1, 1800))
    if len(starts) > 250:
        step = max(1, (len(starts)+249)//250)
        starts = starts[::step]
    return starts


def _item_decision(key, prior, results, entry, conn, gaps, cache, args):
    times, qtys = _clean_truth(conn, gaps, key, cache)
    old = (prior.get("results") or {}).get(key) or {}
    challenger = results.get(key) or {}
    old_scored = _observations(old, times, qtys, gaps, args.min_qty, args.grace_seconds)
    new_scored = _observations(challenger, times, qtys, gaps, args.min_qty, args.grace_seconds)
    paired = _head_to_head(old_scored, new_scored)
    travel = TRAVEL_SECONDS.get(key.split(":", 1)[0])
    if travel is None:
        immediate = {"sessions": 0, "rate": None, "reason": "no flight duration"}
    else:
        # Use shared holdout starts if comparison is possible. Otherwise use
        # the best available chronological holdout, or build a sparse holdout.
        starts = (sorted(set(old_scored) & set(new_scored))
                  if paired["matched"] else sorted(old_scored or new_scored))
        if not starts:
            starts = _sparse_starts(times, travel)
        immediate = _immediate_baseline(times, qtys, gaps, travel,
                                         args.min_qty, args.grace_seconds, starts)

    old_rate = sum(r["success"] for r in old_scored.values())/len(old_scored) if old_scored else None
    new_rate = sum(r["success"] for r in new_scored.values())/len(new_scored) if new_scored else None
    if entry["phase"] == "quantity_limited":
        winner = "quantity_infeasible_at_30"
        reason = "Historical max quantity below 30; choose actual carrying target later"
    elif key in SPECIALIZED_EXCLUDED:
        winner, reason = "specialist_pending", "Japan Xanax requires its independent model"
    elif paired["eligible"]:
        # Model changes should deliver a meaningful paired success benefit.
        # On exact success ties, choose the earlier successful departure.
        net = paired["v21_hits"] - paired["v19_hits"]
        if net >= 3 and paired["v21_rate"] >= paired["v19_rate"] + .02:
            winner, reason = "v21_corrected", "At least three extra matched successes and >=2pp improvement"
        elif net == 0 and paired["v21_median_wait_seconds"] + 900 < paired["v19_median_wait_seconds"]:
            winner, reason = "v21_corrected", "Equal matched arrival success with materially shorter wait"
        else:
            winner, reason = "v19_corrected", "V19 wins/ties matched arrival success without later departure"
    elif old_rate is not None:
        winner, reason = "v19_corrected", "No sufficient paired evidence to replace established incumbent"
    elif new_rate is not None:
        winner, reason = "v21_corrected", "No V19 evaluated model; V21 is provisional"
    elif immediate["sessions"] >= 30 and immediate["rate"] is not None and immediate["rate"] >= .70:
        winner, reason = "depart_now_baseline", "Promising observed availability; no qualified cycle model"
    elif immediate["sessions"] >= 30:
        winner, reason = "best_effort_sparse", "Low-scoring immediate fallback, NOT a validated champion"
    else:
        winner, reason = "unresolved_sparse", "No well-evaluated model; retain live V2 forecast fallback"

    return {
        "model_candidate": winner, "selection_reason": reason,
        "promotion_status": "research_only_not_live_ready",
        "warning": "Selection viewed historical holdout. Revalidate on later unseen or shadow sessions.",
        "v19_sessions": len(old_scored), "v19_corrected_success": old_rate,
        "v21_sessions": len(new_scored), "v21_corrected_success": new_rate,
        "matched_comparison": paired,
        "immediate_baseline": immediate,
        "restock_forecast_validated": False,
        "natural_wait_penalty": 0,
        "wait_interpretation": "long waits are not failures; count avoidable skipped opportunities separately",
    }


def _options(args):
    return {
        "min_qty": args.min_qty, "grace": args.grace_seconds,
        "holdout_fraction": .25, "topn": args.topn,
        "history_step": 600, "replan_step": args.replan_step_seconds,
        "eval_step": 1800, "departure_grid": args.departure_grid_seconds,
        "max_wait": args.max_wait_hours * 3600,
        "min_cycles": args.min_cycles, "min_points": 60,
        "min_starts": 40,
    }


def _report(state, prior, conn, gaps, args, cache, changed_key=None):
    decisions = state.setdefault("winners", {})
    if changed_key is not None and len(decisions) == len(state["catalog"]):
        decisions[changed_key] = _item_decision(
            changed_key, prior, state["results"], state["catalog"][changed_key],
            conn, gaps, cache, args,
        )
    else:
        for key, entry in state["catalog"].items():
            decisions[key] = _item_decision(key, prior, state["results"], entry,
                                           conn, gaps, cache, args)
    phase_counts = {}
    winner_counts = {}
    for k, e in state["catalog"].items():
        p = e["phase"]
        phase_counts[p] = phase_counts.get(p, 0) + 1
    for d in decisions.values():
        w = d["model_candidate"]
        winner_counts[w] = winner_counts.get(w, 0) + 1
    state["summary"] = {
        "catalog_items": len(decisions),
        "v21_challengers_complete": sum(
            r.get("status") == "complete" for r in state["results"].values()
        ),
        "v21_items_attempted": len(state["results"]),
        "phase_counts": phase_counts,
        "provisional_candidate_counts": winner_counts,
        "overall_status": "research_only; requires V20 match, restock metrics, independent shadow validation",
    }


def _restock_neutral_worker(payload):
    """Use corrected V21 scoring without subtracting a flat cost per wait hour.

    This overrides model candidate utility only inside this subprocess.
    Successful long waits for naturally slow restocks remain successes.
    """
    from services import plushie_flower_dynamic_planner_v19 as planner
    original = planner.configs
    def neutral_configs():
        return [replace(c, delay_penalty_per_hour=0.0) for c in original()]
    planner.configs = neutral_configs
    try:
        return _corrected_worker(payload)
    finally:
        planner.configs = original


def main():
    ap = argparse.ArgumentParser(description="V21 all-item corrected checkpoint tournament")
    ap.add_argument("action", choices=("run", "report"))
    ap.add_argument("--db", required=True)
    ap.add_argument("--v19", default="data/all_item_v19/master.json")
    ap.add_argument("--audit", default="data/remaining_item_v21/truth_audit.json")
    ap.add_argument("--seed-v21", default="data/remaining_item_v21/corrected_master.json")
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--retry-failures", action="store_true")
    ap.add_argument("--retest-strong", action="store_true")
    ap.add_argument("--max-new", type=int, default=0, help="0=all; positive=limit new item attempts this run")
    ap.add_argument("--min-qty", type=int, default=30)
    ap.add_argument("--grace-seconds", type=int, default=10)
    ap.add_argument("--max-wait-hours", type=int, default=12)
    ap.add_argument("--replan-step-seconds", type=int, default=900)
    ap.add_argument("--departure-grid-seconds", type=int, default=900)
    ap.add_argument("--min-cycles", type=int, default=6)
    ap.add_argument("--topn", type=int, default=3)
    a = ap.parse_args()
    if a.workers < 1 or a.max_new < 0:
        raise SystemExit("workers >=1 and max-new >=0 required")
    db, prior, truth, seeds, db_sha = _sources(a)
    out = Path(a.output)
    settings = {
        "db_sha256": db_sha, "v19_sha256": _digest(a.v19),
        "audit_sha256": _digest(a.audit),
        "seed_v21_sha256": _digest(a.seed_v21) if a.seed_v21 and Path(a.seed_v21).exists() else None,
        "min_qty": a.min_qty, "grace_seconds": a.grace_seconds,
        "options": _options(a),
        "per_hour_wait_penalty": 0.0,
    }
    if out.exists() and a.resume:
        state = _json(out)
        if state.get("settings") != settings or state.get("schema") != SCHEMA:
            raise SystemExit("STOP: resume settings differ from checkpoint; use original settings/output")
        state.setdefault("results", {})
    else:
        if out.exists():
            raise SystemExit("Output exists; use --resume or new --output (won't overwrite)")
        state = {
            "schema": SCHEMA, "created_at": int(time.time()), "settings": settings,
            "catalog": _catalog(db, prior, truth, seeds, a), "results": {},
            "winners": {}, "summary": {},
            "note": "V19/seed V21 are read-only. Separate from V20; no live deployment.",
        }
    for key, r in seeds.items():
        if key in state["catalog"] and key not in state["results"]:
            state["results"][key] = r

    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    gaps = load_gaps(conn)
    truth_cache = {}

    def checkpoint(changed_key=None):
        _report(state, prior, conn, gaps, a, truth_cache, changed_key)
        state["updated_at"] = int(time.time())
        _atomic(out, state)
        print("CHECKPOINT items_attempted={}/{} completed={} candidates={} saved={}".format(
            state["summary"]["v21_items_attempted"],
            state["summary"]["catalog_items"],
            state["summary"]["v21_challengers_complete"],
            state["summary"]["provisional_candidate_counts"],
            out,
        ), flush=True)

    try:
        checkpoint()
        if a.action == "report":
            return
        order = {"weak":0, "moderate":1, "sparse":2, "strong_retest":3}
        keys = sorted(
            (k for k, info in state["catalog"].items() if info["phase"] in order),
            key=lambda k: (order[state["catalog"][k]["phase"]], k),
        )
        pending = [
            k for k in keys if (
                k not in state["results"] or (
                    a.retry_failures and state["results"][k].get("status") != "complete"
                )
            )
        ]
        if a.max_new:
            pending = pending[:a.max_new]
        print("V21 FULL CATALOG={} pending={} seeded={} workers={} "
              "V19 strong incumbents preserved; V20 untouched".format(
                  len(state["catalog"]), len(pending), len(seeds), a.workers,
              ), flush=True)
        opts = _options(a)
        inputs = [{"key":key, "db":str(db), "opts":opts} for key in pending]
        completed = 0

        def store(key, result):
            nonlocal completed
            state["results"][key] = result
            completed += 1
            hold = (result.get("selected_on_training") or {}).get("holdout") or {}
            print("DONE {}/{} {} status={} success={} cycles={}".format(
                completed, len(pending), key, result.get("status"),
                hold.get("arrival_success_rate"), result.get("cycles"),
            ), flush=True)
            # Durable crash-safe checkpoint after EVERY item.
            checkpoint(key)

        if a.workers == 1:
            for inp in inputs:
                store(*_restock_neutral_worker(inp))
        else:
            with ProcessPoolExecutor(max_workers=a.workers) as executor:
                all_futures = {
                    executor.submit(_restock_neutral_worker, inp): inp["key"]
                    for inp in inputs
                }
                unfinished = set(all_futures)
                while unfinished:
                    done, unfinished = wait(unfinished, timeout=60, return_when=FIRST_COMPLETED)
                    for fut in done:
                        key = all_futures[fut]
                        try:
                            k, r = fut.result()
                        except Exception as exc:
                            k, r = key, {"status":"error", "error":repr(exc)}
                        store(k, r)
                    if unfinished and not done:
                        print("HEARTBEAT done={} running_or_queued={}".format(
                            completed, len(unfinished)), flush=True)
        checkpoint()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
