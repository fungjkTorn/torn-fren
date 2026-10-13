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
    total_routed = total("routed_proposals")
    total_prequential = total("prequential_proposals")
    total_flight = total("flight_horizon_proposals")
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
    rh,rm,rp,ru=(
        total("routed_proxy_hit"),total("routed_proxy_miss"),
        total("routed_proxy_pending"),total("routed_proxy_unknown"))
    qh,qm,qp,qu=(
        total("prequential_proxy_hit"),total("prequential_proxy_miss"),
        total("prequential_proxy_pending"),total("prequential_proxy_unknown"))
    fh,fm,fp,fu=(
        total("flight_horizon_proxy_hit"),total("flight_horizon_proxy_miss"),
        total("flight_horizon_proxy_pending"),total("flight_horizon_proxy_unknown"))
    if (fh+fm+fp+fu != total_flight or
        total("flight_horizon_selected_paired")+
        total("flight_horizon_selected_independent") != total_flight or
        qh+qm+qp+qu != total_prequential or
        total("prequential_paired_selected")+total("prequential_independent_selected") != total_prequential or
        rh+rm+rp+ru != total_routed or
        total("routed_selected_paired")+total("routed_selected_independent") != total_routed or
        h_pair+m_pair+p_pair+u_pair != total_paired or
        h60+m60+p60+u60 != total_fine60 or
        h151+m151+pending151+u151 != total_v151 or
        h148+m148+pending148+u148 != total_v148 or
        h145+m145 > total_v145 or
        total_v148>source["cohorts"] or total_v151>source["cohorts"]
        or total_fine60>source["cohorts"]
        or total_paired>source["cohorts"]
        or total_routed>source["cohorts"]
        or total_prequential>source["cohorts"]
        or total_flight>source["cohorts"]
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
    heldout_reasons={
        "sparse":total("prequential_reason:INSUFFICIENT_DIRECTLY_BOUNDED_PAIRS"),
        "constant":total("prequential_reason:NONIDENTIFIABLE_CONSTANT_PHASE_DURATION"),
        "not_better":total("prequential_reason:PAIRED_NOT_PROVEN_BETTER_PREQUENTIALLY"),
        "better":total("prequential_reason:PREQUENTIAL_FIRST_CYCLE_SURVIVAL_IMPROVEMENT"),
    }
    next_count=total("next_restock_scored")
    next_abs_total=total("next_restock_abs_error_total_seconds")
    next_mae=f"{next_abs_total/next_count/60:.1f} min" if next_count else "not scorable"
    paired_n=total("paired_restock_scored")
    paired_mae=(
        f"{total('paired_restock_abs_sum_seconds')/paired_n/60:.1f}m"
        if paired_n else "N/A")
    paired_timing_matched=total("paired_restock_mature_comparisons")
    paired_better=total("paired_restock_better")
    paired_worse=total("paired_restock_worse")
    paired_ties=total("paired_restock_tie")
    if paired_better+paired_worse+paired_ties!=paired_timing_matched:
        raise ValueError("unbalanced paired first-restock comparison")
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
        f"V128 original {total_v128}/{source['cohorts']} proposals; "
        f"V145 MC capped {total_v145}/{source['cohorts']} proposals, "
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

        f"  V151 complete LOW-HIGH paired cycles: {total_paired}/{source['cohorts']} "
        f"proposals, mature {_rate(h_pair,m_pair)}, {p_pair} pending/{u_pair} unknown; "
        f"vs independent {total('paired_vs_independent_matched')} paired, net "
        f"{total('paired_only_vs_independent')-total('independent_only_vs_paired'):+d} "
        f"({total('paired_only_vs_independent')} paired-only vs "
        f"{total('independent_only_vs_paired')} independent-only); "
        f"vs NOW {total('paired_vs_leave_now_matched')} pairs net "
        f"{total('paired_only_vs_leave_now')-total('leave_now_only_vs_paired'):+d}; "
        f"paired restock MAE {paired_mae} (n={paired_n}), "
        f"timing head-to-head {paired_better} better/{paired_worse} worse/{paired_ties} ties",
        f"  V156 per-item AS-ISSUED routing: {total_routed} proposals, "
        f"{total('routed_selected_paired')} paired vs "
        f"{total('routed_selected_independent')} independent; mature "
        f"{_rate(rh,rm)}; matched vs independent "
        f"{total('routed_vs_independent_matched')} cases net "
        f"{total('routed_only_vs_independent')-total('independent_only_vs_routed'):+d} "
        f"({total('routed_only_vs_independent')} routed-only/"
        f"{total('independent_only_vs_routed')} independent-only); "
        f"vs NOW {total('routed_vs_leave_now_matched')} pairs net "
        f"{total('routed_only_vs_now')-total('now_only_vs_routed'):+d}",
        f"  V157 PREQUENTIAL first-cycle selector: {total_prequential} proposals, "
        f"{total('prequential_paired_selected')} paired/ "
        f"{total('prequential_independent_selected')} independent; "
        f"mature {_rate(qh,qm)}, vs independent "
        f"{total('prequential_vs_independent_matched')} matched net "
        f"{total('prequential_only_vs_independent')-total('independent_only_vs_prequential'):+d} "
        f"({total('prequential_only_vs_independent')} exclusive wins vs "
        f"{total('independent_only_vs_prequential')} losses), vs NOW "
        f"{total('prequential_vs_now_matched')} matched net "
        f"{total('prequential_only_vs_now')-total('now_only_vs_prequential'):+d}; "
        f"routing reasons sparse/constant/no-lift/paired: "
        f"{heldout_reasons['sparse']}/{heldout_reasons['constant']}/"
        f"{heldout_reasons['not_better']}/{heldout_reasons['better']}",
        f"  V158 ACTUAL FLIGHT HORIZON selector: {total_flight} proposals; "
        f"{total('flight_horizon_selected_paired')} paired/"
        f"{total('flight_horizon_selected_independent')} independent; "
        f"mature {_rate(fh,fm)}; vs independent "
        f"{total('flight_horizon_vs_independent_matched')} matched net "
        f"{total('flight_horizon_only_vs_independent')-total('independent_only_vs_flight_horizon'):+d} "
        f"({total('flight_horizon_only_vs_independent')} exclusive wins vs "
        f"{total('independent_only_vs_flight_horizon')} losses), "
        f"vs NOW {total('flight_horizon_vs_now_matched')} mature net "
        f"{total('flight_horizon_only_vs_now')-total('now_only_vs_flight_horizon'):+d}",
        f"  V151 next completed-restock forecast: {next_count} matched fully bounded starts, "
        f"MAE {next_mae}, within 1/5/15 min "
        f"{total('next_restock_within_1m')}/{total('next_restock_within_5m')}/"
        f"{total('next_restock_within_15m')}",

        f"  V148 matched versus leave-now: {matched148} mature pairs, net "
        f"{pair148:+d} model-only minus leave-now-only ({total('explicit_only_vs_now')} vs {total('now_only_vs_explicit')})",
        "  Japan Xanax V151 no-departure diagnoses: "
        f"{_num(items['jap:Xanax'],'stable_peak_under_60pct_scenario_gate')} peak support below .60; "
        f"{_num(items['jap:Xanax'],'stable_single_supported_bin_only')} one-bin-only",
        "=== ITEM | old | recovered | V148 proposed/H/M/net | "
        "V151 proposed/H/M/net | vs V148 | paired props/net | V156 picks/net | V157 picks/net | V158 picks/net | stock/low min | wait min ===",
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
        high_n=_num(it,"profile_high_seconds_n")
        low_n=_num(it,"profile_low_seconds_n")
        stock_mean=(_num(it,"profile_high_seconds_sum")/high_n/60
                    if high_n else None)
        low_mean=(_num(it,"profile_low_seconds_sum")/low_n/60
                  if low_n else None)
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
            f"{_num(it,'paired_proposals'):>2}/"
            f"{_num(it,'paired_only_vs_independent')-_num(it,'independent_only_vs_paired'):+3} "
            f"{_num(it,'routed_selected_paired'):>2}/"
            f"{_num(it,'routed_only_vs_independent')-_num(it,'independent_only_vs_routed'):+3} "
            f"{_num(it,'prequential_paired_selected'):>2}/"
            f"{_num(it,'prequential_only_vs_independent')-_num(it,'independent_only_vs_prequential'):+3} "
            f"{_num(it,'flight_horizon_selected_paired'):>2}/"
            f"{_num(it,'flight_horizon_only_vs_independent')-_num(it,'independent_only_vs_flight_horizon'):+3} "
            f"{'N/A' if stock_mean is None else format(stock_mean,'.1f')}/"
            f"{'N/A' if low_mean is None else format(low_mean,'.1f')} "
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
