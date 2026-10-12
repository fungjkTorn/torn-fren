"""Adapt original V18/V19/V20 plan() output to a 5m beta *PREVIEW* row.

The dynamic plan functions ALREADY return query_time, departure_time,
arrival_time and raw probability/support. They do NOT return a restock-time
forecast or a verified in-game success probability.

This strictly normalizes their emitted point WITHOUT running an expensive
research model or replacing existing V75 rows, specialists or V2 forecasts.
The output follows V97's explicit RESEARCH_PREVIEW_* contract, where a
prediction can be displayed but is NEVER promoted to verified gameplay GO.
Archived special champion replay.py bundles require other inference adapters;
do not pretend they are supported by this one.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS

ROSTER = Path(__file__).with_name("v38_roster.json")
OTHER_V19 = {
    "can:Xanax": "dyn8",
    "uni:Xanax": "dyn3",
}
SUPPORTED = frozenset({"V18", "V19", "V20"})
STEP_SECONDS = 300
MAX_WAIT_SECONDS = 28800
MAX_SOURCE_AGE_SECONDS = 180


def registered_models(roster_path=ROSTER):
    raw=json.loads(Path(roster_path).read_text(encoding="utf8"))
    result = {
        key: (str(r["model_family"]),r.get("config_name"))
        for key,r in raw["items"].items()
        if r.get("model_family") in SUPPORTED and r.get("source_verified") is True
    }
    for key, cfg in OTHER_V19.items():
        if key in result or key in raw["items"]:
            raise ValueError("roster changed; cannot append duplicated generic Xanax")
        result[key] = ("V19",cfg)
    if len(result) != 16:
        raise ValueError("pinned native V18/V19/V20 roster must have 16 items")
    return result


def _integer_like(x):
    if (type(x) not in (int,float) or not math.isfinite(x)
        or not 0 < x < 2**40 or abs(x-round(x))>1e-6):
        return None
    return int(round(x))


def preview_record(item_key, plan, *, family, config, issued_at,
                   stock_as_of, roster_path=ROSTER):
    """Produce independently labeled research preview for the existing board.

    Requires a real as-issued model plan already calculated by the original
    specialist; NEVER computes forecasts from future observations.
    """
    models=registered_models(roster_path)
    if (item_key not in models or
        models[item_key] != (family,config)):
        raise ValueError("wrong or unsupported pinned specialist")
    country,item = item_key.split(":",1)
    travel = TRAVEL_SECONDS[country]
    if (type(issued_at) is not int or type(stock_as_of) is not int
        or not 0 < stock_as_of <= issued_at < 2**40
        or issued_at-stock_as_of>MAX_SOURCE_AGE_SECONDS):
        raise ValueError("missing or stale issuance evidence")
    if plan is None:
        return {
            "item_key": item_key, "model_family":family,
            "model_config":config,"status":"RESEARCH_PREVIEW_ABSTAINED",
            "computed_at":issued_at,"stock_as_of":stock_as_of,
            "valid_until":issued_at+STEP_SECONDS,"departure":None,
            "arrival":None,"actionable":False,"experimental":True,
            "prediction_accuracy_verified":False,
            "probability_calibrated":False,
            "raw_model_availability_score":None,
            "source_interpretation":"NATIVE_ARRIVAL_PROPOSAL_NOT_RESTOCK",
        }
    if not isinstance(plan,dict):
        raise ValueError("native plan must be mapping or None")
    query = _integer_like(plan.get("query_time"))
    dep = _integer_like(plan.get("departure_time"))
    arr = _integer_like(plan.get("arrival_time"))
    raw_score = plan.get("probability")
    support = plan.get("support")
    if (query != issued_at or dep is None or arr is None
        or dep<issued_at or dep>issued_at+MAX_WAIT_SECONDS
        or (dep-issued_at)%STEP_SECONDS != 0
        or arr-dep != travel):
        raise ValueError("plan timing/country contract violated")
    if (type(raw_score) not in (int,float)
        or not math.isfinite(raw_score) or not 0 <= raw_score <= 1):
        raise ValueError("invalid raw score")
    if (type(support) not in (int,float)
        or not math.isfinite(support) or support <= 0):
        raise ValueError("invalid model support")
    return {
        "item_key":item_key, "model_family":family,
        "model_config":config,
        "status":"RESEARCH_PREVIEW_UNVALIDATED",
        "computed_at":issued_at, "stock_as_of":stock_as_of,
        "valid_until":issued_at+STEP_SECONDS,
        "departure":dep, "arrival":arr,
        "actionable":False,"experimental":True,
        "prediction_accuracy_verified":False,
        "probability_calibrated":False,
        "raw_model_availability_score":round(float(raw_score),8),
        "model_effective_support":round(float(support),6),
        "source_interpretation":"NATIVE_ARRIVAL_PROPOSAL_NOT_RESTOCK",
        "stock_30_at_landing_verified":False,
        "needs_near_departure_reconfirmation":True,
    }


def model_integration_inventory(roster_path=ROSTER):
    """Manifest of actual repo source capabilities, not deployed accuracy."""
    raw=json.loads(Path(roster_path).read_text(encoding="utf8"))
    natives=registered_models(roster_path)
    keys=set(raw["items"])|set(OTHER_V19)
    if len(keys)!=24:
        raise ValueError("unexpected roster size")
    out={}
    for key in sorted(keys):
        if key in natives:
            mode="NATIVE_PLAN_HAS_ARRIVAL_TIMES_NOT_RESTOCK_BOUNDARY"
        elif key=="jap:Xanax":
            mode="JAPAN_SPECIALIST_DEPLOYED_SOURCE_UNVERIFIED"
        else:
            mode="REPLAY_CHAMPION_LIVE_ADAPTER_UNVERIFIED"
        out[key]={
            "capability":mode,
            "native_preview_adapter_supported":key in natives,
            "live_website_model_mapping_verified":False,
            "arrival_stock_accuracy_verified":False,
        }
    return out
