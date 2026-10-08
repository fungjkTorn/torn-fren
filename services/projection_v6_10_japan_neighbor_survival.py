import argparse
import json
import math
import statistics
from pathlib import Path

from services.projection_engine_v4 import build_item_context
from services.projection_engine_v6_3 import _examples, _distance


KS = (8, 12, 16, 24)
RECENT_LIMITS = (40, 80, 120, None)
TOD_WEIGHTS = (0.0, 0.5)
RECENCY_WEIGHTS = (0.0, 0.30)
GATES = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)


def _weighted_overlap_choice(chosen, travel_seconds):
    """
    Each historical analog contributes an interval in horizon-space where a
    departure would have landed while stock was alive:
        [actual restock horizon, actual depletion horizon)

    Choose the arrival horizon that maximizes weighted overlap of those
    historical success intervals. This predicts the decision directly rather
    than first predicting an exact restock timestamp.
    """
    intervals = []
    boundaries = {float(travel_seconds)}
    for dist, prior in chosen:
        lo = float(prior["horizon_seconds"])
        hi = lo + float(prior["target_lifetime_seconds"])
        if hi <= travel_seconds:
            continue
        lo = max(lo, float(travel_seconds))
        weight = 1.0 / max(0.05, float(dist))
        intervals.append((lo, hi, weight))
        boundaries.add(lo)
        boundaries.add(hi)

    if not intervals:
        return None

    ordered = sorted(boundaries)
    candidates = {float(travel_seconds)}
    for a, b in zip(ordered, ordered[1:]):
        if b > a:
            candidates.add((a + b) / 2.0)

    best = None
    total_weight = sum(w for _, _, w in intervals)
    for horizon in candidates:
        if horizon < travel_seconds:
            continue
        hit_weight = sum(w for lo, hi, w in intervals if lo <= horizon < hi)
        prob = hit_weight / total_weight if total_weight else 0.0
        margins = [
            min(horizon - lo, hi - horizon)
            for lo, hi, _ in intervals
            if lo <= horizon < hi
        ]
        margin = statistics.median(margins) if margins else -1.0
        score = (prob, margin, -horizon)
        if best is None or score > best[0]:
            best = (score, horizon, prob)
    return None if best is None else {
        "arrival_horizon_seconds": best[1],
        "predicted_success": best[2],
    }


def _rows_for_config(ctx, max_depth, k, recent_limit, tod_weight, recency_weight):
    by_depth = {d: _examples(ctx, depth=d) for d in range(1, max_depth + 1)}
    rows = []

    for depth, examples in by_depth.items():
        for idx, current in enumerate(examples):
            history = examples[:idx]
            if recent_limit:
                history = history[-recent_limit:]
            if len(history) < max(ctx.min_history, k):
                continue

            scored = []
            for age, prior in enumerate(history):
                dist = _distance(
                    current["features"], prior["features"], history,
                    tod_weight=tod_weight,
                )
                # Prefer newer analogs mildly when requested.
                freshness = (len(history) - age) / max(1, len(history))
                adjusted = dist * (1.0 + recency_weight * freshness)
                scored.append((adjusted, prior))
            scored.sort(key=lambda x: x[0])
            chosen = scored[:k]

            choice = _weighted_overlap_choice(chosen, float(ctx.travel_seconds))
            if choice is None:
                continue

            anchor_ts = float(current["anchor_ts"])
            arrival = anchor_ts + choice["arrival_horizon_seconds"]
            departure = arrival - float(ctx.travel_seconds)
            actual_r = float(current["actual_restock_timestamp"])
            actual_d = float(current["actual_depletion_timestamp"])

            rows.append({
                "anchor_timestamp": int(anchor_ts),
                "depth": depth,
                "predicted_success": float(choice["predicted_success"]),
                "recommended_arrival_timestamp": arrival,
                "recommended_departure_timestamp": departure,
                "actionable_from_anchor": int(departure >= anchor_ts),
                "arrival_hit": int(actual_r <= arrival < actual_d),
                "early_arrival": int(arrival < actual_r),
                "late_arrival": int(arrival >= actual_d),
            })
    return rows


def _active(rows, gate):
    grouped = {}
    for r in rows:
        grouped.setdefault(r["anchor_timestamp"], []).append(r)
    selected = []
    eligible_anchors = len(grouped)
    for group in grouped.values():
        candidates = sorted(
            (
                r for r in group
                if r["actionable_from_anchor"]
                and r["predicted_success"] >= gate
            ),
            key=lambda r: r["depth"],
        )
        if candidates:
            selected.append(candidates[0])
    return selected, eligible_anchors


def _summary(rows, eligible):
    n = len(rows)
    if not n:
        return {
            "declared_n": 0,
            "coverage": 0.0 if eligible else None,
            "hit_rate": None,
            "wilson_lower_95": None,
            "early_rate": None,
            "late_rate": None,
        }
    hits = sum(r["arrival_hit"] for r in rows)
    p = hits / n
    z = 1.959963984540054
    den = 1 + z*z/n
    center = p + z*z/(2*n)
    margin = z*math.sqrt((p*(1-p)+z*z/(4*n))/n)
    return {
        "declared_n": n,
        "coverage": n / eligible if eligible else None,
        "hit_rate": p,
        "wilson_lower_95": (center-margin)/den,
        "early_rate": sum(r["early_arrival"] for r in rows)/n,
        "late_rate": sum(r["late_arrival"] for r in rows)/n,
    }


def _fold_summaries(train_rows, gate, folds=4):
    anchors = sorted({r["anchor_timestamp"] for r in train_rows})
    if len(anchors) < 40:
        return []
    chunks = []
    size = max(10, len(anchors)//folds)
    for i in range(folds):
        part = anchors[i*size:] if i == folds-1 else anchors[i*size:(i+1)*size]
        if not part:
            continue
        aset = set(part)
        rows = [r for r in train_rows if r["anchor_timestamp"] in aset]
        selected, eligible = _active(rows, gate)
        chunks.append(_summary(selected, eligible))
    return chunks


def main():
    p = argparse.ArgumentParser(
        description="V6.10 direct analog stock-alive decision model for Xanax"
    )
    p.add_argument("country", nargs="?", default="jap")
    p.add_argument("item_name", nargs="?", default="Xanax")
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--output", default="data/projection_v6_10_japan_neighbor_survival.json")
    args = p.parse_args()

    ctx = build_item_context(
        args.country.lower(), args.item_name,
        max_depth=max(2, args.depth), min_history=8
    )
    target = 0.75 if args.item_name.lower() == "xanax" else 0.80
    results = []

    for k in KS:
        for recent in RECENT_LIMITS:
            for tod in TOD_WEIGHTS:
                for recency in RECENCY_WEIGHTS:
                    rows = _rows_for_config(
                        ctx, max(2, args.depth), k, recent, tod, recency
                    )
                    train = [r for r in rows if r["anchor_timestamp"] < ctx.split_timestamp]
                    hold = [r for r in rows if r["anchor_timestamp"] >= ctx.split_timestamp]

                    for gate in GATES:
                        train_sel, train_eligible = _active(train, gate)
                        hold_sel, hold_eligible = _active(hold, gate)
                        ts = _summary(train_sel, train_eligible)
                        hs = _summary(hold_sel, hold_eligible)
                        folds = _fold_summaries(train, gate)
                        stable = (
                            len(folds) >= 3
                            and sum(
                                1 for f in folds
                                if (f.get("declared_n") or 0) >= 3
                                and (f.get("hit_rate") or 0) >= target - 0.10
                            ) >= 3
                        )
                        valid = (
                            (ts.get("declared_n") or 0) >= 15
                            and (ts.get("hit_rate") or 0) >= target
                            and stable
                        )
                        results.append({
                            "k": k, "recent_limit": recent,
                            "tod_weight": tod, "recency_weight": recency,
                            "gate": gate, "valid_on_train": valid,
                            "stable_on_train_folds": stable,
                            "train": ts, "rolling_train_folds": folds,
                            "holdout": hs,
                        })

    results.sort(key=lambda r: (
        int(r["valid_on_train"]),
        r["train"].get("wilson_lower_95") or 0,
        r["train"].get("hit_rate") or 0,
        r["train"].get("coverage") or 0,
        r["train"].get("declared_n") or 0,
    ), reverse=True)

    selected = results[0] if results else None
    report = {
        "country": args.country.lower(),
        "item_name": args.item_name,
        "target": target,
        "valid_cycles": len(ctx.cycles),
        "selected_on_train": selected,
        "top20": results[:20],
        "note": (
            "Directly predicts a stock-alive arrival using similar prior states. "
            "Selection uses training only; if valid_on_train is false, reject the policy."
        ),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nSaved full report to {out}")


if __name__ == "__main__":
    main()
