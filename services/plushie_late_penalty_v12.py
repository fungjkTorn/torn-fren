import argparse
import json
import math
import time
from pathlib import Path

from services import history_service
from services.deep_arrival_tournament_v10 import (
    SHORT_WAIT_SECONDS,
    WAIT_MINUTES,
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

# Minutes to move the V10-recommended departure earlier.
EARLY_SHIFTS_MINUTES = (0, 3, 5, 8, 10, 12, 15, 20, 25, 30, 40)


def wilson_lower(hits, n, z=1.959963984540054):
    if n <= 0:
        return -1.0
    p = hits / n
    den = 1.0 + z * z / n
    center = p + z * z / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n)
    return (center - margin) / den


def rescore_with_early_shift(ctx, timeline, base_rows, shift_minutes):
    out = []
    shift = float(shift_minutes)
    travel = float(ctx.travel_seconds)

    for row in base_rows:
        old_wait = float(row.get("recommended_wait_minutes") or 0.0)
        new_wait = max(0.0, old_wait - shift)
        departure = float(row["decision_timestamp"]) + new_wait * 60.0
        arrival = departure + travel
        qty = timeline.quantity_at(arrival)
        hit = int(qty is not None and qty >= 30)

        short = 0
        if not hit:
            nxt = timeline.first_at_least(
                arrival, threshold=30, within=SHORT_WAIT_SECONDS
            )
            short = int(nxt is not None and nxt[0] > int(arrival))

        new_row = dict(row)
        new_row.update({
            "recommended_wait_minutes": new_wait,
            "early_shift_minutes": shift,
            "recommended_departure_timestamp": departure,
            "recommended_arrival_timestamp": arrival,
            "quantity_on_arrival": qty,
            "success_30": hit,
            "short_wait_3m": short,
            "early_window": int(arrival < float(row["actual_start"])),
            "late_window": int(arrival >= float(row["actual_end"])),
        })
        out.append(new_row)

    return out


def rank_summary(summary):
    if not summary or not summary.get("n"):
        return (-1.0, -1.0, -1.0, -1.0)

    n = int(summary["n"])
    rate = float(summary.get("success_30_rate") or 0.0)
    hits = round(rate * n)
    wilson = wilson_lower(hits, n)
    late = float(summary.get("late_rate") or 1.0)
    early = float(summary.get("early_rate") or 1.0)

    # Success remains the main objective.
    # Wilson rewards stability/sample size.
    # Late misses are penalized more than early misses because V11 showed a
    # very strong systematic late bias on the hard plushies.
    score = (
        0.70 * rate
        + 0.20 * wilson
        - 0.08 * late
        - 0.02 * early
    )
    return (score, rate, wilson, -late)


def run_item(country, item_name):
    ctx, timeline, decisions = build_dense_decisions(
        country, item_name, max_depth=10
    )
    if ctx.split_timestamp is None:
        raise RuntimeError("No outer split available")

    configs = list(config_grid())
    candidates = []

    for idx, config in enumerate(configs, 1):
        base_rows = score_config(ctx, timeline, decisions, config)

        train_rows = [
            r for r in base_rows
            if r["decision_timestamp"] < ctx.split_timestamp
        ]
        hold_rows = [
            r for r in base_rows
            if r["decision_timestamp"] >= ctx.split_timestamp
        ]

        if len(train_rows) < 80:
            continue

        train_stamps = sorted(
            {int(r["decision_timestamp"]) for r in train_rows}
        )
        cut = max(1, int(len(train_stamps) * 0.75))
        inner_val_stamps = set(train_stamps[cut:])
        inner_train_stamps = set(train_stamps[:cut])

        for shift in EARLY_SHIFTS_MINUTES:
            shifted_train = rescore_with_early_shift(
                ctx, timeline, train_rows, shift
            )
            inner_train = [
                r for r in shifted_train
                if int(r["decision_timestamp"]) in inner_train_stamps
            ]
            inner_val = [
                r for r in shifted_train
                if int(r["decision_timestamp"]) in inner_val_stamps
            ]

            tr = summarize(inner_train)
            va = summarize(inner_val)

            candidates.append({
                "config": config.name,
                "family": config.family,
                "early_shift_minutes": shift,
                "inner_train": tr,
                "inner_validation": va,
                "rank_key": list(rank_summary(va)),
                "_hold_base_rows": hold_rows,
            })

        if idx % 25 == 0:
            print(f"  scored {idx}/{len(configs)} configs", flush=True)

    if not candidates:
        raise RuntimeError("No V12 candidates produced")

    candidates.sort(
        key=lambda x: tuple(x["rank_key"]),
        reverse=True,
    )

    selected = candidates[0]
    selected_hold = rescore_with_early_shift(
        ctx,
        timeline,
        selected.pop("_hold_base_rows"),
        selected["early_shift_minutes"],
    )
    holdout = summarize(selected_hold)

    # Keep a compact leaderboard. Strip internal hold rows from finalists.
    finalists = []
    for c in candidates[:20]:
        item = {k: v for k, v in c.items() if k != "_hold_base_rows"}
        finalists.append(item)

    return {
        "schema": "plushie-late-penalty-v12-item-v1",
        "country": country,
        "item_name": item_name,
        "travel_seconds": ctx.travel_seconds,
        "decision_points": len(decisions),
        "base_configs_tested": len(configs),
        "early_shift_grid_minutes": list(EARLY_SHIFTS_MINUTES),
        "outer_split_timestamp": ctx.split_timestamp,
        "selection_rule": (
            "Select config + early-departure shift using only the last 25% "
            "of the outer training period. Ranking prioritizes >=30 success, "
            "then Wilson stability, and penalizes late misses more than early "
            "misses. Outer holdout is report-only."
        ),
        "selected": {k: v for k, v in selected.items() if k != "_hold_base_rows"},
        "holdout": holdout,
        "top_finalists": finalists,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--output", default="data/plushie_late_penalty_v12.json")
    p.add_argument(
        "--only",
        action="append",
        default=[],
        help='Country:item, e.g. --only "arg:Monkey Plushie"',
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
        targets = [
            x for x in TARGETS
            if f"{x[0]}:{x[1]}".lower() in wanted
        ]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    master = {
        "schema": "plushie-late-penalty-v12-master-v1",
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
        s = report.get("selected") or {}
        print(
            f"  {report['status']} holdout="
            f"{100 * float(h.get('success_30_rate') or 0):.1f}% "
            f"n={h.get('n') or 0} "
            f"late={100 * float(h.get('late_rate') or 0):.1f}% "
            f"early={100 * float(h.get('early_rate') or 0):.1f}% "
            f"shift={s.get('early_shift_minutes')}m",
            flush=True,
        )

    print(f"\nSaved {output}")


if __name__ == "__main__":
    main()
