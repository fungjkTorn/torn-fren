from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from services import history_service
from services.plushie_flower_dynamic_planner_v18 import worker as dynamic_worker


SPECIALIZED_OVERRIDES = {
    ("jap", "Xanax"): {
        "model": "japan_xanax_observation_lag_v7",
        "reason": "Japan Xanax has a specialized corrected-ground-truth model; generic dynamic result is comparison-only.",
    },
}


def _catalog_targets(db: Path):
    history_service.DB_PATH = db
    history_service._DB_READY = False
    catalog = history_service.get_stock_catalog()
    out = []
    for c in catalog.get("countries", []):
        country = str(c.get("country") or "").lower().strip()
        for row in c.get("items", []):
            item = str(row.get("item_name") or "").strip()
            if country and item:
                out.append((country, item))
    return out


def _key(country: str, item: str) -> str:
    return f"{country}:{item}"


def _holdout(report):
    return (report.get("selected_on_training") or {}).get("holdout") or {}


def _scoreboard(results):
    complete = []
    status_counts = {}
    for r in results.values():
        status = r.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "complete":
            h = _holdout(r)
            complete.append({
                "country": r.get("country"),
                "item_name": r.get("item_name"),
                "success": float(h.get("arrival_success_rate") or 0.0),
                "coverage": float(h.get("coverage") or 0.0),
                "n": int(h.get("recommendations") or 0),
                "config": ((r.get("selected_on_training") or {}).get("config") or {}).get("name"),
            })

    rates = [x["success"] for x in complete]
    complete.sort(key=lambda x: (x["success"], x["coverage"], x["n"]))
    return {
        "items_total": len(results),
        "status_counts": status_counts,
        "completed_items": len(complete),
        "items_above_90": sum(x >= .90 for x in rates),
        "items_above_80": sum(x >= .80 for x in rates),
        "items_above_70": sum(x >= .70 for x in rates),
        "items_above_60": sum(x >= .60 for x in rates),
        "mean_holdout_success": (sum(rates) / len(rates)) if rates else None,
        "minimum_holdout_success": min(rates) if rates else None,
        "maximum_holdout_success": max(rates) if rates else None,
        "worst_25_complete": complete[:25],
        "best_25_complete": list(reversed(complete[-25:])),
    }


def _registry(results):
    items = {}
    for k, r in results.items():
        country = r.get("country")
        item = r.get("item_name")
        override = SPECIALIZED_OVERRIDES.get((country, item))
        if override:
            items[k] = {
                "status": "specialized_override",
                "production_candidate": override["model"],
                "reason": override["reason"],
                "generic_challenger": {
                    "status": r.get("status"),
                    "config": ((r.get("selected_on_training") or {}).get("config") or {}).get("name"),
                    "holdout": _holdout(r),
                },
            }
            continue

        if r.get("status") != "complete":
            items[k] = {
                "status": r.get("status"),
                "production_candidate": "prediction_v2_fallback",
                "reason": "Not enough clean dynamic-planner evidence for promotion.",
            }
            continue

        h = _holdout(r)
        items[k] = {
            "status": "candidate",
            "production_candidate": "dynamic_planner_v18_family",
            "config": (r.get("selected_on_training") or {}).get("config"),
            "holdout": h,
            "train": (r.get("selected_on_training") or {}).get("train"),
            "selection_rule": r.get("selection_rule"),
            "promotion_note": "Challenger only until compared with legacy/current production on matched evaluation rules.",
        }
    return {
        "schema": "production-model-registry-candidate-v1",
        "created_at": int(time.time()),
        "items": items,
    }


def main():
    ap = argparse.ArgumentParser(
        description="All-item V19 challenger tournament using the current dynamic leave-time family."
    )
    ap.add_argument("--db", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--output", default="data/all_item_v19/master.json")
    ap.add_argument("--registry-output", default="data/all_item_v19/production_model_registry_candidate.json")
    ap.add_argument("--only", action="append", default=[], help="country:Exact Item Name")
    ap.add_argument("--resume", action="store_true", help="Reuse already-completed item results in output JSON.")

    # Full-quality defaults intentionally match V18.1 except topn is smaller to
    # keep the all-item output manageable.
    ap.add_argument("--topn", type=int, default=4)
    ap.add_argument("--min-qty", type=int, default=30)
    ap.add_argument("--grace-seconds", type=int, default=10)
    ap.add_argument("--holdout-fraction", type=float, default=.25)
    ap.add_argument("--history-step-seconds", type=int, default=600)
    ap.add_argument("--replan-step-seconds", type=int, default=300)
    ap.add_argument("--eval-step-seconds", type=int, default=1800)
    ap.add_argument("--departure-grid-seconds", type=int, default=300)
    ap.add_argument("--max-wait-seconds", type=int, default=6 * 3600)
    args = ap.parse_args()

    db = Path(args.db).resolve()
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")

    targets = _catalog_targets(db)
    only = set(args.only or [])
    if only:
        targets = [(c, i) for c, i in targets if _key(c, i) in only]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    registry_out = Path(args.registry_output)
    registry_out.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "schema": "all-item-dynamic-challenger-v19-master-v1",
        "created_at": int(time.time()),
        "db_path": str(db),
        "items_total": len(targets),
        "benchmark": {
            "success": "quantity_on_arrival >= 30; +10 seconds grace in timeline.success",
            "coverage": "No GO/WAIT abstention threshold; every valid modeled session gets a recommendation.",
            "selection": "Training-only ranking; chronological holdout reporting only.",
            "note": "This is a challenger tournament. Do not promote over current production until matched comparison is reviewed.",
        },
        "specialized_overrides": {
            _key(c, i): v for (c, i), v in SPECIALIZED_OVERRIDES.items()
        },
        "results": {},
    }

    if args.resume and out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(old.get("results"), dict):
                report["results"].update(old["results"])
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
    }

    pending = []
    for country, item in targets:
        k = _key(country, item)
        if args.resume and k in report["results"]:
            continue
        pending.append({"db": str(db), "country": country, "item": item, "opts": opts})

    def store(country, item, result):
        k = _key(country, item)
        report["results"][k] = result
        report["scoreboard"] = _scoreboard(report["results"])
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        registry_out.write_text(json.dumps(_registry(report["results"]), indent=2), encoding="utf-8")
        h = _holdout(result)
        print(
            f"DONE {country}:{item} "
            f"success={100 * float(h.get('arrival_success_rate') or 0):.1f}% "
            f"coverage={100 * float(h.get('coverage') or 0):.1f}% "
            f"status={result.get('status')}",
            flush=True,
        )

    started = time.time()
    if args.workers <= 1 or len(pending) <= 1:
        for payload in pending:
            store(*dynamic_worker(payload))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(dynamic_worker, p) for p in pending]
            for fut in as_completed(futures):
                store(*fut.result())

    report["scoreboard"] = _scoreboard(report["results"])
    report["runtime_seconds"] = round(time.time() - started, 3)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    registry_out.write_text(json.dumps(_registry(report["results"]), indent=2), encoding="utf-8")

    print(json.dumps(report["scoreboard"], indent=2), flush=True)
    print(f"WROTE {out}", flush=True)
    print(f"WROTE {registry_out}", flush=True)


if __name__ == "__main__":
    main()
