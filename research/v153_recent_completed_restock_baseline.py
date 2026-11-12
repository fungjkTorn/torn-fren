"""V153: causal recent observed HIGH/LOW phase timing challenger.

Only completed start/end periods accepted by V145 are used. Historical
start/end provenance is preserved, benign provider-switch periods count,
and gaps or cross-provider threshold disagreements are still discarded.

V151's baseline next-restock median is compared to pre-registered short
history variants on EXACT same eligible as-issued and next-restock episodes:
recent_3, recent_5, recent_10, all history. None is promoted before
out-of-sample MAE/coverage and independent episode checks. No lookup of the
future outcome in this model, no Torn calls, no production mutations.
"""
from __future__ import annotations

import statistics
from research.plushie_champions.common import TRAVEL_SECONDS

PREDECLARED_WINDOWS=(3,5,10)
MAX_HISTORY_INTERVALS=10000


def _duration_intervals(rows, *, asof):
    if not isinstance(rows,list) or len(rows)>MAX_HISTORY_INTERVALS:
        raise ValueError("invalid bounded history")
    last_end=-1
    out=[]
    for start,end in rows:
        if (type(start) is not int or type(end) is not int
            or start<=0 or end<=start or end>asof
            or start<last_end):
            raise ValueError("inconsistent historical bounded interval")
        out.append(end-start)
        last_end=end
    return out


def _median(xs):
    if not xs:
        return None
    return int(statistics.median(xs))


def _predict(phase,age,high,low):
    if not high or not low:
        return None,"NEEDS_ONE_BOUNDED_PERIOD_EACH"
    if phase=="LOW":
        surviving=[duration-age for duration in low if duration>age]
        if not surviving:
            return None,"NO_SURVIVING_RECENT_DEPLETION_ANALOG"
        return _median(surviving),"CURRENT_LOW_SURVIVAL_PLUS_ZERO"
    if phase=="HIGH":
        remaining=[duration-age for duration in high if duration>age]
        if not remaining:
            return None,"NO_SURVIVING_RECENT_STOCK_ANALOG"
        return _median(remaining)+_median(low),"CURRENT_HIGH_SURVIVAL_PLUS_NEXT_LOW"
    return None,"CURRENT_PHASE_UNKNOWN"


def recent_restock_forecasts(item_key, history, *, asof):
    """Return predeclared estimates, never a flight instruction or GO."""
    if (not isinstance(item_key,str) or item_key.count(":")!=1
        or type(asof) is not int or asof<=0 or not isinstance(history,dict)):
        raise ValueError("invalid candidate")
    country,item=item_key.split(":",1)
    if country not in TRAVEL_SECONDS or not item:
        raise ValueError("unsupported item country")
    last=history.get("last_observation")
    onset=history.get("phase_onset")
    phase=history.get("phase")
    result={
        "item_key":item_key,"issued_epoch":asof,"status":"UNKNOWN_CURRENT_PHASE",
        "forecasts":{},"history_only_completed_boundaries":True,
        "published_departure":None,"calibrated_probability":None,
        "future_information_used_in_forecast":False,
        "actual_arrival_verified":False,
    }
    high=_duration_intervals(
        history.get("observed_bounded_stocked_windows"),asof=asof)
    low=_duration_intervals(
        history.get("observed_bounded_depleted_windows"),asof=asof)
    if (last is None or type(last.epoch) is not int or
        last.epoch>asof or type(onset) is not int or
        not 0<=onset<=asof or phase not in ("HIGH","LOW") or
        (last.quantity>=30)!=(phase=="HIGH")):
        return result
    age=asof-onset
    if not high or not low:
        result["status"]="NO_COMPLETE_BOTH_PHASE_TYPES"
        return result
    for width in (*PREDECLARED_WINDOWS,None):
        name="all_bounded" if width is None else f"recent_{width}"
        sample_high=high if width is None else high[-width:]
        sample_low=low if width is None else low[-width:]
        required=3 if width is not None else 1
        if min(len(sample_high),len(sample_low))<required:
            result["forecasts"][name]={
                "forecast_epoch":None,"status":"TOO_FEW_COMPLETED_PERIODS",
                "observed_high_count":len(sample_high),
                "observed_low_count":len(sample_low)}
            continue
        seconds,reason=_predict(phase,age,sample_high,sample_low)
        result["forecasts"][name]={
            "forecast_epoch":asof+seconds if seconds is not None else None,
            "status":reason,
            "observed_high_count":len(sample_high),
            "observed_low_count":len(sample_low),
            "median_high_lifetime_seconds":_median(sample_high),
            "median_depleted_lifetime_seconds":_median(sample_low),
            "elapsed_current_phase_seconds":age,
            "research_only":True,
        }
    result["status"]="ISSUED_PREDECLARED_RECENCY_CHALLENGERS"
    return result
