import argparse
import json
import math
import sqlite3
import statistics
import time
from pathlib import Path

from services.history_service import DB_PATH
from services.country_regime_lab import analyze_country_regime
from services.projection_chain_lab_v3 import (
    ARRIVAL_POLICIES,
    BIAS_POLICIES,
    BASE_METHODS,
    EXTRA_LIFETIME_METHODS,
    EXTRA_WAIT_METHODS,
    V3Strategy,
    conservative_key,
    evaluate_strategy,
    _fmt_minutes,
    _fmt_rate,
)

FLOWER_NAMES = {
    "dahlia",
    "banana orchid",
    "crocus",
    "hawaiian flower",
    "heather",
    "ceibo flower",
    "edelweiss",
    "cherry blossom",
    "peony",
    "tribulus omanense",
    "african violet",
}

DEFAULT_COUNTRIES = ("can", "uni", "jap")
CHECKPOINT = Path("data/projection_overnight_v3_checkpoint.json")
REPORT = Path("data/projection_overnight_v3_report.json")


def discover_items(countries):
    placeholders = ",".join("?" for _ in countries)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT LOWER(country), item_name
            FROM stock_history
            WHERE LOWER(country) IN ({placeholders})
            ORDER BY LOWER(country), item_name COLLATE NOCASE
            """,
            tuple(c.lower() for c in countries),
        ).fetchall()

    out = []
    for country, item in rows:
        lower = item.lower()
        if "plushie" in lower or lower in FLOWER_NAMES or lower == "xanax":
            out.append((country, item))
    return out


def _serialize_summary(summary):
    if not summary:
        return None
    return {k: v for k, v in summary.items()}


def _entry_brief(entry, max_depth):
    return {
        "strategy": entry["strategy"].name,
        "split_timestamp": entry["split_timestamp"],
        "train_active": _serialize_summary(entry["train_active"]),
        "holdout_active": _serialize_summary(entry["holdout_active"]),
        "train_by_depth": {
            str(d): _serialize_summary(entry["train_by_depth"].get(d))
            for d in range(1, max_depth + 1)
        },
        "holdout_by_depth": {
            str(d): _serialize_summary(entry["holdout_by_depth"].get(d))
            for d in range(1, max_depth + 1)
        },
        "rolling_folds_by_depth": {
            str(d): [
                _serialize_summary(s)
                for s in (entry.get("rolling_folds_by_depth", {}).get(d) or [])
            ]
            for d in range(1, max_depth + 1)
        },
    }



def _fold_floor(entry, depth):
    folds = (entry.get("rolling_folds_by_depth") or {}).get(depth) or []
    rates = [
        f.get("wilson_lower_95")
        for f in folds
        if f and f.get("wilson_lower_95") is not None
    ]
    return min(rates) if rates else None


def _rank_train(entries, selector, depth=None):
    usable = []
    for entry in entries:
        summary = selector(entry)
        if summary:
            fold_floor = _fold_floor(entry, depth) if depth is not None else None
            usable.append((entry, summary, fold_floor))

    def key(item):
        entry, summary, fold_floor = item
        base = conservative_key(summary)
        # A model must be good across multiple chronological training folds, not
        # merely on the aggregate. Missing fold evidence is neutral for sparse
        # items; otherwise the worst fold is a strong tie-breaker.
        stability = fold_floor if fold_floor is not None else -1.0
        return (base[0], stability, base[1], base[2], base[3])

    usable.sort(key=key, reverse=True)
    return [(entry, summary) for entry, summary, _ in usable]


def _strategy_from_name_components(life, wait, arrival, bias):
    return V3Strategy(life, wait, arrival, bias)


def stage1_pairs(country, item_name, max_depth, min_history, shortlist):
    """
    Cheap-ish screening: all lifetime x wait models with midpoint arrival and no
    bias. Select finalists using TRAINING history only. Holdout is never used to
    decide who advances.
    """
    lifetimes = tuple(BASE_METHODS) + EXTRA_LIFETIME_METHODS
    waits = tuple(BASE_METHODS) + EXTRA_WAIT_METHODS
    entries = []

    for life in lifetimes:
        for wait in waits:
            strategy = _strategy_from_name_components(life, wait, "midpoint", "none")
            result = evaluate_strategy(
                country, item_name, strategy,
                max_depth=max_depth, min_history=min_history,
            )
            if result:
                entries.append(result)

    finalists = set()

    active_ranked = _rank_train(entries, lambda e: e["train_active"])
    for e, _ in active_ranked[:shortlist]:
        finalists.add((e["strategy"].lifetime, e["strategy"].wait))

    for depth in range(1, max_depth + 1):
        ranked = _rank_train(entries, lambda e, d=depth: e["train_by_depth"].get(d), depth=depth)
        for e, _ in ranked[:shortlist]:
            finalists.add((e["strategy"].lifetime, e["strategy"].wait))

    return entries, sorted(finalists)


def stage2_full(country, item_name, finalists, max_depth, min_history):
    """
    Expand only training-selected point-model finalists across arrival and
    depth-bias policies. Selection remains based on training data.
    """
    entries = []
    for life, wait in finalists:
        for arrival in ARRIVAL_POLICIES:
            for bias in BIAS_POLICIES:
                strategy = V3Strategy(life, wait, arrival, bias)
                result = evaluate_strategy(
                    country, item_name, strategy,
                    max_depth=max_depth, min_history=min_history,
                )
                if result:
                    entries.append(result)
    return entries


def _ensemble_summary(entries, depth=None, active=False, top_n=3):
    """
    Build a holdout ensemble whose members were chosen exclusively by TRAINING
    performance. For each frozen holdout issuance, median the selected models'
    recommended-arrival timestamps and score against real stock availability.
    """
    if active:
        ranked = _rank_train(entries, lambda e: e["train_active"])
    else:
        ranked = _rank_train(entries, lambda e: e["train_by_depth"].get(depth), depth=depth)
    members = [e for e, _ in ranked[:top_n]]
    if len(members) < 2:
        return None

    by_member = []
    for entry in members:
        split = entry["split_timestamp"]
        rows = [r for r in entry["rows"] if int(r["anchor_timestamp"]) >= split]
        if active:
            grouped = {}
            for r in rows:
                grouped.setdefault(r["anchor_timestamp"], []).append(r)
            selected = {}
            for anchor, group in grouped.items():
                reachable = sorted(
                    (r for r in group if r["actionable_from_anchor"]),
                    key=lambda r: r["depth"],
                )
                if reachable:
                    selected[(anchor, reachable[0]["depth"])] = reachable[0]
        else:
            selected = {
                (r["anchor_timestamp"], r["depth"]): r
                for r in rows if r["depth"] == depth
            }
        by_member.append(selected)

    common = set(by_member[0])
    for mapping in by_member[1:]:
        common &= set(mapping)
    if not common:
        return None

    scored = []
    for key in sorted(common):
        rows = [mapping[key] for mapping in by_member]
        arrival = statistics.median(r["recommended_arrival_timestamp"] for r in rows)
        actual_restock = rows[0]["actual_restock_timestamp"]
        actual_depletion = rows[0]["actual_depletion_timestamp"]
        hit = int(actual_restock <= arrival < actual_depletion)
        early = int(arrival < actual_restock)
        late = int(arrival >= actual_depletion)
        scored.append((hit, early, late))

    n = len(scored)
    hits = sum(x[0] for x in scored)
    p = hits / n
    z = 1.96
    denom = 1 + z*z/n
    lower = (
        p + z*z/(2*n)
        - z*math.sqrt((p*(1-p)+z*z/(4*n))/n)
    ) / denom

    return {
        "members": [e["strategy"].name for e in members],
        "n": n,
        "arrival_hit_rate": p,
        "wilson_lower_95": lower,
        "early_rate": sum(x[1] for x in scored) / n,
        "late_rate": sum(x[2] for x in scored) / n,
    }


def summarize_item(country, item_name, stage1, finalists, stage2, max_depth):
    result = {
        "country": country,
        "item_name": item_name,
        "country_regime_diagnostic": analyze_country_regime(country, item_name),
        "stage1_models": len(stage1),
        "finalist_pairs": len(finalists),
        "stage2_models": len(stage2),
        "active": {},
        "depths": {},
    }

    active_ranked = _rank_train(stage2, lambda e: e["train_active"])
    active_top = [e for e, _ in active_ranked[:5]]
    result["active"]["top5_selected_on_train"] = [
        _entry_brief(e, max_depth) for e in active_top
    ]
    result["active"]["ensemble_top3_holdout"] = _ensemble_summary(
        stage2, active=True, top_n=3
    )

    for depth in range(1, max_depth + 1):
        ranked = _rank_train(stage2, lambda e, d=depth: e["train_by_depth"].get(d), depth=depth)
        top = [e for e, _ in ranked[:5]]
        result["depths"][str(depth)] = {
            "top5_selected_on_train": [_entry_brief(e, max_depth) for e in top],
            "ensemble_top3_holdout": _ensemble_summary(
                stage2, depth=depth, active=False, top_n=3
            ),
        }
    return result


def _load_checkpoint():
    try:
        if CHECKPOINT.exists():
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"completed": {}, "started_at": int(time.time())}


def _save_checkpoint(data):
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(CHECKPOINT)


def _print_winner(label, block):
    top = block.get("top5_selected_on_train") or []
    if not top:
        print(f"  {label}: no eligible model")
        return
    winner = top[0]
    holdout = winner.get("holdout_active") if label == "ACTIVE" else None
    if holdout is None and label.startswith("D"):
        holdout = winner["holdout_by_depth"].get(label[1:])
    print(f"  {label}: {winner['strategy']}")
    if holdout:
        print(
            f"      holdout={_fmt_rate(holdout['arrival_hit_rate'])} "
            f"LCB95={_fmt_rate(holdout['wilson_lower_95'])} "
            f"early={_fmt_rate(holdout['early_rate'])} "
            f"late={_fmt_rate(holdout['late_rate'])} "
            f"MedAE={_fmt_minutes(holdout['median_absolute_error_seconds'])}"
        )
    ens = block.get("ensemble_top3_holdout")
    if ens:
        print(
            f"      ensemble3={_fmt_rate(ens['arrival_hit_rate'])} "
            f"LCB95={_fmt_rate(ens['wilson_lower_95'])} n={ens['n']}"
        )


def run(countries, max_depth=4, min_history=8, shortlist=10, resume=True):
    checkpoint = _load_checkpoint() if resume else {"completed": {}, "started_at": int(time.time())}
    items = discover_items(countries)
    print(f"Overnight V3: {len(items)} target items")
    print("Selection uses older training history only; newest holdout is report-only.")
    print()

    for idx, (country, item_name) in enumerate(items, 1):
        key = f"{country.lower()}::{item_name.lower()}"
        if key in checkpoint["completed"]:
            print(f"[{idx}/{len(items)}] SKIP completed {country.upper()} / {item_name}")
            continue

        started = time.time()
        print(f"[{idx}/{len(items)}] {country.upper()} / {item_name}", flush=True)

        stage1, finalists = stage1_pairs(
            country, item_name, max_depth, min_history, shortlist
        )
        print(
            f"  stage1 {len(stage1)} models -> {len(finalists)} point-model finalists",
            flush=True,
        )

        stage2 = stage2_full(
            country, item_name, finalists, max_depth, min_history
        )
        print(f"  stage2 {len(stage2)} full policy models", flush=True)

        summary = summarize_item(
            country, item_name, stage1, finalists, stage2, max_depth
        )
        summary["runtime_seconds"] = round(time.time() - started, 2)
        checkpoint["completed"][key] = summary
        _save_checkpoint(checkpoint)

        regime = summary.get("country_regime_diagnostic") or {}
        corr = regime.get("pearson_country_to_next_lifetime")
        if corr is not None:
            print(
                f"  country-regime diagnostic: n={regime.get('n')} "
                f"peers={regime.get('peer_items')} corr={corr:.3f} "
                "(experimental; not used for selection)"
            )

        _print_winner("ACTIVE", summary["active"])
        for d in range(1, max_depth + 1):
            _print_winner(f"D{d}", summary["depths"][str(d)])
        print(f"  runtime={summary['runtime_seconds']/60:.1f}m", flush=True)
        print()

    checkpoint["finished_at"] = int(time.time())
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    _save_checkpoint(checkpoint)
    print(f"Finished. Report: {REPORT}")
    print(f"Checkpoint: {CHECKPOINT}")


def main():
    p = argparse.ArgumentParser(description="Checkpointed overnight V3 travel-model tournament.")
    p.add_argument("--countries", nargs="+", default=list(DEFAULT_COUNTRIES))
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--min-history", type=int, default=8)
    p.add_argument("--shortlist", type=int, default=10)
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()
    run(
        tuple(c.lower() for c in args.countries),
        max_depth=max(1, args.depth),
        min_history=max(3, args.min_history),
        shortlist=max(3, args.shortlist),
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
