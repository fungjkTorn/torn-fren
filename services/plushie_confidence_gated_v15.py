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
from services.projection_grand_tournament_v7_engine import MIN_STOCK, SHORT_WAIT_SECONDS
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

LOOKBACKS = (12, 20, 30, 45, 60, 90)
AGE_WINDOWS = (0, 10, 20, 30)
DEPTH_MODES = ("all", "modal", "top2")
STATE_SCALES = (None, 1.0, 2.0)
PROB_THRESHOLDS = (0.45, 0.50, 0.55, 0.60, 0.65, 0.70)


def _mad(values):
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(vals) < 3:
        return 1.0
    med = statistics.median(vals)
    return max(1.0, 1.4826 * statistics.median(abs(v - med) for v in vals))


def _filter_history(prior, current, lookback, age_window):
    if age_window == 0:
        rows = [r for r in prior if int(r["age_seconds"]) == int(current["age_seconds"])]
    else:
        w = int(age_window) * 60
        rows = [r for r in prior if abs(float(r["age_seconds"]) - float(current["age_seconds"])) <= w]
    return rows[-int(lookback):]


def _state_weight(history, current, scale):
    if scale is None:
        return [1.0] * len(history)
    keys = ("gap", "life", "peak", "safe", "rate")
    spreads = {k: _mad([r["_state"].get(k) for r in history]) for k in keys}
    out = []
    for row in history:
        terms = []
        for k in keys:
            a = current["_state"].get(k)
            b = row["_state"].get(k)
            if a is None or b is None:
                continue
            terms.append(((float(a) - float(b)) / spreads[k]) ** 2)
        d2 = sum(terms) / max(1, len(terms))
        s = max(float(scale), 0.1)
        out.append(math.exp(-0.5 * d2 / (s * s)))
    return out


def _depth_subset(rows, weights, mode):
    if mode == "all":
        return rows, weights
    totals = {}
    for row, weight in zip(rows, weights):
        d = int(row["actual_target_depth"])
        totals[d] = totals.get(d, 0.0) + float(weight)
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return [], []
    allowed = {ranked[0][0]} if mode == "modal" else {d for d, _ in ranked[:2]}
    rr, ww = [], []
    for row, weight in zip(rows, weights):
        if int(row["actual_target_depth"]) in allowed:
            rr.append(row)
            ww.append(weight)
    return rr, ww


def _choose_wait(prior, current, travel, lookback, age_window, depth_mode, state_scale):
    rows = _filter_history(prior, current, lookback, age_window)
    if len(rows) < 6:
        return None
    weights = _state_weight(rows, current, state_scale)
    rows, weights = _depth_subset(rows, weights, depth_mode)
    if len(rows) < 5 or sum(weights) <= 0:
        return None

    scored = []
    for wait in WAIT_MINUTES:
        arrival_h = float(travel) + float(wait) * 60.0
        hits = []
        margins = []
        total = 0.0
        weighted_hits = 0.0
        for row, weight in zip(rows, weights):
            start_h = float(row["actual_start"]) - float(row["decision_timestamp"])
            end_h = float(row["actual_end"]) - float(row["decision_timestamp"])
            hit = int(start_h <= arrival_h < end_h)
            total += float(weight)
            weighted_hits += hit * float(weight)
            if hit:
                margins.append(min(arrival_h - start_h, end_h - arrival_h))
        if total <= 0:
            continue
        p = weighted_hits / total
        margin = statistics.median(margins) if margins else -1.0
        scored.append((p, margin, -wait, wait))

    if not scored:
        return None
    best = max(scored)
    return {
        "wait_minutes": float(best[3]),
        "predicted_probability": float(best[0]),
        "median_hit_margin_seconds": float(best[1]),
        "samples": len(rows),
    }


def _score_row(ctx, timeline, current, choice):
    departure = float(current["decision_timestamp"]) + choice["wait_minutes"] * 60.0
    arrival = departure + float(ctx.travel_seconds)
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
        "actual_target_depth": current["actual_target_depth"],
        "recommended_wait_minutes": choice["wait_minutes"],
        "predicted_probability": choice["predicted_probability"],
        "samples": choice["samples"],
        "quantity_on_arrival": qty,
        "success_30": hit,
        "short_wait_3m": short,
        "early_window": int(arrival < float(current["actual_start"])),
        "late_window": int(arrival >= float(current["actual_end"])),
    }


def run_config(ctx, timeline, decisions, lookback, age_window, depth_mode, state_scale):
    rows = []
    for current in decisions:
        now = float(current["decision_timestamp"])
        prior = [r for r in decisions if float(r["actual_end"]) + SHORT_WAIT_SECONDS < now]
        choice = _choose_wait(
            prior, current, ctx.travel_seconds,
            lookback, age_window, depth_mode, state_scale
        )
        if choice is not None:
            rows.append(_score_row(ctx, timeline, current, choice))
    return rows


def _inner_validation(rows, outer_split):
    train = [r for r in rows if r["decision_timestamp"] < outer_split]
    stamps = sorted({int(r["decision_timestamp"]) for r in train})
    if len(stamps) < 40:
        return train, []
    cut = max(1, int(len(stamps) * 0.75))
    val_stamps = set(stamps[cut:])
    val = [r for r in train if int(r["decision_timestamp"]) in val_stamps]
    return train, val


def _filtered(rows, threshold):
    return [r for r in rows if float(r.get("predicted_probability") or 0.0) >= threshold]


def _rank(summary, coverage):
    if not summary or not summary.get("n"):
        return (-1.0, -1.0, -1.0, -1.0)
    rate = float(summary.get("success_30_rate") or 0.0)
    return (
        rate,
        float(summary.get("success_or_short_wait_rate") or 0.0),
        coverage,
        -float(summary.get("late_rate") or 1.0),
    )


def run_item(country, item_name):
    ctx, timeline, decisions = build_dense_decisions(country, item_name, max_depth=10)
    if ctx.split_timestamp is None:
        raise RuntimeError("No outer split available")

    candidates = []
    total = len(LOOKBACKS) * len(AGE_WINDOWS) * len(DEPTH_MODES) * len(STATE_SCALES)
    done = 0

    for lb in LOOKBACKS:
        for age in AGE_WINDOWS:
            for depth_mode in DEPTH_MODES:
                for scale in STATE_SCALES:
                    rows = run_config(ctx, timeline, decisions, lb, age, depth_mode, scale)
                    train, val = _inner_validation(rows, ctx.split_timestamp)
                    hold = [r for r in rows if r["decision_timestamp"] >= ctx.split_timestamp]

                    for threshold in PROB_THRESHOLDS:
                        fval = _filtered(val, threshold)
                        fhold = _filtered(hold, threshold)
                        coverage = len(fval) / max(1, len(val))
                        va = summarize(fval)
                        ho = summarize(fhold)

                        candidates.append({
                            "lookback": lb,
                            "age_window": age,
                            "depth_mode": depth_mode,
                            "state_scale": scale,
                            "prob_threshold": threshold,
                            "validation_coverage": coverage,
                            "inner_validation": va,
                            "holdout": ho,
                            "rank_key": list(_rank(va, coverage)),
                        })

                    done += 1
                    if done % 25 == 0:
                        print(f"  scored {done}/{total} base configs", flush=True)

    # Enforce meaningful recommendation frequency: at least 35% of validation rows.
    viable = [c for c in candidates if c["validation_coverage"] >= 0.35 and (c["inner_validation"] or {}).get("n", 0) >= 40]
    pool = viable or candidates
    pool.sort(key=lambda x: tuple(x["rank_key"]), reverse=True)
    selected = pool[0] if pool else None

    return {
        "schema": "plushie-confidence-gated-v15-item-v1",
        "country": country,
        "item_name": item_name,
        "travel_seconds": ctx.travel_seconds,
        "decision_points": len(decisions),
        "candidate_configs": len(candidates),
        "selection_rule": (
            "Select phase-window model plus probability threshold on inner chronological validation only. "
            "Thresholding is allowed only if validation coverage is at least 35% and n>=40. "
            "Outer holdout is report-only. Goal is >=80% arrival success without collapsing recommendation frequency."
        ),
        "selected": selected,
        "top_finalists": pool[:20],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--output", default="data/plushie_confidence_gated_v15.json")
    p.add_argument("--only", action="append", default=[])
    args = p.parse_args()

    db = Path(args.db).resolve()
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")
    history_service.DB_PATH = db
    history_service._DB_READY = False

    wanted = {x.lower() for x in args.only}
    targets = TARGETS if not wanted else [
        x for x in TARGETS if f"{x[0]}:{x[1]}".lower() in wanted
    ]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    master = {"schema": "plushie-confidence-gated-v15-master-v1", "db_path": str(db), "results": {}}

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
            f"threshold={sel.get('prob_threshold')} "
            f"val_coverage={100*float(sel.get('validation_coverage') or 0):.1f}%",
            flush=True,
        )

    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
