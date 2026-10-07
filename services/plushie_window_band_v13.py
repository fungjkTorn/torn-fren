import argparse
import json
import math
import statistics
import time
from pathlib import Path

from services import history_service
from services.deep_arrival_tournament_v10 import (
    WAIT_MINUTES,
    build_dense_decisions,
)
from services.projection_grand_tournament_v7_engine import (
    MIN_STOCK,
    SHORT_WAIT_SECONDS,
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

LOOKBACKS = (8, 12, 20, 30, 45, 60, 90)
AGE_WINDOWS = (0, 10, 20, 30)
SMOOTH_RADII = (0, 1, 2, 3)  # wait-grid neighbors, 5m each


def _decision_key(r):
    return (
        int(r["decision_timestamp"]),
        int(r["anchor_timestamp"]),
        int(r["age_seconds"]),
    )


def _filter_history(prior, current, lookback, age_window):
    if age_window == 0:
        rows = [
            r for r in prior
            if int(r["age_seconds"]) == int(current["age_seconds"])
        ]
    else:
        w = int(age_window) * 60
        rows = [
            r for r in prior
            if abs(float(r["age_seconds"]) - float(current["age_seconds"])) <= w
        ]
    return rows[-int(lookback):]


def _wait_hit(timeline, row, travel, wait_min):
    arrival = (
        float(row["decision_timestamp"])
        + float(wait_min) * 60.0
        + float(travel)
    )
    qty = timeline.quantity_at(arrival)
    return int(qty is not None and qty >= MIN_STOCK)


def _score_wait_band(timeline, rows, travel, wait_idx, radius):
    if len(rows) < 5:
        return None
    idxs = range(
        max(0, wait_idx - radius),
        min(len(WAIT_MINUTES), wait_idx + radius + 1),
    )
    per_row = []
    for r in rows:
        hits = [_wait_hit(timeline, r, travel, WAIT_MINUTES[j]) for j in idxs]
        # Robust-band objective: reward waits whose nearby departures also work.
        per_row.append(sum(hits) / len(hits))
    if not per_row:
        return None
    mean = statistics.mean(per_row)
    floor = statistics.quantiles(per_row, n=4, method="inclusive")[0] if len(per_row) >= 4 else min(per_row)
    return 0.80 * mean + 0.20 * floor


def _choose_wait(timeline, history, current, travel, lookback, age_window, radius):
    rows = _filter_history(history, current, lookback, age_window)
    if len(rows) < 5:
        return None
    scored = []
    for i, wait in enumerate(WAIT_MINUTES):
        score = _score_wait_band(timeline, rows, travel, i, radius)
        if score is None:
            continue
        scored.append((score, -wait, wait))
    if not scored:
        return None
    best = max(scored)
    return float(best[2]), float(best[0])


def _score_row(timeline, current, travel, wait_min, band_score):
    departure = float(current["decision_timestamp"]) + wait_min * 60.0
    arrival = departure + float(travel)
    qty = timeline.quantity_at(arrival)
    hit = int(qty is not None and qty >= MIN_STOCK)
    short = 0
    if not hit:
        nxt = timeline.first_at_least(arrival, threshold=MIN_STOCK, within=SHORT_WAIT_SECONDS)
        short = int(nxt is not None and nxt[0] > int(arrival))
    return {
        "decision_timestamp": current["decision_timestamp"],
        "anchor_timestamp": current["anchor_timestamp"],
        "age_seconds": current["age_seconds"],
        "recommended_wait_minutes": wait_min,
        "band_score": band_score,
        "quantity_on_arrival": qty,
        "success_30": hit,
        "short_wait_3m": short,
        "early_window": 0,
        "late_window": 0,
    }


def run_config(ctx, timeline, decisions, lookback, age_window, radius):
    resolution = max(WAIT_MINUTES) * 60.0 + float(ctx.travel_seconds) + SHORT_WAIT_SECONDS
    rows = []
    for current in decisions:
        now = float(current["decision_timestamp"])
        history = [
            r for r in decisions
            if float(r["decision_timestamp"]) + resolution < now
        ]
        choice = _choose_wait(
            timeline, history, current, ctx.travel_seconds,
            lookback, age_window, radius
        )
        if choice is None:
            continue
        wait_min, score = choice
        rows.append(_score_row(
            timeline, current, ctx.travel_seconds, wait_min, score
        ))
    return rows


def _inner_split(rows, outer_split):
    train = [r for r in rows if r["decision_timestamp"] < outer_split]
    stamps = sorted({int(r["decision_timestamp"]) for r in train})
    cut = max(1, int(len(stamps) * 0.75))
    val_stamps = set(stamps[cut:])
    val = [r for r in train if int(r["decision_timestamp"]) in val_stamps]
    return train, val


def _rank(summary):
    if not summary or not summary.get("n"):
        return (-1.0, -1.0)
    return (
        float(summary.get("success_30_rate") or 0.0),
        float(summary.get("success_or_short_wait_rate") or 0.0),
    )


def run_item(country, item_name):
    ctx, timeline, decisions = build_dense_decisions(country, item_name, max_depth=10)
    candidates = []
    for lb in LOOKBACKS:
        for age in AGE_WINDOWS:
            for radius in SMOOTH_RADII:
                rows = run_config(ctx, timeline, decisions, lb, age, radius)
                train, val = _inner_split(rows, ctx.split_timestamp)
                hold = [r for r in rows if r["decision_timestamp"] >= ctx.split_timestamp]
                candidates.append({
                    "lookback": lb,
                    "age_window": age,
                    "smooth_radius": radius,
                    "train": summarize(train),
                    "inner_validation": summarize(val),
                    "holdout": summarize(hold),
                    "rank_key": list(_rank(summarize(val))),
                })
    candidates.sort(key=lambda x: tuple(x["rank_key"]), reverse=True)
    selected = candidates[0] if candidates else None
    return {
        "schema": "plushie-window-band-v13-item-v1",
        "country": country,
        "item_name": item_name,
        "travel_seconds": ctx.travel_seconds,
        "decision_points": len(decisions),
        "candidate_configs": len(candidates),
        "selection_rule": (
            "Select lookback/age/band radius on inner chronological validation only. "
            "The model scores a departure by the historical robustness of the entire "
            "nearby wait band rather than a single exact arrival minute. Outer holdout "
            "is report-only."
        ),
        "selected": selected,
        "top_finalists": candidates[:15],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--output", default="data/plushie_window_band_v13.json")
    p.add_argument("--only", action="append", default=[])
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

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    master = {"schema": "plushie-window-band-v13-master-v1", "db_path": str(db), "results": {}}

    for i, (country, item) in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {country.upper()} / {item}", flush=True)
        t0 = time.time()
        try:
            report = run_item(country, item)
            report["status"] = "complete"
        except Exception as exc:
            report = {"country": country, "item_name": item, "status": "error", "error": repr(exc)}
        report["runtime_seconds"] = round(time.time() - t0, 2)
        master["results"][f"{country}:{item}"] = report
        out.write_text(json.dumps(master, indent=2))
        sel = report.get("selected") or {}
        h = sel.get("holdout") or {}
        print(
            f"  {report['status']} holdout="
            f"{100*float(h.get('success_30_rate') or 0):.1f}% "
            f"n={h.get('n') or 0} "
            f"lb={sel.get('lookback')} age={sel.get('age_window')} "
            f"radius={sel.get('smooth_radius')}",
            flush=True,
        )

    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
