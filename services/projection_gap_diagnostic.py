import argparse
import datetime as dt
import statistics

from services.history_service import (
    _build_validated_cycles,
    _get_all_item_rows_with_source,
    _suppress_provider_bounces,
)


def _fmt_ts(ts):
    if ts is None:
        return "-"
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_dur(seconds):
    if seconds is None:
        return "-"
    seconds = float(seconds)
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours >= 1:
        return f"{sign}{int(hours)}h {int(minutes)}m {secs:.0f}s"
    return f"{sign}{int(minutes)}m {secs:.0f}s"


def _median(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _cycle_line(index, cycle):
    reasons = "; ".join(cycle.get("exclusion_reasons") or []) or "-"
    return (
        f"  cycle[{index}] restock={_fmt_ts(cycle.get('restock_time'))} "
        f"depletion={_fmt_ts(cycle.get('depletion_time'))} "
        f"life={_fmt_dur(cycle.get('lifetime_seconds'))} "
        f"peak={cycle.get('peak_quantity')} "
        f"tiny={bool(cycle.get('tiny_restock'))} "
        f"valid_life={bool(cycle.get('valid_lifetime'))} "
        f"restock_clean={cycle.get('restock_boundary_clean')} "
        f"depletion_clean={cycle.get('depletion_boundary_clean')} "
        f"max_gap={_fmt_dur(cycle.get('max_collection_gap_seconds'))} "
        f"reasons={reasons}"
    )


def diagnose(country, item_name, anchors, hours=10.0, raw_limit=120):
    raw = _get_all_item_rows_with_source(country, item_name)
    cleaned, suppressed = _suppress_provider_bounces(raw)
    rows = [(ts, qty) for ts, qty, _source in cleaned]
    cycles, active, waits = _build_validated_cycles(rows, country, item_name)

    completed = [c for c in cycles if c.get("complete")]
    normal = [c for c in completed if not c.get("tiny_restock")]
    wait_by_dep = {
        int(w["from_depletion"]): w
        for w in waits
        if w.get("from_depletion") is not None
    }

    normal_waits = [
        float(w["seconds"])
        for w in waits
        if w.get("valid") and w.get("seconds") is not None
    ]
    median_wait = _median(normal_waits)
    median_life = _median(
        c.get("lifetime_seconds")
        for c in completed
        if c.get("valid_lifetime") and not c.get("tiny_restock")
    )

    print(f"Projection gap diagnostic: {country.upper()} / {item_name}")
    print(f"raw rows={len(raw)} cleaned rows={len(cleaned)} suppressed bounces={len(suppressed)}")
    print(f"completed cycles={len(completed)} normal cycles={len(normal)}")
    print(f"median valid normal wait={_fmt_dur(median_wait)}")
    print(f"median valid normal lifetime={_fmt_dur(median_life)}")
    print()

    for anchor in anchors:
        anchor = int(anchor)
        print("=" * 100)
        print(f"ANCHOR {anchor} = {_fmt_ts(anchor)}")

        exact_cycle_i = next(
            (i for i, c in enumerate(completed)
             if c.get("depletion_time") is not None
             and int(c["depletion_time"]) == anchor),
            None,
        )
        if exact_cycle_i is None:
            nearest = sorted(
                enumerate(completed),
                key=lambda p: abs(int(p[1].get("depletion_time") or 0) - anchor),
            )[:3]
            print("No completed cycle has this exact depletion timestamp.")
            for i, c in nearest:
                print("NEAREST " + _cycle_line(i, c))
        else:
            lo = max(0, exact_cycle_i - 3)
            hi = min(len(completed), exact_cycle_i + 7)
            print(f"Detected completed cycles around anchor (indexes {lo}..{hi-1}):")
            for i in range(lo, hi):
                prefix = ">>" if i == exact_cycle_i else "  "
                print(prefix + _cycle_line(i, completed[i]))

            outgoing = wait_by_dep.get(anchor)
            print()
            print("VALIDATED WAIT FROM ANCHOR:")
            if outgoing is None:
                print("  NONE")
            else:
                reasons = "; ".join(outgoing.get("exclusion_reasons") or []) or "-"
                print(
                    f"  to={_fmt_ts(outgoing.get('to_restock'))} "
                    f"seconds={_fmt_dur(outgoing.get('seconds'))} "
                    f"valid={outgoing.get('valid')} "
                    f"bridged_tiny={outgoing.get('bridged_tiny_restock_count')} "
                    f"max_gap={_fmt_dur(outgoing.get('max_collection_gap_seconds'))} "
                    f"coverage={outgoing.get('coverage_method')} "
                    f"reasons={reasons}"
                )
                if median_wait:
                    print(
                        f"  wait / median = {float(outgoing['seconds']) / median_wait:.2f}x"
                    )

            print()
            print("IMMEDIATE REAL CYCLE TRANSITIONS:")
            for i in range(exact_cycle_i, min(len(completed) - 1, exact_cycle_i + 5)):
                a = completed[i]
                b = completed[i + 1]
                gap = int(b["restock_time"]) - int(a["depletion_time"])
                print(
                    f"  cycle[{i}] -> cycle[{i+1}]: gap={_fmt_dur(gap)} "
                    f"next_tiny={bool(b.get('tiny_restock'))} "
                    f"next_valid={bool(b.get('valid_lifetime'))} "
                    f"next_restock={_fmt_ts(b.get('restock_time'))}"
                )

        print()
        start = anchor - int(hours * 3600)
        end = anchor + int(hours * 3600)
        nearby = [r for r in raw if start <= int(r[0]) <= end]
        print(
            f"RAW STOCK ROWS ±{hours:g}h ({len(nearby)} rows; showing up to {raw_limit}):"
        )
        if len(nearby) > raw_limit:
            # Keep rows closest to anchor while preserving chronological order.
            nearby = sorted(
                sorted(nearby, key=lambda r: abs(int(r[0]) - anchor))[:raw_limit],
                key=lambda r: int(r[0]),
            )
            print("  [trimmed to rows closest to anchor]")
        for ts, qty, source in nearby:
            marker = ">>" if int(ts) == anchor else "  "
            print(
                f"{marker} {_fmt_ts(ts)} ts={int(ts)} qty={qty} source={source}"
            )

        nearby_suppressed = [
            x for x in suppressed
            if start <= int(x.get("timestamp", -1)) <= end
        ]
        print()
        print(f"SUPPRESSED PROVIDER BOUNCES IN WINDOW: {len(nearby_suppressed)}")
        for x in nearby_suppressed:
            print(f"  {x}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Inspect suspicious frozen-projection anchors against raw stock history."
    )
    parser.add_argument("country")
    parser.add_argument("item_name")
    parser.add_argument("anchors", nargs="+", type=int)
    parser.add_argument("--hours", type=float, default=10.0)
    parser.add_argument("--raw-limit", type=int, default=120)
    args = parser.parse_args()
    diagnose(
        args.country,
        args.item_name,
        args.anchors,
        hours=max(1.0, args.hours),
        raw_limit=max(20, args.raw_limit),
    )


if __name__ == "__main__":
    main()
