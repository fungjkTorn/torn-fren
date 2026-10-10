"""Research-only original Nessie Plushie TemplatePlanner live single tick.

Uses the exact source-pinned recent-phase template algorithm, but avoids the
historical replay's all-10-plushie feature-context build: TemplatePlanner only
needs its target Timeline. No change to the algorithm, 2h/1d/+/-1h/.5 config.

Live source must be current; training input is strictly as-of the current tick.
Do not expose its uncalibrated template probability as a success guarantee.
"""
from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from pathlib import Path

from services.frozen_candidate_worker_v31 import inspect_live_source
from research.plushie_champions.common import (
    connect, load_gaps, Timeline, TemplatePlanner, MAX_WAIT, STEP, GRACE,
    TRAVEL_SECONDS,
)

COUNTRY="uni"
ITEM="Nessie Plushie"
CONFIG={"lags":(1,),"lookback":7200,"shift_range":3600,"minfit":0.5}
KEY=f"{COUNTRY}:{ITEM}"
TRAVEL=TRAVEL_SECONDS[COUNTRY]


def predict(db: str | Path,country:str,item:str,now:int)->dict:
    country=country.strip().lower()
    item=item.strip()
    now=int(now)
    if (country,item)!=(COUNTRY,ITEM):
        return {"status":"NOT_APPROVED_NESSIE_TEMPLATE"}
    source=inspect_live_source(db,now)
    if source["status"]!="FRESH":
        return {"status":source["status"]}
    con=connect(db)
    try:
        gs,ge=load_gaps(con)
        target=Timeline(con,gs,ge,country,item)
        # TemplatePlanner uses only ctx.timelines[(country,item)], not the
        # costly ResearchContext.build cross-plushie arrays/rolling medians.
        ctx=SimpleNamespace(timelines={(country,item):target})
        planner=TemplatePlanner(ctx,country,item,**CONFIG)
        choice=planner.plan(float(now))
    finally:
        con.close()
    if choice is None:
        return {"status":"NO_RECOMMENDATION","model_generation":"recent_phase_template"}
    dep=int(choice[0])
    if dep<now or dep>now+MAX_WAIT or dep-now>28800:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    return {
        "status":"RESEARCH_PROPOSAL_ONLY",
        "model_generation":"recent_phase_template",
        "model_config":"nessie_recent_phase_lookback2h_lag1_shift1h_minfit0.5",
        "key":KEY,
        "query_timestamp":now,
        "recommended_departure_timestamp":dep,
        "recommended_arrival_timestamp":dep+TRAVEL,
        "replan_step_seconds":STEP,
        "research_horizon_seconds":MAX_WAIT,
        "quantity_threshold":30,
        "grace_seconds":GRACE,
        "probability_calibrated":False,
        "gameplay_automated":False,
        "source":"SOURCE_PINNED_NESSIE_TEMPLATE_SINGLE_TICK",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--country",required=True)
    p.add_argument("--item",required=True)
    p.add_argument("--now",required=True,type=int)
    a=p.parse_args()
    try:
        response=predict(a.db,a.country,a.item,a.now)
    except Exception as exc:
        response={"status":"V38_NESSIE_ERROR","error_type":type(exc).__name__}
    print(json.dumps(response,sort_keys=True))


if __name__=="__main__":
    main()
