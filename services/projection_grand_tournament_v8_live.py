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
    rolling_folds,
    split_rows,
    summarize,
)


def _rank(train, folds):
    if not train or train.get("success_30_rate") is None:
        return (-1, -1, -1, -1)
    stable = 0.0
    usable = [f for f in folds if (f.get("n") or 0) >= 20]
    if usable:
        stable = sum((f.get("success_30_rate") or 0) for f in usable) / len(usable)
    return (
        int((train.get("success_30_rate") or 0) >= 0.90),
        train.get("success_30_rate") or 0,
        train.get("wilson_lower_95") or 0,
        stable,
    )


def run(country="jap", item_name="Xanax", max_depth=8, mc_samples=300, shortlist=40):
    started = time.time()
    ctx, timeline, decisions = build_live_decisions(
        country, item_name, max_depth=max_depth, min_history=8
    )
    candidates = []

    for lb in DIRECT_LOOKBACKS:
        for age in DIRECT_AGE_WINDOWS:
            for tod in DIRECT_TOD_HOURS:
                for method in DIRECT_METHODS:
                    for frac in DIRECT_FRACTIONS:
                        rows = direct_rows(ctx, timeline, decisions, lb, age, tod, method, frac)
                        train, hold = split_rows(ctx, rows)
                        folds = rolling_folds(ctx, rows)
                        candidates.append({
                            "family": "direct_live_horizon",
                            "config": f"lb={lb}|age={age}|tod={tod}|m={method}|f={frac}",
                            "train": summarize(train),
                            "holdout": summarize(hold),
                            "rolling_train_folds": folds,
                        })

    # Mechanics family is smaller but materially different: it bootstraps
    # depletion->restock gaps and >=30 durations while conditioning the first
    # wait on the fact that the current sold-out period has already survived to
    # the simulated decision time.
    for lb in MC_LOOKBACKS:
        for q in MC_QUANTILES:
            for frac in MC_FRACTIONS:
                rows = mechanics_rows(
                    ctx, timeline, decisions, lb, q, frac, samples=mc_samples
                )
                train, hold = split_rows(ctx, rows)
                folds = rolling_folds(ctx, rows)
                candidates.append({
                    "family": "conditional_bootstrap_mechanics",
                    "config": f"lb={lb}|q={q}|f={frac}|samples={mc_samples}",
                    "train": summarize(train),
                    "holdout": summarize(hold),
                    "rolling_train_folds": folds,
                })

    for c in candidates:
        c["rank_key"] = list(_rank(c["train"], c["rolling_train_folds"]))
    candidates.sort(key=lambda c: tuple(c["rank_key"]), reverse=True)

    return {
        "schema": "grand-tournament-v8-live-state-v1",
        "country": country.lower(),
        "item_name": item_name,
        "valid_cycles": len(ctx.cycles),
        "decision_points": len(decisions),
        "decision_offsets_minutes": [0,15,30,45,60,75,90,105,120],
        "success_definition": "quantity_on_arrival >= 30",
        "short_wait_definition": "quantity reaches >=30 within 180 seconds after an early arrival",
        "product_objective": (
            "At an arbitrary live sold-out decision time, use only information "
            "known then and recommend the next soonest reachable >=30-stock arrival."
        ),
        "candidate_configs_tested": len(candidates),
        "runtime_seconds": round(time.time() - started, 3),
        "selected_on_training": candidates[0] if candidates else None,
        "top_finalists": candidates[:max(10, shortlist)],
    }


def main():
    p = argparse.ArgumentParser(description="V8 live-state grand tournament")
    p.add_argument("--item-country", default="jap")
    p.add_argument("--item-name", default="Xanax")
    p.add_argument("--depth", type=int, default=8)
    p.add_argument("--mc-samples", type=int, default=300)
    p.add_argument("--shortlist", type=int, default=40)
    p.add_argument("--output")
    a = p.parse_args()

    report = run(
        a.item_country, a.item_name, max_depth=max(2, a.depth),
        mc_samples=max(100, a.mc_samples), shortlist=max(10, a.shortlist)
    )
    s = report.get("selected_on_training") or {}
    tr = s.get("train") or {}
    ho = s.get("holdout") or {}
    print(
        f"{report['country'].upper()} / {report['item_name']} | "
        f"decisions={report['decision_points']} candidates={report['candidate_configs_tested']} | "
        f"train={100*(tr.get('success_30_rate') or 0):.1f}% "
        f"(+short={100*(tr.get('success_or_short_wait_rate') or 0):.1f}%) | "
        f"holdout={100*(ho.get('success_30_rate') or 0):.1f}% "
        f"(+short={100*(ho.get('success_or_short_wait_rate') or 0):.1f}%) "
        f"n={ho.get('n') or 0} | {s.get('family')} {s.get('config')}",
        flush=True,
    )
    out = Path(
        a.output or
        f"data/projection_grand_v8_live_{a.item_country.lower()}_"
        f"{a.item_name.lower().replace(' ','_')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Saved {out}", flush=True)


if __name__ == "__main__":
    main()
