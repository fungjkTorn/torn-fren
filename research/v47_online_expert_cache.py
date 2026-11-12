"""V47 exact online template champion with incremental, resolved-only ledger.

PRIVATE research adapter; not yet scheduled. Source algorithms:
research/plushie_champions/checkpoint4_online_selector.py (frozen 24 expert
bank, Beta(2,2) posterior, 2/3-day selection) and TemplatePlanner.

No synthetic success or partially scored expert bank. Until all eligible
historical expert decisions are evaluated the adapter abstains. An ordinary
new live stock-change row never causes wholesale recomputation; any gap
revision or backdated target row invalidates the target's ledger.

Does not write collector history, public predictions, or existing V38 sidecar.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

from services.frozen_candidate_worker_v31 import inspect_live_source
from research.plushie_champions.common import (
    connect, load_gaps, Timeline, gap_overlap, MAX_WAIT, STEP, GRACE,
    DAY, TRAVEL_SECONDS,
)
from research.v45_online_template_probe import (
    EXPERTS, TARGETS, STRIDE, simulate_one,
)
from research.v46_fast_template import FastTemplatePlanner

SCHEMA=1
CACHE_TABLE="""CREATE TABLE IF NOT EXISTS expert_resolutions(
 item_key TEXT NOT NULL, anchor_ts INTEGER NOT NULL, expert_id INTEGER NOT NULL,
 status TEXT NOT NULL, success INTEGER, resolved_at INTEGER,
 departure INTEGER, arrival INTEGER, PRIMARY KEY(item_key,anchor_ts,expert_id)
)"""
STATE_TABLE="""CREATE TABLE IF NOT EXISTS expert_source_state(
 item_key TEXT PRIMARY KEY, gap_fingerprint TEXT NOT NULL,
 source_max_id INTEGER NOT NULL
)"""
DEFAULT_CACHE="/var/lib/torn-fren-v47/online_expert_cache.db"


def initialize(con):
    con.execute("PRAGMA busy_timeout=3000")
    con.execute(CACHE_TABLE)
    con.execute(STATE_TABLE)
    con.execute("CREATE INDEX IF NOT EXISTS idx_expert_resolutions ON expert_resolutions(item_key,anchor_ts)")
    con.commit()


def eligible_starts(timeline, gs, ge, country, now, window_days):
    """Exactly valid_start warmup and 30-min stride, all outcomes resolved."""
    maxfuture=MAX_WAIT+TRAVEL_SECONDS[country]+GRACE
    first=max(float(timeline.ts[0])+8*DAY,now-window_days*DAY)
    lo=math.ceil(first/STRIDE)*STRIDE
    hi=math.floor((now-maxfuture)/STRIDE)*STRIDE
    anchors=[]
    for s in range(lo,hi+1,STRIDE):
        a,_,_=timeline.vals([s])
        if math.isnan(float(a[0])):
            continue
        if gap_overlap(gs,ge,s,s+maxfuture):
            continue
        anchors.append(s)
    return anchors


def gap_fingerprint(gs,ge):
    pairs=list(zip([float(x) for x in gs],[float(x) for x in ge]))
    return hashlib.sha256(json.dumps(pairs,separators=(",",":")).encode()).hexdigest()


def update_cache_source(con, source_con, key, country, item, digest):
    """Explicitly invalidate backdated stock inserts or revised gap intervals."""
    maximum=source_con.execute("SELECT COALESCE(MAX(id),0) FROM stock_history").fetchone()[0]
    row=con.execute("SELECT gap_fingerprint,source_max_id FROM expert_source_state WHERE item_key=?",(key,)).fetchone()
    reset=False
    if row:
        previous_hash,lastid=row
        reset=previous_hash!=digest or maximum<lastid
        if not reset and lastid!=maximum:
            # Non-target stock rows are irrelevant; newer normal target changes
            # cannot alter resolved historical labels. For maximum safety,
            # detect ANY inserted target row older than a cached decision path.
            # We cap at the newest stored resolved path before this run.
            last_cached=con.execute(
                "SELECT MAX(resolved_at) FROM expert_resolutions WHERE item_key=?",
                (key,)
            ).fetchone()[0]
            if last_cached is not None:
                amended=source_con.execute("""SELECT 1 FROM stock_history
                  WHERE id>? AND country=? AND lower(item_name)=lower(?)
                    AND timestamp<=? LIMIT 1""",
                  (lastid,country,item,int(last_cached))).fetchone()
                if amended: reset=True
    with con:
        if reset:
            con.execute("DELETE FROM expert_resolutions WHERE item_key=?",(key,))
        con.execute("""INSERT INTO expert_source_state VALUES(?,?,?)
            ON CONFLICT(item_key) DO UPDATE SET
            gap_fingerprint=excluded.gap_fingerprint,
            source_max_id=excluded.source_max_id""",(key,digest,int(maximum)))
    return reset


def score_experts(entries, anchors, now, days, count=len(EXPERTS)):
    """Exact frozen checkpoint4 Beta(2,2), prefer more resolved wins on ties.

    Return None until every eligible original expert is scored, including
    explicit no-schedule entries (not counted as misses).
    """
    if any((s,e) not in entries for s in anchors for e in range(count)):
        return None
    cut=now-days*DAY
    scored=[]
    for e in range(count):
        outcomes=[entries[(s,e)] for s in anchors
                  if cut<=s<now and entries[(s,e)][1] is not None
                  and entries[(s,e)][1]<now]
        successes=[x[0] for x in outcomes if x[0] in (0,1)]
        if len(successes)!=len(outcomes):
            raise ValueError("inconsistent expert cache outcome")
        n=len(successes)
        score=(sum(successes)+2)/(n+4) if n else .5
        scored.append((score,n,e))
    # Python max on ties is stable, preserving the frozen bank ordering.
    best=max(scored,key=lambda x:(x[0],x[1]))
    return {"expert_index":best[2],"posterior_score":best[0],
            "resolved_count":best[1],"expert_bank_size":count}


def run(db,cache,target,now,*,budget_seconds=35,max_decisions=24):
    if target not in TARGETS:
        raise ValueError("not an approved online specialist target")
    if not 1<=budget_seconds<=120 or not 1<=max_decisions<=200:
        raise ValueError("bounded replay arguments required")
    country,item,days=TARGETS[target]
    key=f"{country}:{item}"
    now=int(now)
    freshness=inspect_live_source(db,now)
    if freshness.get("status")!="FRESH":
        return {"status":freshness.get("status","NO_COLLECTOR_HEARTBEAT"),"key":key}
    started=time.monotonic()
    source=connect(db,readonly=True)
    try:
        source.execute("BEGIN")
        gs,ge=load_gaps(source)
        tl=Timeline(source,gs,ge,country,item)
        if tl.ts[-1]>now:
            return {"status":"FUTURE_STOCK_ROWS_REJECTED","key":key}
        anchors=eligible_starts(tl,gs,ge,country,now,days)
        if not anchors:
            return {"status":"NO_FULLY_RESOLVED_ANCHORS","key":key}
        p=Path(cache)
        p.parent.mkdir(parents=True,exist_ok=True)
        side=sqlite3.connect(p,timeout=3)
        try:
            initialize(side)
            invalidated=update_cache_source(side,source,key,country,item,
                                             gap_fingerprint(gs,ge))
            all_rows=side.execute("""SELECT anchor_ts,expert_id,success,resolved_at
                FROM expert_resolutions WHERE item_key=? AND anchor_ts>=?""",
                (key,anchors[0])).fetchall()
            entries={(int(s),int(e)):(success,resolved)
                     for s,e,success,resolved in all_rows}
            ctx=SimpleNamespace(timelines={(country,item):tl})
            planners={}
            processed=0
            # Advance oldest missing resolved evidence first. All anchors
            # and experts are eventually filled without resimulating successes.
            for s in anchors:
                for e,(lags,look,shift) in enumerate(EXPERTS):
                    if (s,e) in entries:
                        continue
                    if processed>=max_decisions or time.monotonic()-started>=budget_seconds:
                        break
                    if e not in planners:
                        planners[e]=FastTemplatePlanner(
                            ctx,country,item,lags=lags,lookback=look,
                            shift_range=shift)
                    outcome=simulate_one(planners[e].plan,tl,s,TRAVEL_SECONDS[country])
                    success=outcome.get("success")
                    resolved=outcome.get("resolved_at")
                    with side:
                        side.execute("""INSERT OR IGNORE INTO expert_resolutions
                            VALUES(?,?,?,?,?,?,?,?)""",
                            (key,int(s),e,outcome["status"],
                             success,resolved,outcome.get("departure"),
                             outcome.get("arrival")))
                    entries[(s,e)]=(success,resolved)
                    processed+=1
                if processed>=max_decisions or time.monotonic()-started>=budget_seconds:
                    break
            expected=len(anchors)*len(EXPERTS)
            observed=sum((s,e) in entries for s in anchors for e in range(len(EXPERTS)))
            response={
                "key":key,
                "source":"SOURCE_PINNED_CHECKPOINT4_RESOLVED_ONLINE_SELECTOR",
                "research_only":True,
                "model_generation":"online_template_expert",
                "model_config":f"original_{len(EXPERTS)}_experts_{days}d_resolved_selector",
                "cache_schema":SCHEMA,
                "cached_decisions":observed,
                "required_decisions":expected,
                "missing_decisions":expected-observed,
                "executed_decisions":processed,
                "cache_invalidated":invalidated,
                "elapsed_seconds":round(time.monotonic()-started,3),
                "probability_calibrated":False,
                "gameplay_automated":False,
            }
            if observed!=expected:
                return {**response,"status":"BUILDING_RESOLVED_EXPERT_CACHE"}
            selection=score_experts(entries,anchors,now,days)
            selected=selection["expert_index"]
            lags,look,shift=EXPERTS[selected]
            candidate=planners.get(selected)
            if candidate is None:
                candidate=FastTemplatePlanner(
                    ctx,country,item,lags=lags,lookback=look,
                    shift_range=shift)
            slot=(now//STEP)*STEP
            recommendation=candidate.plan(float(slot))
            response.update({
                "chosen_expert_index":selected,
                "resolved_evidence_count":selection["resolved_count"],
                "posterior_research_score_uncalibrated":selection["posterior_score"],
            })
            if recommendation is None:
                return {**response,"status":"NO_RECOMMENDATION"}
            departure=int(recommendation[0])
            if departure<now:
                return {**response,"status":"DEPARTURE_PASSED"}
            if departure>now+MAX_WAIT:
                return {**response,"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
            return {**response,
                    "status":"RESEARCH_PROPOSAL_ONLY",
                    "query_timestamp":now,
                    "recommended_departure_timestamp":departure,
                    "recommended_arrival_timestamp":departure+TRAVEL_SECONDS[country],
                    "replan_step_seconds":STEP,"research_horizon_seconds":MAX_WAIT,
                    "quantity_threshold":30,"grace_seconds":GRACE,
                    "source":"SOURCE_PINNED_CHECKPOINT4_CACHE_COMPLETE_PRIVATE"}
        finally:
            side.close()
    finally:
        source.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",default="/opt/torn-fren/data/stock_history.db")
    p.add_argument("--cache",default=DEFAULT_CACHE)
    p.add_argument("--target",choices=tuple(TARGETS),required=True)
    p.add_argument("--now",type=int,default=None)
    p.add_argument("--budget",type=float,default=35)
    p.add_argument("--max-decisions",type=int,default=24)
    a=p.parse_args()
    try:
        result=run(a.db,a.cache,a.target,int(time.time()) if a.now is None else a.now,
                   budget_seconds=a.budget,max_decisions=a.max_decisions)
    except Exception as exc:
        result={"status":"V47_EXPERT_CACHE_ERROR","error_type":type(exc).__name__}
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
