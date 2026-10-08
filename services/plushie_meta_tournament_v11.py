import argparse
import json
import math
import statistics
import time
from pathlib import Path

from services import history_service
from services.deep_arrival_tournament_v10 import (
    SHORT_WAIT_SECONDS,
    WAIT_MINUTES,
    _folds,
    build_dense_decisions,
    config_grid,
    score_config,
)
from services.projection_grand_tournament_v8_live_engine import summarize


TARGETS = [
    ("uni", "Nessie Plushie"),
    ("uni", "Red Fox Plushie"),
    ("swi", "Chamois Plushie"),
    ("arg", "Monkey Plushie"),
    ("chi", "Panda Plushie"),
    ("uae", "Camel Plushie"),
    ("sou", "Lion Plushie"),
]

RECENT_WINDOWS = (12, 20, 30, 45, 60, 90)
EXP_HALVES = (6.0, 10.0, 15.0, 25.0, 40.0)
MIN_META_SAMPLES = 6


def row_key(row):
    return (
        int(row["decision_timestamp"]),
        int(row["anchor_timestamp"]),
        int(row["age_seconds"]),
    )


def wilson_lower(hits, n, z=1.6448536269514722):
    if n <= 0:
        return -1.0
    p = hits / n
    den = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return (center - margin) / den


def resolved_history(rows, current_ts, resolution_horizon):
    cutoff = float(current_ts) - float(resolution_horizon)
    return [r for r in rows if float(r["decision_timestamp"]) < cutoff]


def recent_score(rows, n):
    work = rows[-int(n):]
    if len(work) < MIN_META_SAMPLES:
        return None
    hits = sum(int(r["success_30"]) for r in work)
    rate = hits / len(work)
    floor = wilson_lower(hits, len(work))
    return 0.65 * rate + 0.35 * floor


def exp_score(rows, half_life):
    if len(rows) < MIN_META_SAMPLES:
        return None
    rows = rows[-120:]
    n = len(rows)
    weights = [0.5 ** ((n - 1 - i) / float(half_life)) for i in range(n)]
    total = sum(weights)
    if total <= 0:
        return None
    rate = sum(w * int(r["success_30"]) for w, r in zip(weights, rows)) / total
    ess = (total * total) / sum(w * w for w in weights)
    pseudo_hits = rate * ess
    floor = wilson_lower(pseudo_hits, ess)
    return 0.70 * rate + 0.30 * floor


def selector_score(rows, policy):
    kind, value = policy
    if kind == "recent":
        return recent_score(rows, int(value))
    if kind == "exp":
        return exp_score(rows, float(value))
    raise ValueError(policy)


def choose_config(config_rows, current_key, current_ts, resolution_horizon, policy):
    best = None
    for config_name, row_map in config_rows.items():
        current_row = row_map.get(current_key)
        if current_row is None:
            continue
        history = resolved_history(
            list(row_map.values()), current_ts, resolution_horizon
        )
        score = selector_score(history, policy)
        if score is None:
            continue
        hist_n = len(history)
        wait = float(current_row.get("recommended_wait_minutes") or 0.0)
        candidate = (score, hist_n, -wait, config_name, current_row)
        if best is None or candidate[:3] > best[:3]:
            best = candidate
    return None if best is None else best[-1]


def evaluate_meta(config_rows, keys, resolution_horizon, policy):
    chosen = []
    for key in keys:
        current_ts = key[0]
        row = choose_config(
            config_rows, key, current_ts, resolution_horizon, policy
        )
        if row is not None:
            chosen.append(row)
    return chosen


def chronological_keys(config_rows):
    all_keys = set()
    for row_map in config_rows.values():
        all_keys.update(row_map.keys())
    return sorted(all_keys)


def run_item(country, item_name):
    ctx, timeline, decisions = build_dense_decisions(country, item_name, max_depth=10)
    configs = list(config_grid())
    config_rows = {}
    config_static = []

    for idx, config in enumerate(configs, 1):
        rows = score_config(ctx, timeline, decisions, config)
        row_map = {row_key(r): r for r in rows}
        config_rows[config.name] = row_map
        train_rows = [r for r in rows if r["decision_timestamp"] < ctx.split_timestamp]
        hold_rows = [r for r in rows if r["decision_timestamp"] >= ctx.split_timestamp]
        folds = _folds(ctx, rows)
        config_static.append({
            "config": config.name,
            "family": config.family,
            "train": summarize(train_rows),
            "holdout": summarize(hold_rows),
            "folds": folds,
        })
        if idx % 25 == 0:
            print(f"  scored {idx}/{len(configs)} configs", flush=True)

    keys = chronological_keys(config_rows)
    train_keys = [k for k in keys if k[0] < ctx.split_timestamp]
    hold_keys = [k for k in keys if k[0] >= ctx.split_timestamp]
    if len(train_keys) < 80:
        raise RuntimeError(f"Not enough training decisions: {len(train_keys)}")

    meta_cut = max(1, int(len(train_keys) * 0.75))
    meta_val_keys = train_keys[meta_cut:]

    resolution_horizon = (
        max(WAIT_MINUTES) * 60.0
        + float(ctx.travel_seconds)
        + float(SHORT_WAIT_SECONDS)
    )

    policies = [("recent", n) for n in RECENT_WINDOWS]
    policies += [("exp", h) for h in EXP_HALVES]
    meta_results = []
    for policy in policies:
        rows = evaluate_meta(config_rows, meta_val_keys, resolution_horizon, policy)
        summary = summarize(rows)
        meta_results.append({"policy": list(policy), "validation": summary})

    meta_results.sort(
        key=lambda x: (
            float((x["validation"] or {}).get("success_30_rate") or -1.0),
            int((x["validation"] or {}).get("n") or 0),
        ),
        reverse=True,
    )
    selected_policy = tuple(meta_results[0]["policy"])

    hold_rows = evaluate_meta(
        config_rows, hold_keys, resolution_horizon, selected_policy
    )
    holdout = summarize(hold_rows)

    static_ranked = sorted(
        config_static,
        key=lambda x: (
            float((x["train"] or {}).get("success_30_rate") or -1.0),
            statistics.mean([
                f["success_30_rate"]
                for f in x["folds"]
                if f.get("success_30_rate") is not None
            ]) if x["folds"] else -1.0,
        ),
        reverse=True,
    )

    return {
        "schema": "plushie-meta-v11-item-v1",
        "country": country,
        "item_name": item_name,
        "travel_seconds": ctx.travel_seconds,
        "decision_points": len(decisions),
        "candidate_configs": len(configs),
        "outer_split_timestamp": ctx.split_timestamp,
        "meta_validation_decisions": len(meta_val_keys),
        "holdout_decisions_available": len(hold_keys),
        "selected_meta_policy": list(selected_policy),
        "meta_validation": meta_results[0]["validation"],
        "holdout": holdout,
        "meta_policy_table": meta_results,
        "static_training_winner": static_ranked[0] if static_ranked else None,
        "notes": (
            "Meta policy selected only on the last 25% of the outer training period. "
            "Outer holdout is never used for model or selector choice. Prior model "
            "performance is eligible only after the conservative full candidate "
            "wait+travel+short-wait horizon has resolved."
        ),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--output", default="data/plushie_meta_v11.json")
    p.add_argument(
        "--only",
        action="append",
        default=[],
        help='Country:item, e.g. --only "uni:Nessie Plushie"',
    )
    args = p.parse_args()

    db = Path(args.db).resolve()
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")
    history_service.DB_PATH = db
    history_service._DB_READY = False

    wanted = {x.lower() for x in args.only}
    targets = TARGETS
    if wanted:
        targets = [x for x in TARGETS if f"{x[0]}:{x[1]}".lower() in wanted]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    master = {
        "schema": "plushie-meta-v11-master-v1",
        "db_path": str(db),
        "results": {},
    }

    for i, (country, item) in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {country.upper()} / {item}", flush=True)
        t0 = time.time()
        try:
            report = run_item(country, item)
            report["status"] = "complete"
        except Exception as exc:
            report = {
                "country": country,
                "item_name": item,
                "status": "error",
                "error": repr(exc),
            }
        report["runtime_seconds"] = round(time.time() - t0, 2)
        master["results"][f"{country}:{item}"] = report
        output.write_text(json.dumps(master, indent=2))

        h = report.get("holdout") or {}
        print(
            f"  {report['status']} holdout="
            f"{100 * float(h.get('success_30_rate') or 0):.1f}% "
            f"n={h.get('n') or 0} "
            f"policy={report.get('selected_meta_policy')}",
            flush=True,
        )

    print(f"\nSaved {output}")


if __name__ == "__main__":
    main()
