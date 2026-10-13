"""V149: <45-line summary for V146 V128/V145/V148/V151 same-issued replay.

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
        "mc_capped_eligible": _num(counts, "NEW_ELIGIBLE_BUT_RESOURCE_LIMIT"),
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
    total_v151 = total("stable_proposals")
    h145, m145, pn145, unk145 = (
        total("HIT"),total("MISS"),total("PENDING"),
        sum(total(key) for key in (
            "unknown_or_no_proposal",))
    )
    h148,m148,pending148,u148 = (
        total("explicit_proxy_hit"),total("explicit_proxy_miss"),
        total("explicit_proxy_pending"),total("explicit_proxy_unknown"))
    h151,m151,pending151,u151 = (
        total("stable_proxy_hit"),total("stable_proxy_miss"),
        total("stable_proxy_pending"),total("stable_proxy_unknown"))
    if (h151+m151+pending151+u151 != total_v151 or
        h148+m148+pending148+u148 != total_v148 or
        h145+m145 > total_v145 or
        total_v148>source["cohorts"] or total_v151>source["cohorts"]
        or total_v128>source["cohorts"]
        or total_v145>source["mc_actual_evaluations"]):
        raise ValueError("model outcome denominators do not reconcile")
    matched145=total("matched_new_vs_now")
    matched148=total("matched_explicit_vs_now")
    matched151=total("matched_stable_vs_now")
    pair145=total("new_only")-total("now_only")
    pair148=total("explicit_only_vs_now")-total("now_only_vs_explicit")
    pair151=total("stable_only_vs_now")-total("now_only_vs_stable")
    paired151148=total("matched_stable_vs_explicit")
    wins151148=total("stable_only_vs_explicit")
    wins148151=total("explicit_only_vs_stable")
    delayed151=total("matched_stable_delayed_vs_now")
    delayed_wins151=total("delayed_stable_only_vs_now")
    delayed_now_wins=total("delayed_now_only_vs_stable")
    lines=[
        "=== V149 COMPACT V146 REPLAY (HISTORICAL AS-OF / NOT LIVE FLIGHT PROOF) ===",
        f"24 items; {source['cohorts']} first-issued item/UTC-hour cohorts; NO DATABASE OR WEBSITE WRITES",
        f"V145 recovered NEW eligibility on {source['recovered_eligible']} cohorts; "
        f"{source['mc_capped_eligible']} eligible (old or new) were unscored due to CPU cap;",
        f"  V145 simulations run: {source['mc_actual_evaluations']} (max {_num(result, 'replay_cap')}); "
        f"{source['insufficient_or_no_onset']} remain sparse/onset-unknown",
        f"V128 original proposals: {total_v128}/{source['cohorts']} ({100*total_v128/source['cohorts']:.1f}%)",
        f"V145 corrected Monte Carlo proposals: {total_v145}/{source['cohorts']} "
        f"(budget-limited; NOT total potential coverage)",
        f"  proxy results among V145 proposals: {_rate(h145,m145)}; "
        f"{pn145} pending, remaining unknown/unmatched",
        f"V148 explicit-stock-window proposals: {total_v148}/{source['cohorts']} "
        f"({100*total_v148/source['cohorts']:.1f}%)",
        f"  V148 proxy outcomes: {_rate(h148,m148)}; {pending148} pending, {u148} unknown",
        f"V151 stable whole-cycle scenario departures: {total_v151}/{source['cohorts']}"
        f" ({100*total_v151/source['cohorts']:.1f}%)",
        f"  V151 proxy outcomes: {_rate(h151,m151)}; {pending151} pending, {u151} unknown",
        f"  V151 matched vs leave-now: {matched151} pairs, net {pair151:+d}"
        f" ({total('stable_only_vs_now')} V151-only vs {total('now_only_vs_stable')} now-only)",
        f"  V151 vs V148 identical issue: {paired151148} mature pairs, net "
        f"{wins151148-wins148151:+d} (V151-only {wins151148}, V148-only {wins148151})",
        f"  V151 chooses: {total('stable_depart_now_proposals')} NOW, "
        f"{total('stable_depart_future_proposals')} FUTURE; among {delayed151} mature delayed pairs "
        f"{delayed_wins151} V151-only vs {delayed_now_wins} leave-now-only",
        f"  V145 matched versus leave-now: {matched145} mature pairs, net "
        f"{pair145:+d} model-only minus leave-now-only ({total('new_only')} vs {total('now_only')})",
        f"  V148 matched versus leave-now: {matched148} mature pairs, net "
        f"{pair148:+d} model-only minus leave-now-only ({total('explicit_only_vs_now')} vs {total('now_only_vs_explicit')})",
        "=== ITEM | old | recovered | V148 proposed/H/M/net | "
        "V151 proposed/H/M/net | V151-V148 paired net | V151 median wait min ===",
    ]
    focus=["jap:Xanax","chi:Peony","swi:Edelweiss","uni:Xanax"]
    ordered=sorted(items,key=lambda k:(0 if k in focus else 1,focus.index(k) if k in focus else k))
    for name in ordered:
        it=items[name]
        wait=it.get("stable_departure_median_wait_seconds")
        if wait is not None and (
            not isinstance(wait,(int,float)) or wait<0):
            raise ValueError("invalid wait value")
        lines.append(
            f"{name:24} {_num(it,'original_proposals'):>2} "
            f"{_num(it,'recovered'):>2} "
            f"{_num(it,'explicit_proposals'):>2}/"
            f"{_num(it,'explicit_proxy_hit'):>2}/"
            f"{_num(it,'explicit_proxy_miss'):>2}/"
            f"{_num(it,'explicit_only_vs_now')-_num(it,'now_only_vs_explicit'):+3} "
            f"{_num(it,'stable_proposals'):>2}/"
            f"{_num(it,'stable_proxy_hit'):>2}/"
            f"{_num(it,'stable_proxy_miss'):>2}/"
            f"{_num(it,'stable_only_vs_now')-_num(it,'now_only_vs_stable'):+3} "
            f"{_num(it,'stable_only_vs_explicit')-_num(it,'explicit_only_vs_stable'):+3} "
            f"{'—' if wait is None else f'{wait/60:.1f}'}"
        )
    lines.extend([
        "Caution: first-UTC-hour cohorts share restock cycles; these are not independent trips.",
        "V148/V151 proxy rates condition on mature scored proposals; "
        "V145 was capped at 4 model evaluations per item.",
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
