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
    total_fine60 = total("fine60_proposals")
    total_paired = total("paired_proposals")
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
    h60,m60,p60,u60=(
        total("fine60_proxy_hit"),total("fine60_proxy_miss"),
        total("fine60_proxy_pending"),total("fine60_proxy_unknown"))
    h_pair,m_pair,p_pair,u_pair=(
        total("paired_proxy_hit"),total("paired_proxy_miss"),
        total("paired_proxy_pending"),total("paired_proxy_unknown"))
    if (h_pair+m_pair+p_pair+u_pair != total_paired or
        h60+m60+p60+u60 != total_fine60 or
        h151+m151+pending151+u151 != total_v151 or
        h148+m148+pending148+u148 != total_v148 or
        h145+m145 > total_v145 or
        total_v148>source["cohorts"] or total_v151>source["cohorts"]
        or total_fine60>source["cohorts"]
        or total_paired>source["cohorts"]
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
    next_count=total("next_restock_scored")
    next_abs_total=total("next_restock_abs_error_total_seconds")
    next_mae=f"{next_abs_total/next_count/60:.1f} min" if next_count else "not scorable"
    recency_summary={}
    for name in ("recent_3","recent_5","recent_10","all_bounded"):
        prefix="recent_"+name
        n=total(prefix+"_paired")
        w=total(prefix+"_beats_v151")
        l=total("v151_beats_"+prefix)
        ties=total(prefix+"_ties")
        aerr=total(prefix+"_abs_total_seconds")
        nscored=total(prefix+"_scored")
        if w+l+ties != n or n>nscored:
            raise ValueError("unbalanced recency paired comparison")
        mae=f"{aerr/nscored/60:.1f}m" if nscored else "N/A"
        recency_summary[name]=(n,w,l,ties,mae)
    lines=[
        "=== V149 COMPACT V146 REPLAY (HISTORICAL AS-OF / NOT LIVE FLIGHT PROOF) ===",
        f"24 items; {source['cohorts']} first-issued item/UTC-hour cohorts; NO DATABASE OR WEBSITE WRITES",
        f"V145 recovered NEW eligibility on {source['recovered_eligible']} cohorts; "
        f"{source['mc_capped_eligible']} eligible (old or new) were unscored due to CPU cap;",
        f"V128 original proposals: {total_v128}/{source['cohorts']} ({100*total_v128/source['cohorts']:.1f}%)",
        f"V145 MC capped: {total_v145}/{source['cohorts']} proposals, "
        f"{_rate(h145,m145)} known; {pn145} pending",
        f"V148 explicit-stock-window proposals: {total_v148}/{source['cohorts']} "
        f"({100*total_v148/source['cohorts']:.1f}%); V148 proxy outcomes: "
        f"{_rate(h148,m148)}, {pending148} pending, {u148} unknown",
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
        f"  V151 1min timing code vs 5min: {total_fine60} proposals vs {total_v151}; "
        f"{total('fine60_earlier_than_coarse')} earlier, "
        f"{total('fine60_new_from_coarse_abstention')} recovered; "
        f"{total('fine60_vs_coarse_matched')} exact matched, net "
        f"{total('fine60_only_vs_coarse')-total('coarse_only_vs_fine60'):+d} "
        f"({total('fine60_only_vs_coarse')} finer-only vs "
        f"{total('coarse_only_vs_fine60')} coarse-only); "
        f"finer mature proxy {_rate(h60,m60)}",
        f"  V151 complete LOW-HIGH paired cycles: {total_paired}/{source['cohorts']} "
        f"proposals, mature {_rate(h_pair,m_pair)}, {p_pair} pending/{u_pair} unknown; "
        f"vs independent {total('paired_vs_independent_matched')} paired, net "
        f"{total('paired_only_vs_independent')-total('independent_only_vs_paired'):+d} "
        f"({total('paired_only_vs_independent')} paired-only vs "
        f"{total('independent_only_vs_paired')} independent-only); "
        f"vs NOW {total('paired_vs_leave_now_matched')} pairs net "
        f"{total('paired_only_vs_leave_now')-total('leave_now_only_vs_paired'):+d}",
        f"  V151 next completed-restock forecast: {next_count} matched fully bounded starts, "
        f"MAE {next_mae}, within 1/5/15 min "
        f"{total('next_restock_within_1m')}/{total('next_restock_within_5m')}/"
        f"{total('next_restock_within_15m')}",
        "  V153 completed-history recency vs V151 next-restock errors (same event): "
        + "; ".join(
            f"{name} {v[0]} paired, {v[1]} better/{v[2]} worse/{v[3]} tied, MAE {v[4]}"
            for name,v in recency_summary.items()),
        f"  V148 matched versus leave-now: {matched148} mature pairs, net "
        f"{pair148:+d} model-only minus leave-now-only ({total('explicit_only_vs_now')} vs {total('now_only_vs_explicit')})",
        "  Japan Xanax V151 no-departure diagnoses: "
        f"{_num(items['jap:Xanax'],'stable_peak_under_60pct_scenario_gate')} peak support below .60; "
        f"{_num(items['jap:Xanax'],'stable_single_supported_bin_only')} one-bin-only",
        "=== ITEM | old | recovered | V148 proposed/H/M/net | "
        "V151 proposed/H/M/net | vs V148 | 1min net | paired net | restock MAE base/recent5 | wait min ===",
    ]
    focus=["jap:Xanax","chi:Peony","swi:Edelweiss","uni:Xanax"]
    ordered=sorted(items,key=lambda k:(0 if k in focus else 1,focus.index(k) if k in focus else k))
    for name in ordered:
        it=items[name]
        wait=it.get("stable_departure_median_wait_seconds")
        if wait is not None and (
            not isinstance(wait,(int,float)) or wait<0):
            raise ValueError("invalid wait value")
        next_abs_mean=it.get('next_restock_mean_abs_error_seconds')
        recent5_n=_num(it,"recent_recent_5_scored")
        recent5_avg=(
            _num(it,"recent_recent_5_abs_total_seconds")/recent5_n/60
            if recent5_n else None)
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
            f"{_num(it,'fine60_only_vs_coarse')-_num(it,'coarse_only_vs_fine60'):+3} "
            f"{_num(it,'paired_only_vs_independent')-_num(it,'independent_only_vs_paired'):+3} "
            f"{'N/A' if next_abs_mean is None else f'{next_abs_mean/60:.1f}'}"
            f"/{'N/A' if recent5_avg is None else format(recent5_avg,'.1f')} "
            f"{'N/A' if wait is None else f'{wait/60:.1f}'}"
        )
    lines.extend([
        "Caution: first-UTC-hour cohorts share restock cycles; these are not independent trips.",
        "V148/V151 proxy rates condition on mature scored proposals; "
        "V145 was capped at 4 model evaluations per item.",
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
