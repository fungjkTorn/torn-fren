"""V130: isolated deterministic common-random-number challenger for V128.

Historical V128 seeds 128 Monte Carlo scenarios with seed+asof%100003.
Reissuing a forecast 6 seconds later therefore redraws 128 *different*
scenarios, even if NO stock observation changed; near .60, candidate
departures jump by tens of minutes. V130 fixes the simulation seed to a
stable fingerprint of item, phase threshold-start and upstream provider
within a continuous observed phase, while changing the conditional
survival horizon naturally as asof advances.

The original V128 research data and private 5m recorder MUST remain
unchanged. This is an independent experimental V130 counterfactual
challenger, not evidence of improved arrival accuracy. Identical scenario
trajectories across close times only demonstrate lower sampling noise,
NOT better calibration or real-world stock freshness.
"""
from __future__ import annotations

import hashlib

from research.v128_full24_earliest_shadow import (
    empirical_arrival_scores,fast_phases,item_record,earliest_credible_for_country,
    MAX_ITEM_ROWS
)
from research.plushie_champions.common import TRAVEL_SECONDS,MAX_WAIT,STEP

POLICY="v130_phase_pinned_common_random_128_v1"
DOMAIN="torn-fren/v130/phase-pinned/common-random/128"


def phase_pinned_seed(history,item_key):
    last=history.get("last_observation")
    onset=history.get("phase_onset")
    phase=history.get("phase")
    if (last is None or onset is None or phase not in ("LOW","HIGH")
        or item_key.split(":",1)[0] not in TRAVEL_SECONDS):
        return None
    # A provider switch / unproven start triggers V128 abstention, not
    # an invented restock. Reuse seed while the *observed phase* is stable.
    fields=(DOMAIN,item_key,str(onset),phase,str(last.source))
    digest=hashlib.sha256("\x1f".join(fields).encode("utf-8")).digest()
    return int.from_bytes(digest[:8],"big")


def model(history,item_key,*,asof,scenarios=128):
    pin=phase_pinned_seed(history,item_key)
    if pin is None:
        return empirical_arrival_scores(
            history,item_key,asof=asof,scenarios=scenarios)
    # V128 adds asof%100003 to its input seed. Subtract it so each issued
    # query in the same confirmed phase uses identical scenario draws.
    return empirical_arrival_scores(
        history,item_key,asof=asof,scenarios=scenarios,
        seed=pin-asof%100003,
    )


def record(item_key,roster,observations,gaps,*,issued):
    """Produce independent challenger proposal; original v128 untouched."""
    if observations is None or len(observations)>MAX_ITEM_ROWS:
        result=item_record(
            item_key,roster,None,gaps,issued=issued)
        result["policy_id"]=POLICY
        result["model_variant"]="phase_pinned_common_random"
        result["source_status"]="SOURCE_HISTORY_TOO_LARGE"
        result["earliest_departure"]=None
        result["earliest_arrival"]=None
        result["earliest_score"]=None
        result["departure_state"]="ABSTAIN"
        result["decision_status"]="ABSTAIN_SOURCE_HISTORY_TOO_LARGE"
        return result

    history=fast_phases(observations,asof=issued,gaps=gaps)
    curve=model(history,item_key,asof=issued)
    choice=earliest_credible_for_country(curve,item_key)
    original=item_record(item_key,roster,observations,gaps,issued=issued)
    dep=choice["departure"]
    if dep is not None and not issued<=dep<=issued+MAX_WAIT:
        raise AssertionError("invalid V130 departure")
    original.update(
        policy_id=POLICY,
        model_variant="phase_pinned_common_random",
        score_at_leave_now=curve.get("earliest_immediate_arrival_score"),
        earliest_departure=dep,
        earliest_arrival=choice["arrival"],
        earliest_score=choice["score"],
        decision_status=choice["status"],
        wait_minutes=None if dep is None else (dep-issued)/60,
        departure_state=(
            "ABSTAIN" if dep is None else
            "RESEARCH_NOW" if dep==issued else
            "RESEARCH_READY_WITHIN_5M" if dep-issued<=STEP else
            "RESEARCH_FUTURE_WATCH_UNCONFIRMED"),
        completed_high=curve.get("completed_high"),
        completed_low=curve.get("completed_low"),
        scores_distinct=curve.get("scores_distinct"),
        source_status=curve["status"],
        scenario_count=curve.get("scenario_count"),
        stable_monte_carlo_source=True,
        scores_not_calibrated=True,
        no_gameplay_flight_verification=True,
        source_country_age_verified=False,
    )
    return original


def drift_comparison(observations,item_key,*,issued,seconds=6,gaps=()):
    """Identical stored input stock; simulate only time passing by seconds."""
    if not 1<=seconds<=60:
        raise ValueError("invalid fixed-history elapsed-second sensitivity")
    history_start=fast_phases(observations,asof=issued,gaps=gaps)
    history_end=fast_phases(observations,asof=issued+seconds,gaps=gaps)
    results={}
    for name,policy in (("v128",empirical_arrival_scores),("v130",model)):
        before=policy(history_start,item_key,asof=issued)
        after=policy(history_end,item_key,asof=issued+seconds)
        b=earliest_credible_for_country(before,item_key)
        a=earliest_credible_for_country(after,item_key)
        results[name]={
            "before_status":before["status"],
            "after_status":after["status"],
            "before_departure":b["departure"],
            "after_departure":a["departure"],
            "before_wait_minutes":b.get("wait_seconds",0)/60 if b["departure"] is not None else None,
            "after_wait_minutes":a.get("wait_seconds",0)/60 if a["departure"] is not None else None,
            "score_drift_max":(
                round(max(abs(x-y) for x,y in zip(
                    before["scores"],after["scores"])),6)
                if "scores" in before and "scores" in after else None),
            "decision_shift_minutes":(
                round((a["departure"]-b["departure"])/60,3)
                if a["departure"] is not None and b["departure"] is not None
                else None),
        }
    return {
        "status":"V130_FIXED_STOCK_HISTORY_SAMPLING_STABILITY_AUDIT",
        "item_key":item_key,
        "same_input_stock_history_both_queries":True,
        "no_new_stock_observed_in_test":True,
        "source_country_freshness_verified":False,
        "arrival_success_verified":False,
        "research_only":True,
        "elapsed_query_seconds":seconds,
        "comparisons":results,
    }
