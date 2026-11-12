"""V93 source-aware arrival audit design, PURE functions, no network or DB writes.

YATA exports include country-specific "update" timestamps. Current collector
persists each item change with local time and provider source, not that
country-update epoch. An HTTP fetch is NOT proof of a freshly updated country.

This module designs optional *shared* extra export observations using the
intersection of arrival .. arrival+10s windows, deduplicates forecast target
IDs, enforces a global rate budget, and validates decoded observation metadata.
The default extra-poll budget is ZERO. This module does not send requests,
schedule timers, access APIs, or perform gameplay actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

GRACE=10
MAX_AGE_SECONDS=60
MAX_FUTURE_SECONDS=28800
SOURCES={"yata","prometheus"}


@dataclass(frozen=True)
class ArrivalTarget:
    forecast_id: str
    item_key: str
    arrival_epoch: int
    forecast_issued_epoch: int
    valid_until_epoch: int


def _parse_epoch(value):
    if type(value) is int:
        return value if value>0 else None
    if isinstance(value,str) and value.isdecimal() and 0<len(value)<16:
        parsed=int(value)
        return parsed if parsed>0 else None
    return None


def decode_export_observation(export, *, item_key, received_epoch,
                              max_country_age=MAX_AGE_SECONDS):
    """Return precise origin-age status, not self-certified game stock truth."""
    base={"item_key":item_key,"received_epoch":received_epoch,
          "quantity":None,"source":None,"country_update_epoch":None,
          "country_age_seconds":None,
          "export_timestamp":None,"status":"INVALID_EXPORT"}
    if (type(received_epoch) is not int or received_epoch<=0
        or not isinstance(item_key,str) or ":" not in item_key
        or not 0<=max_country_age<=1800):
        return base
    country,item = item_key.split(":",1)
    if not country or not item or not isinstance(export,dict):
        return base
    source=export.get("source")
    if source not in SOURCES:
        return base
    base["source"]=source
    base["export_timestamp"]=_parse_epoch(export.get("timestamp"))
    countries=export.get("stocks")
    if not isinstance(countries,dict) or country not in countries:
        base["status"]="COUNTRY_MISSING"
        return base
    record=countries[country]
    if not isinstance(record,dict):
        return base
    country_ts=_parse_epoch(record.get("update"))
    if country_ts is not None:
        base["country_update_epoch"]=country_ts
        base["country_age_seconds"]=received_epoch-country_ts
    items=record.get("stocks")
    if not isinstance(items,list):
        return base
    matched=[i for i in items if isinstance(i,dict)
             and i.get("name")==item]
    if len(matched)!=1:
        base["status"]="ITEM_MISSING_OR_DUPLICATED"
        return base
    q=matched[0].get("quantity")
    if type(q) is not int or q<0:
        base["status"]="INVALID_QUANTITY"
        return base
    base["quantity"]=q
    if country_ts is None:
        base["status"]="COUNTRY_TIMESTAMP_MISSING"
    elif country_ts>received_epoch:
        base["status"]="COUNTRY_TIMESTAMP_IN_FUTURE"
    elif received_epoch-country_ts>max_country_age:
        base["status"]="COUNTRY_UPDATE_STALE"
    else:
        base["status"]="FRESH_PROVIDER_OBSERVATION"
    return base


def plan_extra_observations(targets, *, now, per_hour_budget=0,
                            min_request_spacing=60):
    """Produce at most a rate-limited plan; default zero calls.

    An exact +10s shared capture for all targets is only possible when their
    [arrival,arrival+10s] windows intersect. A planned fetch at time T is not
    proof of YATA actually refreshing at T or network response arriving by T.
    """
    if (type(now) is not int or now<=0 or type(per_hour_budget) is not int
        or not 0<=per_hour_budget<=60 or type(min_request_spacing) is not int
        or not 1<=min_request_spacing<=3600):
        raise ValueError("invalid arrival-observer budget")
    uniq={}
    excluded=Counter()
    for t in targets:
        if not isinstance(t,ArrivalTarget):
            excluded["INVALID_TARGET"]+=1
            continue
        fields=(t.arrival_epoch,t.forecast_issued_epoch,t.valid_until_epoch)
        if (not isinstance(t.forecast_id,str) or not t.forecast_id
            or not isinstance(t.item_key,str) or ":" not in t.item_key
            or any(type(x) is not int for x in fields)
            or not t.forecast_issued_epoch<=now<t.valid_until_epoch
            or t.arrival_epoch<now
            or t.arrival_epoch-now>MAX_FUTURE_SECONDS):
            excluded["INVALID_OR_EXPIRED"]+=1
            continue
        key=(t.item_key,t.arrival_epoch)
        if key not in uniq or t.forecast_issued_epoch<uniq[key].forecast_issued_epoch:
            uniq[key]=t

    targets_sorted=sorted(uniq.values(),
                          key=lambda t:(t.arrival_epoch,t.item_key,t.forecast_id))
    groups=[]
    current=None
    for t in targets_sorted:
        low=t.arrival_epoch
        high=t.arrival_epoch+GRACE
        if current is not None and low<=current["high"]:
            current["low"]=max(current["low"],low)
            current["high"]=min(current["high"],high)
            current["target_ids"].append(t.forecast_id)
            current["items"].add(t.item_key)
        else:
            if current is not None:
                groups.append(current)
            current={"low":low,"high":high,
                     "target_ids":[t.forecast_id],"items":{t.item_key}}
    if current is not None:
        groups.append(current)

    accepted=[]
    skipped=Counter()
    hour_counts=Counter()
    last_request=None
    for group in groups:
        at=group["low"]
        bucket=at//3600
        if per_hour_budget==0:
            skipped["DISABLED_BY_DEFAULT"]+=1
            continue
        if hour_counts[bucket]>=per_hour_budget:
            skipped["HOURLY_EXTRA_EXPORT_BUDGET"]+=1
            continue
        if last_request is not None and at-last_request<min_request_spacing:
            skipped["RATE_LIMIT_SPACING"]+=1
            continue
        hour_counts[bucket]+=1
        last_request=at
        accepted.append({
            "planned_request_epoch":at,
            "latest_on_time_request_epoch":group["high"],
            "item_keys":sorted(group["items"]),
            "forecast_ids":sorted(group["target_ids"]),
            "expected_network_source":"FULL_TRAVEL_EXPORT_ONLY",
            "actual_country_age_known":False,
        })
    return {
        "status":"RESEARCH_DESIGN_ONLY_NO_REQUESTS_EXECUTED",
        "now":now,"extra_fetch_budget_per_hour":per_hour_budget,
        "unique_item_arrival_targets":len(targets_sorted),
        "coalesced_precise_windows":len(groups),
        "hypothetical_extra_fetches":len(accepted),
        "hypothetical_plan":accepted,
        "excluded_target_counts":dict(sorted(excluded.items())),
        "skipped_window_counts":dict(sorted(skipped.items())),
        "note":"No YATA calls made; this is only a proposed schedule. Country provider update freshness must be checked on returned exports.",
    }
