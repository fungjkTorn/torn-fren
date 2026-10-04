import argparse
import statistics
from dataclasses import dataclass
from itertools import product

from services.history_service import (
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)


@dataclass(frozen=True)
class Strategy:
    lifetime: str
    wait: str

    @property
    def name(self):
        return f"{self.lifetime} + {self.wait}"


def _mean(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _median(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _weighted_recent(values, n=5):
    vals = [float(v) for v in values if v is not None][-n:]
    if not vals:
        return None
    weights = list(range(1, len(vals) + 1))
    return sum(v * w for v, w in zip(vals, weights)) / sum(weights)


def _estimate(values, method):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None

    if method == "all_median":
        return _median(vals)
    if method == "recent3_mean":
        return _mean(vals[-3:])
    if method == "recent5_mean":
        return _mean(vals[-5:])
    if method == "recent5_median":
        return _median(vals[-5:])
    if method == "recent10_median":
        return _median(vals[-10:])
    if method == "weighted_recent5":
        return _weighted_recent(vals, 5)

    raise ValueError(f"Unknown estimator: {method}")


LIFETIME_METHODS = (
    "all_median",
    "recent3_mean",
    "recent5_mean",
    "recent5_median",
    "recent10_median",
    "weighted_recent5",
)

WAIT_METHODS = (
    "all_median",
    "recent3_mean",
    "recent5_mean",
    "recent5_median",
    "recent10_median",
    "weighted_recent5",
)


def _qualified_series(country, item_name):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, _ = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    cycles, _active, wait_samples = _build_validated_cycles(rows, country, item_name)

    valid_cycles = [
        c for c in cycles
        if c.get("complete")
        and not c.get("tiny_restock")
        and c.get("valid_lifetime")
        and c.get("restock_time") is not None
        and c.get("depletion_time") is not None
        and c.get("lifetime_seconds") is not None
    ]

    wait_by_from_depletion = {
        int(s["from_depletion"]): float(s["seconds"])
        for s in wait_samples
        if s.get("valid")
        and s.get("from_depletion") is not None
        and s.get("seconds") is not None
    }

    return valid_cycles, wait_by_from_depletion


def _score_strategy(cycles, waits_by_depletion, strategy, max_depth=4, min_history=8):
    rows = []

    # Anchor on a REAL observed depletion. Everything used to predict from this
    # point must have happened at or before that depletion timestamp.
    for anchor_i, anchor_cycle in enumerate(cycles):
        anchor_ts = int(anchor_cycle["depletion_time"])

        known_lifetimes = [
            float(c["lifetime_seconds"])
            for c in cycles[: anchor_i + 1]
            if int(c["depletion_time"]) <= anchor_ts
        ]
        known_waits = [
            float(waits_by_depletion[int(c["depletion_time"])])
            for c in cycles[:anchor_i]
            if int(c["depletion_time"]) in waits_by_depletion
            and int(c["depletion_time"]) < anchor_ts
        ]

        if len(known_lifetimes) < min_history or len(known_waits) < min_history:
            continue

        life_est = _estimate(known_lifetimes, strategy.lifetime)
        wait_est = _estimate(known_waits, strategy.wait)
        if not life_est or not wait_est:
            continue

        # P1 from an observed depletion is anchor + predicted zero wait.
        projected_restock = float(anchor_ts) + float(wait_est)

        for depth in range(1, max_depth + 1):
            target_i = anchor_i + depth
            if target_i >= len(cycles):
                break

            target_cycle = cycles[target_i]
            actual_restock = float(target_cycle["restock_time"])
            actual_depletion = float(target_cycle["depletion_time"])

            # For depth > 1, cross one fully unobserved projected cycle.
            if depth > 1:
                projected_restock += float(life_est) + float(wait_est)

            error = actual_restock - projected_restock

            # A neutral arrival target uses half the predicted stock lifetime.
            # This isolates whether the frozen chain would have put a traveler
            # on the shelf while stock actually existed.
            predicted_arrival = projected_restock + (float(life_est) / 2.0)
            arrival_hit = int(actual_restock <= predicted_arrival < actual_depletion)

            rows.append({
                "anchor_timestamp": anchor_ts,
                "depth": depth,
                "predicted_restock_timestamp": projected_restock,
                "actual_restock_timestamp": actual_restock,
                "actual_depletion_timestamp": actual_depletion,
                "signed_error_seconds": error,
                "absolute_error_seconds": abs(error),
                "arrival_hit": arrival_hit,
                "lifetime_estimate_seconds": life_est,
                "wait_estimate_seconds": wait_est,
            })

    return rows


def _summarize(rows):
    by_depth = {}
    for depth in sorted({r["depth"] for r in rows}):
        d = [r for r in rows if r["depth"] == depth]
        if not d:
            continue
        signed = [r["signed_error_seconds"] for r in d]
        absolute = [r["absolute_error_seconds"] for r in d]
        by_depth[depth] = {
            "n": len(d),
            "median_absolute_error_seconds": statistics.median(absolute),
            "mean_absolute_error_seconds": statistics.mean(absolute),
            "signed_bias_seconds": statistics.median(signed),
            "arrival_hit_rate": sum(r["arrival_hit"] for r in d) / len(d),
        }
    return by_depth


def tournament(country, item_name, max_depth=4, min_history=8):
    cycles, waits = _qualified_series(country, item_name)
    results = []

    for life_method, wait_method in product(LIFETIME_METHODS, WAIT_METHODS):
        strategy = Strategy(life_method, wait_method)
        rows = _score_strategy(
            cycles,
            waits,
            strategy,
            max_depth=max_depth,
            min_history=min_history,
        )
        summaries = _summarize(rows)
        results.append({
            "strategy": strategy,
            "rows": rows,
            "by_depth": summaries,
        })

    return {
        "country": country.lower(),
        "item_name": item_name,
        "valid_cycles": len(cycles),
        "strategies": results,
    }


def rank_for_depth(result, depth):
    ranked = []
    for entry in result["strategies"]:
        summary = entry["by_depth"].get(depth)
        if not summary:
            continue
        ranked.append((entry["strategy"], summary))

    # Primary objective: arrival success. Secondary: median timing error.
    ranked.sort(
        key=lambda x: (
            -x[1]["arrival_hit_rate"],
            x[1]["median_absolute_error_seconds"],
            x[1]["mean_absolute_error_seconds"],
        )
    )
    return ranked


def _fmt_minutes(seconds):
    return f"{float(seconds) / 60.0:.1f}m"


def print_report(result, top=8, max_depth=4):
    print(
        f"Projection-chain tournament: {result['country'].upper()} / "
        f"{result['item_name']} ({result['valid_cycles']} valid cycles)"
    )
    print("Frozen historical anchors only; no re-anchoring after issuance.")
    print()

    for depth in range(1, max_depth + 1):
        ranked = rank_for_depth(result, depth)
        print(f"DEPTH {depth}")
        if not ranked:
            print("  insufficient samples")
            print()
            continue

        for strategy, s in ranked[:top]:
            print(
                f"  {strategy.name:<40} "
                f"n={s['n']:<4} "
                f"arrival={s['arrival_hit_rate'] * 100:5.1f}%  "
                f"MedAE={_fmt_minutes(s['median_absolute_error_seconds']):>7}  "
                f"MAE={_fmt_minutes(s['mean_absolute_error_seconds']):>7}  "
                f"bias={_fmt_minutes(s['signed_bias_seconds']):>7}"
            )
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Backtest frozen P1/P2/P3/P4 projection chains."
    )
    parser.add_argument("country")
    parser.add_argument("item_name")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--min-history", type=int, default=8)
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()

    result = tournament(
        args.country,
        args.item_name,
        max_depth=max(1, args.depth),
        min_history=max(3, args.min_history),
    )
    print_report(result, top=max(1, args.top), max_depth=max(1, args.depth))


if __name__ == "__main__":
    main()
