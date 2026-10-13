"""V156: strictly as-issued item-specific cycle profile and provisional router.

A plant with long, irregular stocked periods is not a short-lived plushie.
The router examines only completed HIGH/LOW phases available when an issue
was recorded; it NEVER observes the later success outcome to pick a model.

Predeclared hypothesis: correlated adjacent LOW->HIGH durations may benefit
from V151's paired-cycle bootstrap. Use it ONLY with >=8 validated pairs,
nondegenerate HIGH/LOW variability, rank-correlation magnitude >=.65 and
same-direction correlations in both chronological halves. Otherwise retain
the already measured independent V151. This is a research hypothesis, not
a fitted item leaderboard, calibrated confidence or a production selector.
"""
from __future__ import annotations

import statistics

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v151_stable_earliest_departure import _paired_complete_cycles

MIN_PAIRS_TO_ROUTE=8
MIN_ABS_RANK_CORRELATION=0.65
SHORT_STOCK_SECONDS=300


def _median(values):
    return int(statistics.median(values)) if values else None


def _ranks(values):
    ordered=sorted(enumerate(values), key=lambda pair: pair[1])
    ranks=[None]*len(values)
    start=0
    while start<len(ordered):
        end=start+1
        while end<len(ordered) and ordered[end][1]==ordered[start][1]:
            end+=1
        average=(start+end+1)/2.0
        for i in range(start,end):
            ranks[ordered[i][0]]=average
        start=end
    return ranks


def _spearman(a,b):
    if len(a)!=len(b) or len(a)<3:
        return None
    ra,rb=_ranks(a),_ranks(b)
    ma,mb=statistics.mean(ra),statistics.mean(rb)
    va=sum((x-ma)**2 for x in ra)
    vb=sum((y-mb)**2 for y in rb)
    if va==0 or vb==0:
        return None
    return sum((x-ma)*(y-mb) for x,y in zip(ra,rb))/(va*vb)**0.5


def item_cycle_profile(item_key, phases, *, asof):
    """Classify stock longevity, gap, route and predeclared model choice.

    The caller MUST supply V145 periods from observations <= asof. Paired
    windows are separately validated for future epochs by V151's helper.
    """
    if (not isinstance(item_key,str) or item_key.count(":")!=1
        or type(asof) is not int or asof<=0
        or not isinstance(phases,dict)):
        raise ValueError("invalid item-cycle profile")
    country,name=item_key.split(":",1)
    if country not in TRAVEL_SECONDS or not name:
        raise ValueError("unsupported country or item")
    high=phases.get("stocked_durations")
    low=phases.get("depleted_durations")
    if (not isinstance(high,list) or not isinstance(low,list)
        or any(type(x) is not int or x<=0 for x in high+low)):
        raise ValueError("unverified phase duration list")
    last=phases.get("last_observation")
    if last is not None and (type(last.epoch) is not int
                              or last.epoch>asof):
        raise ValueError("phase profile looks into future")
    pairs=_paired_complete_cycles(phases,asof)
    stocked=_median(high)
    depleted=_median(low)
    cycle=(stocked+depleted if stocked is not None
           and depleted is not None else None)
    flight=TRAVEL_SECONDS[country]
    stock_type=(
        "UNOBSERVED" if stocked is None
        else "SHORT_LT_5MIN" if stocked<SHORT_STOCK_SECONDS
        else "MEDIUM_5_TO_20MIN" if stocked<1200
        else "LONG_20MIN_PLUS"
    )
    low_type=(
        "UNOBSERVED" if depleted is None
        else "FREQUENT_LT_30MIN" if depleted<1800
        else "INTERMEDIATE_30_TO_90MIN" if depleted<5400
        else "INFREQUENT_90MIN_PLUS"
    )
    rho=None
    half_a=half_b=None
    low_pairs=[x for x,_ in pairs]
    high_pairs=[y for _,y in pairs]
    if len(pairs)>=MIN_PAIRS_TO_ROUTE:
        rho=_spearman(low_pairs,high_pairs)
        cut=len(pairs)//2
        half_a=_spearman(low_pairs[:cut],high_pairs[:cut])
        half_b=_spearman(low_pairs[cut:],high_pairs[cut:])
    stable_sign=(rho is not None and
                 half_a is not None and half_b is not None and
                 abs(rho)>=MIN_ABS_RANK_CORRELATION and
                 rho*half_a>0 and rho*half_b>0)
    paired_allowed=(len(pairs)>=MIN_PAIRS_TO_ROUTE and stable_sign)
    routing="paired_complete" if paired_allowed else "independent"
    if len(pairs)<MIN_PAIRS_TO_ROUTE:
        reason="SPARSE_DIRECTLY_MATCHED_EPISODES"
    elif rho is None or half_a is None or half_b is None:
        reason="NO_IDENTIFIABLE_DEPENDENCE"
    elif not paired_allowed:
        reason="INSUFFICIENT_STABLE_PAIR_DEPENDENCE"
    else:
        reason="PREDECLARED_STABLE_PAIR_DEPENDENCE"
    return {
        "item_key":item_key,
        "issued_epoch":asof,
        "flight_seconds":flight,
        "stocked_median_seconds":stocked,
        "depleted_median_seconds":depleted,
        "completed_stocked_periods":len(high),
        "completed_depleted_periods":len(low),
        "direct_completed_low_to_high_pairs":len(pairs),
        "stock_duration_regime":stock_type,
        "depletion_duration_regime":low_type,
        "flight_over_median_cycle":(
            round(flight/cycle,3) if cycle is not None else None),
        "flight_over_median_stocked_lifetime":(
            round(flight/stocked,3) if stocked is not None else None),
        "paired_low_high_rank_correlation":(
            round(rho,4) if rho is not None else None),
        "paired_dependence_first_half":(
            round(half_a,4) if half_a is not None else None),
        "paired_dependence_second_half":(
            round(half_b,4) if half_b is not None else None),
        "predeclared_research_route":routing,
        "selection_reason":reason,
        "threshold_based_on_known_phases_only":True,
        "outcome_free_selection":True,
        "model_is_provisional":True,
        "stock_at_arrival_confirmed":False,
        "success_probability_calibrated":False,
    }


def route_issued_prediction(profile, independent, paired):
    """No new simulation: select from already as-of forecasts or abstain.

    This must be run BEFORE evaluating future outcomes. If a correlated
    paired model abstains, use the independent research fallback rather
    than silently promoting a below-.60 flight.
    """
    if any(not isinstance(o,dict) for o in (profile,independent,paired)):
        raise ValueError("invalid routed forecasts")
    item=profile.get("item_key")
    issue=profile.get("issued_epoch")
    if (not isinstance(item,str) or type(issue) is not int or
        any(o.get("item_key")!=item or o.get("issued_epoch")!=issue
            for o in (independent,paired))):
        raise ValueError("mixed item/issue forecasts")
    choice=profile.get("predeclared_research_route")
    if choice not in ("independent","paired_complete"):
        raise ValueError("invalid frozen item selection")
    chosen=independent
    fallback=False
    if choice=="paired_complete":
        if paired.get("first_reachable") is not None:
            chosen=paired
        else:
            fallback=True
    decision=chosen.get("first_reachable")
    return {
        "item_key":item,"issued_epoch":issue,
        "profile_route":choice,
        "actual_model_used":chosen.get("cycle_sampling","independent"),
        "paired_fell_back_to_independent":fallback,
        "departure_epoch":(
            decision["departure_epoch"] if decision else None),
        "arrival_epoch":(
            decision["arrival_epoch"] if decision else None),
        "wait_seconds":(
            decision["wait_seconds"] if decision else None),
        "predeclared_asof_research_only":True,
        "outcome_optimized_posthoc":False,
        "recommendation_production_ready":False,
    }
