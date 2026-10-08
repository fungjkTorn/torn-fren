"""V21 non-destructive repair of the all-item arrival-success benchmark.

V19/V20 used only completed cycles to construct truth windows, so a confirmed
in-stock arrival during an incomplete/partially observed cycle scored as a miss.
This module audits stored recommendations and can rerun V19's model selection
with corrected quantity-at-arrival labels. It DOES NOT modify V19/V20 files.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


def load_clean_item(conn, country, item):
    raw = conn.execute(
        "SELECT timestamp, quantity, source FROM stock_history "
        "WHERE country=? AND item_name=? ORDER BY timestamp, id",
        (country, item),
    ).fetchall()
    kept = []
    for j, (t, q, source) in enumerate(raw):
        if 0 < j < len(raw) - 1:
            pt, pq, ps = raw[j - 1]
            nt, nq, ns = raw[j + 1]
            disagree = source != ps or source != ns
            bounce = ((q == 0 and pq > 0 and nq > 0)
                      or (q > 0 and pq == 0 and nq == 0))
            if t - pt <= 180 and nt - t <= 180 and disagree and bounce:
                continue
        kept.append((int(t), int(q)))
    return kept


def load_gaps(conn):
    return sorted(
        (int(s), int(e) if e is not None else 2**63 - 1)
        for s, e in conn.execute(
            "SELECT start_timestamp, end_timestamp FROM collection_gaps"
        ).fetchall()
    )


def crosses_gap(gaps, a, b):
    lo, hi = sorted((float(a), float(b)))
    for start, end in gaps:
        if start > hi:
            return False
        if start <= hi and end >= lo:
            return True
    return False


def observed_arrival_success(times, quantities, gaps, arrival, min_qty, grace):
    """None means not safely scorable; otherwise use recorded stock state."""
    arrival = float(arrival)
    end = arrival + float(grace)
    j = bisect.bisect_right(times, arrival) - 1
    if j < 0 or arrival > times[-1] or end > times[-1]:
        return None
    if crosses_gap(gaps, times[j], end):
        return None
    if quantities[j] >= min_qty:
        return True
    hi = bisect.bisect_right(times, end)
    return any(quantities[k] >= min_qty for k in range(j + 1, hi))


def audit(args):
    db = Path(args.db).resolve()
    masters = [Path(x).resolve() for x in args.masters]
    for p in [db, *masters]:
        if not p.is_file():
            raise SystemExit(f"Missing file: {p}")

    # Read only. The collector and original V20 run are never modified.
    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    gaps = load_gaps(conn)
    sha = hashlib.sha256(db.read_bytes()).hexdigest()
    if args.expected_db_sha256 and sha.lower() != args.expected_db_sha256.lower():
        raise SystemExit(f"DB SHA mismatch: {sha} != {args.expected_db_sha256}")

    cache = {}
    master_reports = []
    for master_path in masters:
        master = json.loads(master_path.read_text(encoding="utf-8"))
        evaluated = []
        for key, result in (master.get("results") or {}).items():
            holdout = result.get("holdout_rows") or []
            if not holdout or ":" not in key:
                continue
            if key not in cache:
                country, item = key.split(":", 1)
                rows = load_clean_item(conn, country, item)
                cache[key] = ([t for t, _q in rows], [q for _t, q in rows])
            times, qtys = cache[key]
            if not times:
                continue
            compared = old_hits = actual_hits = fn = fp = uncertain = 0
            for row in holdout:
                truth = observed_arrival_success(
                    times, qtys, gaps, row["arrival"], args.min_qty, args.grace_seconds
                )
                if truth is None:
                    uncertain += 1
                    continue
                old = bool(row["success"])
                compared += 1
                old_hits += int(old)
                actual_hits += int(truth)
                fn += int(not old and truth)
                fp += int(old and not truth)
            if compared:
                evaluated.append({
                    "key": key, "status": result.get("status"),
                    "cycles": result.get("cycles"),
                    "observed_max_quantity": max(qtys),
                    "compared": compared, "uncertain_skipped": uncertain,
                    "original_success": old_hits, "corrected_success": actual_hits,
                    "original_rate": old_hits / compared,
                    "corrected_rate": actual_hits / compared,
                    "false_negative": fn, "false_positive": fp,
                    "correction_only_not_reselected": True,
                })

        summary = {
            "items_evaluated": len(evaluated),
            "items_with_changed_labels": sum(
                x["false_negative"] + x["false_positive"] > 0 for x in evaluated
            ),
            "sessions_scored": sum(x["compared"] for x in evaluated),
            "uncertain_sessions_excluded": sum(x["uncertain_skipped"] for x in evaluated),
            "total_false_negatives": sum(x["false_negative"] for x in evaluated),
            "total_false_positives": sum(x["false_positive"] for x in evaluated),
            "items_ge_80_before": sum(x["original_rate"] >= .80 for x in evaluated),
            "items_ge_80_after": sum(x["corrected_rate"] >= .80 for x in evaluated),
        }
        evaluated.sort(key=lambda x: (
            -(x["false_negative"] + x["false_positive"]), x["key"]
        ))
        print(
            f"AUDIT {master_path.name}: {summary} "
            f"top_corrections={[x['key'] for x in evaluated[:10]]}",
            flush=True,
        )
        master_reports.append({
            "master": str(master_path), "summary": summary, "items": evaluated
        })

    report = {
        "schema": "remaining-item-truth-audit-v21",
        "created_at": int(time.time()), "db_path": str(db),
        "db_sha256": sha, "quantity_threshold": args.min_qty,
        "grace_seconds": args.grace_seconds, "masters": master_reports,
        "warning": (
            "This fixes recorded holdout labels only. V19/V20 model-selection "
            "scores used the same flawed labels. Rerun training/selection using "
            "corrected truth before treating a challenger as a new champion."
        ),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"WROTE {out}", flush=True)


def _corrected_worker(payload):
    from services import history_service
    from services import plushie_flower_dynamic_planner_v19 as planner

    db = Path(payload["db"]).resolve()
    history_service.DB_PATH = db
    history_service._DB_READY = False

    # This is a separate process and changes only its module-local binding.
    # Original V19/V20 scripts and currently running tournaments stay untouched.
    class QuantityTruthTimeline(planner.Timeline):
        def success(self, arrival, grace_seconds):
            val = observed_arrival_success(
                self.ts, self.qty, self.gaps, arrival, self.min_qty, grace_seconds
            )
            if val is None:
                # Valid scored sessions exclude these gaps. Historical analogs
                # must likewise not be credited for an unknown arrival state.
                return False
            return bool(val)

    planner.Timeline = QuantityTruthTimeline
    country, item = payload["key"].split(":", 1)
    try:
        _c, _i, result = planner.run_item(country, item, **payload["opts"])
        result["scorer"] = "quantity-at-arrival-v21"
    except Exception as exc:
        result = {
            "country": country, "item_name": item,
            "status": "error", "error": repr(exc),
            "scorer": "quantity-at-arrival-v21",
        }
    return payload["key"], result


def tournament(args):
    db = Path(args.db).resolve()
    if not db.is_file():
        raise SystemExit(f"Missing DB: {db}")
    if not args.only:
        raise SystemExit(
            "Use --only country:Item (repeat) to keep V21 targeted. "
            "The ongoing original V20 run should be allowed to finish."
        )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "remaining-item-v21-corrected-challenger-v1",
        "created_at": int(time.time()), "db_path": str(db),
        "benchmark": "True recorded >=min_qty at arrival or within grace; "
                     "gap-invalid arrivals excluded from sessions.",
        "warning": "Research challenger; no production promotion or deploy.",
        "results": {},
    }
    if args.resume and out.is_file():
        report["results"].update(
            json.loads(out.read_text(encoding="utf-8")).get("results", {})
        )

    opts = {
        "min_qty": args.min_qty, "grace": args.grace_seconds,
        "holdout_fraction": .25, "topn": 3,
        "history_step": 600, "replan_step": args.replan_step_seconds,
        "eval_step": 1800, "departure_grid": args.departure_grid_seconds,
        "max_wait": args.max_wait_hours * 3600,
        "min_cycles": args.min_cycles, "min_points": 60,
        "min_starts": 40,
    }
    payloads = [
        {"key": k, "db": str(db), "opts": opts}
        for k in dict.fromkeys(args.only)
        if not (args.resume and k in report["results"])
    ]
    print(f"V21 TARGETS {len(payloads)} workers={args.workers}", flush=True)

    def store(key, result):
        report["results"][key] = result
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        hold = (result.get("selected_on_training") or {}).get("holdout") or {}
        print(
            f"DONE {key} status={result.get('status')} "
            f"cycles={result.get('cycles')} "
            f"corrected_holdout={hold.get('arrival_success_rate')} "
            f"coverage={hold.get('coverage')}",
            flush=True,
        )

    if args.workers <= 1:
        for payload in payloads:
            store(*_corrected_worker(payload))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(_corrected_worker, p) for p in payloads]
            for future in as_completed(futures):
                store(*future.result())
    print(f"WROTE {out}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Remaining-item V21 truth audit and corrected challenger")
    sub = ap.add_subparsers(dest="command", required=True)
    audit_parser = sub.add_parser("audit", help="Re-score existing V19/V20 recommendations")
    audit_parser.add_argument("--db", required=True)
    audit_parser.add_argument("--masters", nargs="+", required=True)
    audit_parser.add_argument("--min-qty", type=int, default=30)
    audit_parser.add_argument("--grace-seconds", type=int, default=10)
    audit_parser.add_argument("--expected-db-sha256")
    audit_parser.add_argument("--output", default="data/remaining_item_v21/truth_audit.json")

    run_parser = sub.add_parser("tournament", help="Re-select dynamic models on corrected labels")
    run_parser.add_argument("--db", required=True)
    run_parser.add_argument("--only", action="append", default=[])
    run_parser.add_argument("--workers", type=int, default=2)
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--min-qty", type=int, default=30)
    run_parser.add_argument("--grace-seconds", type=int, default=10)
    run_parser.add_argument("--min-cycles", type=int, default=6)
    run_parser.add_argument("--max-wait-hours", type=int, default=12)
    run_parser.add_argument("--replan-step-seconds", type=int, default=900)
    run_parser.add_argument("--departure-grid-seconds", type=int, default=900)
    run_parser.add_argument("--output", default="data/remaining_item_v21/corrected_master.json")
    args = ap.parse_args()
    if args.command == "audit":
        audit(args)
    else:
        tournament(args)


if __name__ == "__main__":
    main()
