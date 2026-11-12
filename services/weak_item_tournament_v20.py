from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

from services import history_service
from services.plushie_flower_dynamic_planner_v19 import run_item as run_dynamic_v19


SPECIALIZED = {("jap", "Xanax")}


def _key(country: str, item: str) -> str:
    return f"{country}:{item}"


def _holdout_rate(result: dict) -> float | None:
    try:
        return float(result["selected_on_training"]["holdout"]["arrival_success_rate"])
    except Exception:
        return None


def _targets_from_master(master: dict, threshold: float):
    targets = []
    for key, result in (master.get("results") or {}).items():
        if ":" not in key:
            continue
        country, item = key.split(":", 1)
        if (country, item) in SPECIALIZED:
            continue

        status = result.get("status")
        rate = _holdout_rate(result)
        if status != "complete" or rate is None or rate < threshold:
            targets.append({
                "country": country,
                "item": item,
                "incumbent_status": status,
                "incumbent_holdout_success": rate,
                "incumbent_cycles": result.get("cycles"),
            })
    return targets


def _worker(payload):
    db = Path(payload["db"]).resolve()
    history_service.DB_PATH = db
    history_service._DB_READY = False

    country = payload["country"]
    item = payload["item"]
    opts = payload["opts"]

    t0 = time.time()
    try:
        _c, _i, result = run_dynamic_v19(country, item, **opts)
    except Exception as exc:
        result = {
            "status": "error",
            "country": country,
            "item_name": item,
            "error": repr(exc),
        }
    result["runtime_seconds"] = round(time.time() - t0, 3)
    return country, item, result


def _summary(master, results):
    rows = []
    improved = 0
    newly_modelled = 0
    completed = 0

    for key, challenger in results.items():
        old = (master.get("results") or {}).get(key, {})
        old_rate = _holdout_rate(old)
        new_rate = _holdout_rate(challenger)
        if challenger.get("status") == "complete":
            completed += 1
            if old.get("status") != "complete":
                newly_modelled += 1
            elif old_rate is not None and new_rate is not None and new_rate > old_rate:
                improved += 1
        rows.append({
            "key": key,
            "old_status": old.get("status"),
            "old_cycles": old.get("cycles"),
            "old_holdout_success": old_rate,
            "new_status": challenger.get("status"),
            "new_cycles": challenger.get("cycles"),
            "new_holdout_success": new_rate,
            "delta": (new_rate - old_rate) if new_rate is not None and old_rate is not None else None,
            "config": ((challenger.get("selected_on_training") or {}).get("config") or {}).get("name"),
        })

    rows.sort(
        key=lambda r: (
            r["new_status"] != "complete",
            -(r["delta"] if r["delta"] is not None else -999),
            -(r["new_holdout_success"] if r["new_holdout_success"] is not None else -1),
        )
    )
    return {
        "targeted_items": len(results),
        "completed_challengers": completed,
        "newly_modelled_previous_insufficient": newly_modelled,
        "improved_over_v19_incumbent": improved,
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser(
        description="V20 targeted tournament for weak and insufficient all-item V19 results."
    )
    ap.add_argument("--db", required=True)
    ap.add_argument("--source-master", default="data/all_item_v19/master.json")
    ap.add_argument("--output", default="data/weak_item_v20/master.json")
    ap.add_argument("--threshold", type=float, default=0.80,
                    help="Retest completed items below this V19 holdout success.")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--resume", action="store_true")

    # Sparse-data / weak-item settings.
    ap.add_argument("--min-cycles", type=int, default=6)
    ap.add_argument("--min-points", type=int, default=60)
    ap.add_argument("--min-starts", type=int, default=40)
    ap.add_argument("--min-qty", type=int, default=30)
    ap.add_argument("--grace-seconds", type=int, default=10)
    ap.add_argument("--holdout-fraction", type=float, default=.25)
    ap.add_argument("--history-step-seconds", type=int, default=600)
    ap.add_argument("--replan-step-seconds", type=int, default=900)
    ap.add_argument("--eval-step-seconds", type=int, default=1800)
    ap.add_argument("--departure-grid-seconds", type=int, default=900)
    ap.add_argument("--max-wait-seconds", type=int, default=12 * 3600)
    ap.add_argument("--topn", type=int, default=4)
    args = ap.parse_args()

    db = Path(args.db).resolve()
    source = Path(args.source_master)
    out = Path(args.output)
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")
    if not source.exists():
        raise SystemExit(f"Source master not found: {source}")

    master = json.loads(source.read_text(encoding="utf-8"))
    targets = _targets_from_master(master, args.threshold)

    report = {
        "schema": "weak-item-targeted-tournament-v20-master-v1",
        "created_at": int(time.time()),
        "db_path": str(db),
        "source_master": str(source),
        "target_rule": {
            "retest_if": f"status != complete OR holdout_success < {args.threshold}",
            "specialized_exclusions": ["jap:Xanax"],
            "coverage": "No abstention; every valid modeled session receives a recommendation.",
            "selection": "Training-only model selection; chronological holdout reporting only.",
        },
        "settings": {
            "min_cycles": args.min_cycles,
            "min_points": args.min_points,
            "min_starts": args.min_starts,
            "max_wait_seconds": args.max_wait_seconds,
            "departure_grid_seconds": args.departure_grid_seconds,
        },
        "targets": targets,
        "results": {},
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    if args.resume and out.exists():
        try:
            prior = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(prior.get("results"), dict):
                report["results"].update(prior["results"])
        except Exception:
            pass

    opts = {
        "min_qty": args.min_qty,
        "grace": args.grace_seconds,
        "holdout_fraction": args.holdout_fraction,
        "topn": args.topn,
        "history_step": args.history_step_seconds,
        "replan_step": args.replan_step_seconds,
        "eval_step": args.eval_step_seconds,
        "departure_grid": args.departure_grid_seconds,
        "max_wait": args.max_wait_seconds,
        "min_cycles": args.min_cycles,
        "min_points": args.min_points,
        "min_starts": args.min_starts,
    }

    pending = []
    for target in targets:
        key = _key(target["country"], target["item"])
        if args.resume and key in report["results"] and report["results"][key].get("status") == "complete":
            continue
        pending.append({
            "db": str(db),
            "country": target["country"],
            "item": target["item"],
            "opts": opts,
        })

    def store(country, item, result):
        key = _key(country, item)
        report["results"][key] = result
        report["summary"] = _summary(master, report["results"])
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        old = (master.get("results") or {}).get(key, {})
        old_rate = _holdout_rate(old)
        new_rate = _holdout_rate(result)
        print(
            f"DONE {key} "
            f"old={(100*old_rate if old_rate is not None else None)} "
            f"new={(100*new_rate if new_rate is not None else None)} "
            f"cycles={result.get('cycles')} "
            f"status={result.get('status')}",
            flush=True,
        )

    started = time.time()
    print(
        f"TARGETS total={len(targets)} pending={len(pending)} "
        f"workers={args.workers} grid={args.departure_grid_seconds}s "
        f"replan={args.replan_step_seconds}s max_wait={args.max_wait_seconds/3600:.1f}h",
        flush=True,
    )
    if args.workers <= 1 or len(pending) <= 1:
        for idx, payload in enumerate(pending, 1):
            print(f"START {idx}/{len(pending)} {_key(payload['country'], payload['item'])}", flush=True)
            store(*_worker(payload))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            future_map = {}
            for idx, p in enumerate(pending, 1):
                fut = ex.submit(_worker, p)
                future_map[fut] = (idx, p)
            unfinished = set(future_map)
            last_heartbeat = time.time()
            while unfinished:
                done, unfinished = wait(unfinished, timeout=60, return_when=FIRST_COMPLETED)
                for fut in done:
                    store(*fut.result())
                now = time.time()
                if unfinished and (not done or now - last_heartbeat >= 60):
                    names = [
                        _key(future_map[f][1]["country"], future_map[f][1]["item"])
                        for f in list(unfinished)[:min(8, len(unfinished))]
                    ]
                    print(
                        f"HEARTBEAT completed={len(future_map)-len(unfinished)}/{len(future_map)} "
                        f"still_running_or_queued={len(unfinished)} examples={names}",
                        flush=True,
                    )
                    last_heartbeat = now

    report["runtime_seconds"] = round(time.time() - started, 3)
    report["summary"] = _summary(master, report["results"])
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    compact = {k: v for k, v in report["summary"].items() if k != "rows"}
    print(json.dumps(compact, indent=2), flush=True)
    print(f"WROTE {out}", flush=True)


if __name__ == "__main__":
    main()
