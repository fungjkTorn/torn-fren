import argparse
import json
import time
from pathlib import Path

from services.projection_grand_tournament_v8_live_engine import (
    DIRECT_AGE_WINDOWS,
    DIRECT_FRACTIONS,
    DIRECT_LOOKBACKS,
    DIRECT_METHODS,
    DIRECT_TOD_HOURS,
    MC_FRACTIONS,
    MC_LOOKBACKS,
    MC_QUANTILES,
    build_live_decisions,
    direct_rows,
    mechanics_rows,
    summarize,
)


SCHEMA = "grand-tournament-v8-1-age-adaptive-v1"


def _rank(summary):
    n = summary.get("n") or 0
    rate = summary.get("success_30_rate")
    if rate is None or n < 25:
        return (-1, -1, -1, -1)
    return (
        int(rate >= 0.90),
        rate,
        summary.get("wilson_lower_95") or 0.0,
        summary.get("success_or_short_wait_rate") or 0.0,
    )


def _split_by_age(ctx, rows, age_seconds):
    train = [
        r for r in rows
        if r["decision_timestamp"] < ctx.split_timestamp
        and int(r["age_seconds"]) == int(age_seconds)
    ]
    hold = [
        r for r in rows
        if r["decision_timestamp"] >= ctx.split_timestamp
        and int(r["age_seconds"]) == int(age_seconds)
    ]
    return train, hold


def run(country="jap", item_name="Xanax", max_depth=8, mc_samples=300):
    started = time.time()
    ctx, timeline, decisions = build_live_decisions(
        country, item_name, max_depth=max_depth, min_history=8
    )
    ages = sorted({int(r["age_seconds"]) for r in decisions})
    best = {age: None for age in ages}
    candidates_tested = 0

    def consider(family, config, rows):
        nonlocal candidates_tested
        candidates_tested += 1
        for age in ages:
            train_rows, hold_rows = _split_by_age(ctx, rows, age)
            ts = summarize(train_rows)
            key = _rank(ts)
            current = best[age]
            if current is None or key > tuple(current["rank_key"]):
                best[age] = {
                    "family": family,
                    "config": config,
                    "rank_key": list(key),
                    "train": ts,
                    "holdout": summarize(hold_rows),
                    "_train_rows": train_rows,
                    "_hold_rows": hold_rows,
                }

    for lb in DIRECT_LOOKBACKS:
        for age_window in DIRECT_AGE_WINDOWS:
            for tod in DIRECT_TOD_HOURS:
                for method in DIRECT_METHODS:
                    for frac in DIRECT_FRACTIONS:
                        rows = direct_rows(
                            ctx, timeline, decisions,
                            lb, age_window, tod, method, frac
                        )
                        consider(
                            "direct_live_horizon",
                            f"lb={lb}|agewin={age_window}|tod={tod}|m={method}|f={frac}",
                            rows,
                        )

    for lb in MC_LOOKBACKS:
        for q in MC_QUANTILES:
            for frac in MC_FRACTIONS:
                rows = mechanics_rows(
                    ctx, timeline, decisions,
                    lb, q, frac, samples=mc_samples
                )
                consider(
                    "conditional_bootstrap_mechanics",
                    f"lb={lb}|q={q}|f={frac}|samples={mc_samples}",
                    rows,
                )

    selected_train = []
    selected_hold = []
    by_age = {}
    for age in ages:
        entry = best[age]
        if entry is None:
            continue
        selected_train.extend(entry.pop("_train_rows"))
        selected_hold.extend(entry.pop("_hold_rows"))
        by_age[str(age // 60)] = entry

    report = {
        "schema": SCHEMA,
        "country": country.lower(),
        "item_name": item_name,
        "valid_cycles": len(ctx.cycles),
        "decision_points": len(decisions),
        "candidate_configs_tested": candidates_tested,
        "selection": (
            "Select one model configuration independently for each current "
            "sold-out age bucket using training data only; combine untouched "
            "holdout rows afterward."
        ),
        "success_definition": "quantity_on_arrival >= 30",
        "short_wait_definition": "quantity reaches >=30 within 180 seconds after early arrival",
        "aggregate_selected": {
            "train": summarize(selected_train),
            "holdout": summarize(selected_hold),
        },
        "selected_by_age_minutes": by_age,
        "runtime_seconds": round(time.time() - started, 3),
    }
    return report


def main():
    p = argparse.ArgumentParser(
        description="V8.1 age-adaptive live-state tournament"
    )
    p.add_argument("--item-country", default="jap")
    p.add_argument("--item-name", default="Xanax")
    p.add_argument("--depth", type=int, default=8)
    p.add_argument("--mc-samples", type=int, default=300)
    p.add_argument("--output")
    a = p.parse_args()

    report = run(
        a.item_country, a.item_name,
        max_depth=max(2, a.depth),
        mc_samples=max(100, a.mc_samples),
    )
    agg = report["aggregate_selected"]
    tr = agg["train"]
    ho = agg["holdout"]
    print(
        f"{report['country'].upper()} / {report['item_name']} AGE-ADAPTIVE | "
        f"decisions={report['decision_points']} configs={report['candidate_configs_tested']} | "
        f"train={100*(tr.get('success_30_rate') or 0):.1f}% "
        f"(+short={100*(tr.get('success_or_short_wait_rate') or 0):.1f}%) | "
        f"holdout={100*(ho.get('success_30_rate') or 0):.1f}% "
        f"(+short={100*(ho.get('success_or_short_wait_rate') or 0):.1f}%) "
        f"n={ho.get('n') or 0}",
        flush=True,
    )
    for age, entry in sorted(
        report["selected_by_age_minutes"].items(),
        key=lambda kv: int(kv[0])
    ):
        tr = entry["train"]; ho = entry["holdout"]
        print(
            f"  age={age:>3}m | {entry['family']:<31} "
            f"train={100*(tr.get('success_30_rate') or 0):5.1f}% n={tr.get('n') or 0:<3} | "
            f"hold={100*(ho.get('success_30_rate') or 0):5.1f}% "
            f"(+short={100*(ho.get('success_or_short_wait_rate') or 0):5.1f}%) "
            f"n={ho.get('n') or 0:<3} | {entry['config']}",
            flush=True,
        )

    out = Path(
        a.output or
        f"data/projection_grand_v8_1_age_{a.item_country.lower()}_"
        f"{a.item_name.lower().replace(' ','_')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Saved {out}", flush=True)


if __name__ == "__main__":
    main()
