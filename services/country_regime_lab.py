import argparse
import math
import sqlite3
import statistics

from services.history_service import (
    DB_PATH,
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)


def _pearson(xs, ys):
    if len(xs) < 5 or len(xs) != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = math.sqrt(sum(v*v for v in dx) * sum(v*v for v in dy))
    if denom <= 0:
        return None
    return sum(a*b for a, b in zip(dx, dy)) / denom


def _normal_cycles(country, item_name):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, _ = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    cycles, _active, _waits = _build_validated_cycles(rows, country, item_name)
    return [
        c for c in cycles
        if c.get("complete")
        and not c.get("tiny_restock")
        and c.get("valid_lifetime")
        and c.get("lifetime_seconds")
    ]


def _country_items(country):
    with sqlite3.connect(DB_PATH) as conn:
        return [
            row[0]
            for row in conn.execute(
                """
                SELECT DISTINCT item_name
                FROM stock_history
                WHERE LOWER(country) = LOWER(?)
                ORDER BY item_name COLLATE NOCASE
                """,
                (country,),
            ).fetchall()
        ]


def _latest_prior_ratio(cycles, anchor_ts, lookback_seconds=6*3600):
    prior = [
        c for c in cycles
        if c.get("depletion_time") is not None
        and int(c["depletion_time"]) < int(anchor_ts)
        and int(anchor_ts) - int(c["depletion_time"]) <= lookback_seconds
    ]
    if not prior:
        return None
    historical = [
        float(c["lifetime_seconds"])
        for c in cycles
        if c.get("lifetime_seconds") is not None
        and int(c["depletion_time"]) < int(anchor_ts)
    ]
    if len(historical) < 8:
        return None
    baseline = statistics.median(historical)
    if baseline <= 0:
        return None
    return float(prior[-1]["lifetime_seconds"]) / baseline


def analyze_country_regime(country, target_item):
    target = _normal_cycles(country, target_item)
    if len(target) < 12:
        return {"n": 0, "reason": "insufficient target cycles"}

    other = {}
    for item in _country_items(country):
        if item.lower() == target_item.lower():
            continue
        cycles = _normal_cycles(country, item)
        if len(cycles) >= 8:
            other[item] = cycles

    rows = []
    for i in range(1, len(target)):
        previous = target[i-1]
        current = target[i]
        anchor = previous["depletion_time"]
        ratios = []
        for cycles in other.values():
            ratio = _latest_prior_ratio(cycles, anchor)
            if ratio is not None:
                ratios.append(ratio)
        if len(ratios) < 2:
            continue

        target_history = [
            float(c["lifetime_seconds"])
            for c in target[:i]
            if c.get("lifetime_seconds") is not None
        ]
        if len(target_history) < 8:
            continue
        target_baseline = statistics.median(target_history)
        target_ratio = float(current["lifetime_seconds"]) / target_baseline if target_baseline else None
        if target_ratio is None:
            continue

        rows.append({
            "anchor_timestamp": int(anchor),
            "country_regime_ratio": statistics.median(ratios),
            "target_next_lifetime_ratio": target_ratio,
            "peer_count": len(ratios),
        })

    corr = _pearson(
        [r["country_regime_ratio"] for r in rows],
        [r["target_next_lifetime_ratio"] for r in rows],
    )
    return {
        "country": country.lower(),
        "target_item": target_item,
        "n": len(rows),
        "peer_items": len(other),
        "pearson_country_to_next_lifetime": corr,
        "rows": rows,
        "interpretation": (
            "experimental only; promote only if correlation is stable and "
            "improves frozen holdout prediction"
        ),
    }


def main():
    p = argparse.ArgumentParser(description="Test whether same-country item activity predicts target depletion lifetime.")
    p.add_argument("country")
    p.add_argument("item_name")
    args = p.parse_args()
    result = analyze_country_regime(args.country, args.item_name)
    print(
        f"{result.get('country','').upper()} / {result.get('target_item')} "
        f"n={result.get('n')} peers={result.get('peer_items')} "
        f"corr={result.get('pearson_country_to_next_lifetime')}"
    )
    print(result.get("interpretation") or result.get("reason"))


if __name__ == "__main__":
    main()
