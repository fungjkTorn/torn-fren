"""V149: <45-line summary for V146 V128/V145/V148 same-issued replay.

Use this for read-only VM operator output instead of dumping ~1,000 lines of
per-item JSON. Does not alter sources, compute models, read databases, or
misrepresent unmatched samples as a head-to-head success rate.
"""
from __future__ import annotations


def _num(d, key):
    value = d.get(key, 0)
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {key}")
    return value


def _rate(hit, miss):
    return f"{hit}/{hit + miss}={100 * hit / (hit + miss):.1f}%" if hit + miss else "no mature known"


def compact(result):
    if result.get("status") != "READ_ONLY_ASOF_REPLAY_NOT_PROSPECTIVE_CERTIFICATION":
        raise ValueError("not a complete protected V146 replay")
    if result.get("exact_item_roster") != 24 or result.get("no_writes") is not True:
        raise ValueError("roster or read-only proof missing")
    items = result.get("items")
    if type(items) is not dict or len(items) != 24:
        raise ValueError("missing item histories")
    counts = result.get("summary", {})
    if not isinstance(counts, dict):
        raise ValueError("missing summary counts")
    source = {
        "cohorts": _num(result, "hourly_issued_cohorts"),
        "mc_actual_evaluations": _num(result, "monte_carlo_replayed"),
        "mc_capped_recovery": _num(counts, "NEW_ELIGIBLE_BUT_RESOURCE_LIMIT"),
        "recovered_eligible": _num(counts, "recovered"),
        "insufficient_or_no_onset": _num(
            counts, "OBSERVED_HISTORY_SPARSE_OR_ONSET_UNKNOWN"),
    }
    if sum(_num(it, "issued_hourly_samples") for it in items.values()) != source["cohorts"]:
        raise ValueError("issued item-hour totals do not balance")
    if source["mc_actual_evaluations"] > _num(result, "replay_cap"):
        raise ValueError("replay counted more model evaluations than budget")
    def total(key):
        return sum(_num(it, key) for it in items.values())
    total_v128 = total("original_proposals")
    total_v145 = total("new_proposals")
    total_v148 = total("explicit_proposals")
    h145, m145, pn145, unk145 = (
        total("HIT"),total("MISS"),total("PENDING"),
        sum(total(key) for key in (
            "unknown_or_no_proposal",))
    )
    h148,m148,p148,u148 = (
        total("explicit_proxy_hit"),total("explicit_proxy_miss"),
        total("explicit_proxy_pending"),total("explicit_proxy_unknown"))
    if (h148+m148+p148+u148 != total_v148 or
        h145+m145 > total_v145 or
        total_v148>source["cohorts"] or total_v128>source["cohorts"]
        or total_v145>source["mc_actual_evaluations"]):
        raise ValueError("model outcome denominators do not reconcile")
    p145=total("matched_new_vs_now")
    p148=total("matched_explicit_vs_now")
    pair145=total("new_only")-total("now_only")
    pair148=total("explicit_only_vs_now")-total("now_only_vs_explicit")
    lines=[
        "=== V149 COMPACT V146 REPLAY (HISTORICAL AS-OF / NOT LIVE FLIGHT PROOF) ===",
        f"24 items; {source['cohorts']} first-issued item/UTC-hour cohorts; NO DATABASE OR WEBSITE WRITES",
        f"V145 recovered NEW eligibility on {source['recovered_eligible']} cohorts; "
        f"{source['mc_capped_recovery']} newly eligible were unscored due to CPU cap;",
        f"  V145 simulations run: {source['mc_actual_evaluations']} (max {_num(result, 'replay_cap')}); "
        f"{source['insufficient_or_no_onset']} remain sparse/onset-unknown",
        f"V128 original proposals: {total_v128}/{source['cohorts']} ({100*total_v128/source['cohorts']:.1f}%)",
        f"V145 corrected Monte Carlo proposals: {total_v145}/{source['cohorts']} "
        f"(budget-limited; NOT total potential coverage)",
        f"  proxy results among V145 proposals: {_rate(h145,m145)}; "
        f"{pn145} pending, remaining unknown/unmatched",
        f"V148 explicit-stock-window proposals: {total_v148}/{source['cohorts']} "
        f"({100*total_v148/source['cohorts']:.1f}%)",
        f"  V148 proxy outcomes: {_rate(h148,m148)}; {p148} pending, {u148} unknown",
        f"  V145 matched versus leave-now: {p145} mature pairs, net "
        f"{pair145:+d} model-only minus leave-now-only ({total('new_only')} vs {total('now_only')})",
        f"  V148 matched versus leave-now: {p148} mature pairs, net "
        f"{pair148:+d} model-only minus leave-now-only ({total('explicit_only_vs_now')} vs {total('now_only_vs_explicit')})",
        f"  V148 long-wait caution flags: {total('long_wait_needs_explanation')}; "
        "0 flags is NOT a guarantee of optimal timing",
        "=== ITEM | old proposals | v145 MC | recovered eligible | "
        "v148 proposals | v148 HIT/MISS/PEND/UNKNOWN | net vs now | wait median min ===",
    ]
    focus=["jap:Xanax","chi:Peony","swi:Edelweiss","uni:Xanax"]
    ordered=sorted(items,key=lambda k:(0 if k in focus else 1,focus.index(k) if k in focus else k))
    for name in ordered:
        it=items[name]
        wait=it.get("explicit_departure_median_wait_seconds")
        if wait is not None and (
            not isinstance(wait,(int,float)) or wait<0):
            raise ValueError("invalid wait value")
        lines.append(
            f"{name:24} {_num(it,'original_proposals'):>3} "
            f"{_num(it,'new_proposals'):>3} {_num(it,'recovered'):>3} "
            f"{_num(it,'explicit_proposals'):>3} "
            f"{_num(it,'explicit_proxy_hit'):>2}/"
            f"{_num(it,'explicit_proxy_miss'):>2}/"
            f"{_num(it,'explicit_proxy_pending'):>2}/"
            f"{_num(it,'explicit_proxy_unknown'):>2}  "
            f"{_num(it,'explicit_only_vs_now')-_num(it,'now_only_vs_explicit'):+3} "
            f"{'—' if wait is None else f'{wait/60:.1f}'}"
        )
    lines.extend([
        "Caution: first-UTC-hour cohorts share restock cycles; these are not independent trips.",
        "V148 proxy rate is conditional on mature scorable proposals; "
        "V145 was capped at 4 model evaluations per item.",
        "Japan Xanax: separately inspect explicit NO_CONSERVATIVE_REACHABLE_WINDOW "
        "vs actual recorded restocks.",
        "Original V2 graph and deployed 24-item website are unchanged.",
    ])
    return "\n".join(lines)


def main():
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json",type=Path)
    args=parser.parse_args()
    print(compact(json.loads(args.input_json.read_text())))


if __name__=="__main__":
    main()
