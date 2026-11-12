"""V152: Event-level next restock timing verification for V151 as-of forecasts.

Research-only audit. The first NEXT fully observed HIGH (>=$30 units)
interval after issue is the target. Both its start AND end are direct
same-provider threshold crossings (V145), and benign source switching
inside the phase is allowed. Explicit collector gaps and source-state
contradictions between issue and first period make "first" unknowable.

The forecast is issued using ONLY old observations before issue; this
function receives future observations solely for post-hoc EVALUATION.
Backfills can exist, so historical as-of replay != prospective proof.
"""
from __future__ import annotations
import bisect

from research.v128_full24_earliest_shadow import MIN_QTY, _gap_index


def evaluate_next_completed_restock(observations, future_phases, *,
                                     issued, predicted_onset_epoch,
                                     asof, gaps=()):
    if type(issued) is not int or type(asof) is not int or issued>=asof:
        raise ValueError("invalid issue and outcome timestamps")
    if (predicted_onset_epoch is not None
        and (type(predicted_onset_epoch) is not int
             or predicted_onset_epoch < issued)):
        raise ValueError("invalid issue-time forecast")
    if not isinstance(future_phases,dict):
        raise ValueError("missing evaluated bounded phases")
    candidate_windows=future_phases.get("observed_bounded_stocked_windows")
    if not isinstance(candidate_windows,list):
        raise ValueError("no verified completed restock window evidence")
    starts=[x[0] for x in candidate_windows]
    if starts != sorted(starts):
        raise ValueError("unordered observed complete windows")
    future_index=bisect.bisect_right(starts,issued)
    window=(candidate_windows[future_index]
            if future_index<len(candidate_windows) else None)
    result={
        "status":"NO_VERIFIED_COMPLETE_NEXT_RESTOCK",
        "issued_epoch":issued,
        "predicted_onset_epoch":predicted_onset_epoch,
        "next_observed_complete_start_epoch":None,
        "next_observed_complete_end_epoch":None,
        "forecast_error_seconds":None,
        "absolute_forecast_error_seconds":None,
        "within_1_min":None,
        "within_5_min":None,
        "within_15_min":None,
        "source_freshness_certified":False,
        "source_backfill_provenance_frozen":False,
        "actual_game_restock_certified":False,
    }
    if window is None:
        return result
    start,end=window
    if (type(start) is not int or type(end) is not int
        or end<=start or start<=issued or end>asof):
        raise ValueError("invalid bounded outcome period")
    last=None
    # Protect against a discarded cross-provider restock BEFORE the first
    # observed complete stock period. In that case the later event may not
    # really be the FIRST opportunity, so it is NOT scorable.
    ambiguous_change=False
    for obs in observations:
        if obs.epoch>asof:
            raise ValueError("future outcome observation")
        if last is not None and issued < obs.epoch <= start:
            if (obs.source != last.source and
                (obs.quantity>=MIN_QTY)!=(last.quantity>=MIN_QTY)):
                ambiguous_change=True
                break
        last=obs
    if ambiguous_change:
        result["status"]="AMBIGUOUS_CROSS_PROVIDER_EVENT_BEFORE_NEXT_RESTOCK"
        return result
    crosses=_gap_index(gaps,asof)
    if crosses(issued,start):
        result["status"]="COLLECTOR_GAP_BEFORE_NEXT_RESTOCK"
        return result
    result["next_observed_complete_start_epoch"]=start
    result["next_observed_complete_end_epoch"]=end
    if predicted_onset_epoch is None:
        result["status"]="NEXT_RESTOCK_OBSERVED_BUT_MODEL_ABSTAINED"
        return result
    error=predicted_onset_epoch-start
    absolute=abs(error)
    result.update({
        "status":"MATCHED_NEXT_BOUNDED_RESTOCK_TIMING_PROXY",
        "forecast_error_seconds":error,
        "absolute_forecast_error_seconds":absolute,
        "within_1_min":absolute<=60,
        "within_5_min":absolute<=300,
        "within_15_min":absolute<=900,
    })
    return result
