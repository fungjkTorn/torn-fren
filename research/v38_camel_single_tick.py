"""Research-only frozen Camel 24-template online probability selector single tick.

Exact original expert bank + live selection rule from camel_fast_selector.py,
but intentionally no full historical replay: TemplatePlanner only needs the
target's causal read-only Timeline. Selector score is UNCALIBRATED.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from services.frozen_candidate_worker_v31 import inspect_live_source
from research.plushie_champions.common import (
    connect, load_gaps, Timeline, TemplatePlanner,
    MAX_WAIT, STEP, GRACE, TRAVEL_SECONDS,
)

KEY="uae:Camel Plushie"
EXPERTS=tuple(
    (lags,look,shift)
    for lags in ((1,),(2,),(7,),(1,2),(1,7),(1,2,7))
    for look in (7200,14400)
    for shift in (3600,7200)
)


def predict(db: str|Path,country:str,item:str,now:int)->dict:
    country=country.strip().lower();item=item.strip();now=int(now)
    if f"{country}:{item}"!=KEY:
        return {"status":"NOT_APPROVED_CAMEL_SELECTOR"}
    source=inspect_live_source(db,now)
    if source["status"]!="FRESH":
        return {"status":source["status"]}
    con=connect(db)
    try:
        gs,ge=load_gaps(con)
        timeline=Timeline(con,gs,ge,country,item)
        ctx=SimpleNamespace(timelines={(country,item):timeline})
        candidates=[]
        for lags,look,shift in EXPERTS:
            candidate=TemplatePlanner(
                ctx,country,item,lags=lags,
                lookback=look,shift_range=shift,
            ).plan(float(now))
            if candidate is None or candidate[0]>now+MAX_WAIT:
                continue
            candidates.append((
                candidate[1],candidate[2].get("maxfit",0),
                -candidate[0],candidate,
            ))
    finally:
        con.close()
    if not candidates:
        return {"status":"NO_RECOMMENDATION","model_generation":"template_probability_selector"}
    # Preserve the October winning source's exact tie-break and 24-bank choice.
    dep=int(max(candidates,key=lambda x:(x[0],x[1],x[2]))[3][0])
    if dep<now or dep>now+MAX_WAIT:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    return {
        "status":"RESEARCH_PROPOSAL_ONLY",
        "model_generation":"template_probability_selector",
        "model_config":"camel_original_24_template_experts_probability_selector",
        "key":KEY,
        "query_timestamp":now,
        "recommended_departure_timestamp":dep,
        "recommended_arrival_timestamp":dep+TRAVEL_SECONDS[country],
        "replan_step_seconds":STEP,
        "research_horizon_seconds":MAX_WAIT,
        "quantity_threshold":30,
        "grace_seconds":GRACE,
        "probability_calibrated":False,
        "gameplay_automated":False,
        "source":"SOURCE_PINNED_CAMEL_24_EXPERT_SINGLE_TICK",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--country",required=True)
    p.add_argument("--item",required=True)
    p.add_argument("--now",required=True,type=int)
    a=p.parse_args()
    try:
        result=predict(a.db,a.country,a.item,a.now)
    except Exception as exc:
        result={"status":"V38_CAMEL_ERROR","error_type":type(exc).__name__}
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":main()
