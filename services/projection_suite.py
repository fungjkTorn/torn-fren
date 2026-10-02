import argparse
import sqlite3
from pathlib import Path

from services.history_service import DB_PATH
from services.projection_chain_lab_v2 import (
    ARRIVAL_POLICIES,
    BASE_METHODS,
    Strategy,
    _active_target_rows,
    _qualified_series,
    _simulate_strategy,
    _summarize,
    _summarize_depth,
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


def _score(summary):
    if not summary:
        return (-1.0, float("inf"), float("inf"))
    rate = summary.get("actionable_arrival_hit_rate")
    if rate is None:
        rate = summary.get("arrival_hit_rate")
    return (
        float(rate if rate is not None else -1.0),
        -float(summary.get("median_absolute_error_seconds") or 1e18),
        -float(summary.get("p90_absolute_error_seconds") or 1e18),
    )


def _discover_items(countries):
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

    selected = []
    for country, item_name in rows:
        lower = item_name.lower()
        if (
            "plushie" in lower
            or lower in FLOWER_NAMES
            or lower == "xanax"
        ):
            selected.append((country, item_name))
    return selected


def _stage1(country, item_name, max_depth, min_history, shortlist):
    cycles, waits = _qualified_series(country, item_name, exclude_travel_day=True)
    from services.arrival_success_lab import TRAVEL_SECONDS
    travel_seconds = TRAVEL_SECONDS.get(country.lower())

    entries = []
    for life in BASE_METHODS:
        for wait in BASE_METHODS:
            strategy = Strategy(life, wait, "midpoint")
            rows = _simulate_strategy(
                cycles,
                waits,
                strategy,
                travel_seconds=travel_seconds,
                max_depth=max_depth,
                min_history=min_history,
            )
            by_depth = _summarize(rows, max_depth)
            active = _summarize_depth(_active_target_rows(rows))
            entries.append({
                "life": life,
                "wait": wait,
                "rows": rows,
                "by_depth": by_depth,
                "active": active,
            })

    chosen = set()

    # Keep finalists for the actual reachable-flight objective.
    for entry in sorted(entries, key=lambda e: _score(e["active"]), reverse=True)[:shortlist]:
        chosen.add((entry["life"], entry["wait"]))

    # Also keep the best candidates at every horizon so a depth-specific winner
    # is not discarded merely because another depth dominates active-target mix.
    for depth in range(1, max_depth + 1):
        ranked = sorted(
            entries,
            key=lambda e: _score(e["by_depth"].get(depth)),
            reverse=True,
        )
        for entry in ranked[:shortlist]:
            chosen.add((entry["life"], entry["wait"]))

    return cycles, waits, travel_seconds, entries, sorted(chosen)


def run_item(country, item_name, max_depth=4, min_history=8, shortlist=8):
    cycles, waits, travel_seconds, screening, finalists = _stage1(
        country,
        item_name,
        max_depth=max_depth,
        min_history=min_history,
        shortlist=shortlist,
    )

    final_entries = []
    for life, wait in finalists:
        for policy in ARRIVAL_POLICIES:
            strategy = Strategy(life, wait, policy)
            rows = _simulate_strategy(
                cycles,
                waits,
                strategy,
                travel_seconds=travel_seconds,
                max_depth=max_depth,
                min_history=min_history,
            )
            final_entries.append({
                "strategy": strategy,
                "rows": rows,
                "by_depth": _summarize(rows, max_depth),
                "active": _summarize_depth(_active_target_rows(rows)),
            })

    return {
        "country": country,
        "item_name": item_name,
        "valid_cycles": len(cycles),
        "screened_pairs": len(BASE_METHODS) ** 2,
        "finalist_pairs": len(finalists),
        "final_simulations": len(final_entries),
        "screening": screening,
        "final": final_entries,
    }


def _best(entries, selector):
    usable = []
    for e in entries:
        s = selector(e)
        if s:
            usable.append((e, s))
    if not usable:
        return None
    usable.sort(key=lambda x: _score(x[1]), reverse=True)
    return usable[0]


def _summary_line(strategy, s):
    return (
        f"{strategy.name} | n={s['n']} act={s['actionable_n']} "
        f"trip={_fmt_rate(s['actionable_arrival_hit_rate'])} "
        f"all={_fmt_rate(s['arrival_hit_rate'])} "
        f"early={_fmt_rate(s['early_rate'])} "
        f"late={_fmt_rate(s['late_rate'])} "
        f"MedAE={_fmt_minutes(s['median_absolute_error_seconds'])} "
        f"P90={_fmt_minutes(s['p90_absolute_error_seconds'])}"
    )


def print_item_report(result, max_depth=4):
    print("=" * 100)
    print(
        f"{result['country'].upper()} / {result['item_name']} | "
        f"{result['valid_cycles']} valid cycles | "
        f"screened {result['screened_pairs']} point-model pairs -> "
        f"{result['finalist_pairs']} finalists -> "
        f"{result['final_simulations']} full simulations"
    )

    best_active = _best(result["final"], lambda e: e["active"])
    if best_active:
        print("ACTIVE TARGET WINNER")
        print("  " + _summary_line(best_active[0]["strategy"], best_active[1]))

    for depth in range(1, max_depth + 1):
        winner = _best(result["final"], lambda e, d=depth: e["by_depth"].get(d))
        if winner:
            print(f"DEPTH {depth} WINNER")
            print("  " + _summary_line(winner[0]["strategy"], winner[1]))
    print()


def run_suite(countries=DEFAULT_COUNTRIES, max_depth=4, min_history=8, shortlist=8):
    items = _discover_items(countries)
    print(f"Discovered {len(items)} target items: " + ", ".join(
        f"{c.upper()}/{i}" for c, i in items
    ))
    print()

    results = []
    for idx, (country, item_name) in enumerate(items, 1):
        print(f"[{idx}/{len(items)}] Running {country.upper()} / {item_name} ...", flush=True)
        result = run_item(
            country,
            item_name,
            max_depth=max_depth,
            min_history=min_history,
            shortlist=shortlist,
        )
        results.append(result)
        print_item_report(result, max_depth=max_depth)

    print("=" * 100)
    print("SUITE SUMMARY")
    for result in results:
        best_active = _best(result["final"], lambda e: e["active"])
        if not best_active:
            continue
        print(
            f"{result['country'].upper():>3} / {result['item_name']:<28} "
            f"{_fmt_rate(best_active[1]['actionable_arrival_hit_rate']):>6}  "
            f"{best_active[0]['strategy'].name}"
        )

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Two-stage frozen travel-prediction tournament for core travel items."
    )
    parser.add_argument(
        "--countries",
        nargs="+",
        default=list(DEFAULT_COUNTRIES),
        help="Country codes to scan (default: can uni jap).",
    )
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--min-history", type=int, default=8)
    parser.add_argument(
        "--shortlist",
        type=int,
        default=8,
        help="Top lifetime/wait pairs retained per horizon before expensive arrival-policy testing.",
    )
    args = parser.parse_args()

    run_suite(
        countries=tuple(c.lower() for c in args.countries),
        max_depth=max(1, args.depth),
        min_history=max(3, args.min_history),
        shortlist=max(2, args.shortlist),
    )


if __name__ == "__main__":
    main()
