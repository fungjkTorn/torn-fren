"""V166 seven-specialist causal 5-minute earliest-restock replay.

Targets the recovered plushie specialists that are hardest to generalize:
Monkey, Chamois, Panda, Lion, Camel, Nessie, Red Fox.

This is the bridge from recovered champion code to the actual TORN-FREN
decision contract.  Each item is replayed on a rolling causal SQLite mirror
that contains only evidence available by the historical issue clock.
Predictions are rescored against sealed future truth for:
  * stock >=30 at arrival
  * earliest actually reachable restock window
  * timing error relative to that restock
  * 5-minute replan stability / confirmation

No production, website, collector, or live routing writes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import (
    ResearchContext, TemplatePlanner, valid_starts, TRAVEL_SECONDS,
    MAX_WAIT, STEP, GRACE, DAY,
)
from research.v164_evidence_routed_earliest_restock import (
    _truth_rows, _earliest_reachable_window, _clean_windows,
)
from research.japan_xanax.renewal_shadow import source_data

MODEL_FREEZE_EPOCH=1791504000  # 2026-10-09 00:00:00 UTC; after roster freeze
MIN_QTY=30
SEVEN=(
    "arg:Monkey Plushie",
    "swi:Chamois Plushie",
    "chi:Panda Plushie",
    "sou:Lion Plushie",
    "uae:Camel Plushie",
    "uni:Nessie Plushie",
    "uni:Red Fox Plushie",
)

CHECKPOINT4_EXPERTS=[
    (lags,look,shift)
    for lags in ((1,),(2,),(7,),(1,2),(1,7),(1,2,7))
    for look in (7200,14400)
    for shift in (3600,7200)
]
CHECKPOINT4_DAYS={"arg:Monkey Plushie":2,"swi:Chamois Plushie":3}


def _ro(path):
    p=Path(path).expanduser().resolve(strict=True)
    db=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=30)
    db.execute("PRAGMA query_only=ON")
    return db


class CausalMirror:
    """Rolling sanitized mirror with no rows after the current issue clock."""
    def __init__(self, source, target, start):
        self.source=Path(source).expanduser().resolve(strict=True)
        self.target=Path(target)
        if self.target.exists(): self.target.unlink()
        with closing(sqlite3.connect(self.target)) as dst:
            dst.executescript("""
            PRAGMA journal_mode=DELETE;
            CREATE TABLE stock_history(
              id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
              item_name TEXT,quantity INTEGER,source TEXT);
            CREATE TABLE poll_heartbeats(
              id INTEGER PRIMARY KEY,timestamp INTEGER,mode TEXT,success INTEGER);
            CREATE TABLE collection_gaps(
              id INTEGER PRIMARY KEY,start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
            CREATE INDEX stock_item ON stock_history(country,item_name,timestamp);
            CREATE INDEX stock_clock ON stock_history(timestamp);
            CREATE INDEX poll_clock ON poll_heartbeats(mode,success,timestamp);
            CREATE INDEX gap_clock ON collection_gaps(start_timestamp,end_timestamp);
            """)
        self.clock=None
        self.advance(start)

    def advance(self, issued):
        issued=int(issued)
        if self.clock is not None and issued<self.clock:
            raise ValueError("causal mirror clock moved backwards")
        lower=-1 if self.clock is None else self.clock
        with closing(_ro(self.source)) as src, closing(sqlite3.connect(self.target)) as dst:
            stock=src.execute(
                """SELECT id,timestamp,country,item_name,quantity,source
                   FROM stock_history WHERE timestamp>? AND timestamp<=?
                   ORDER BY timestamp,id""",(lower,issued)).fetchall()
            polls=src.execute(
                """SELECT id,timestamp,mode,success FROM poll_heartbeats
                   WHERE timestamp>? AND timestamp<=? ORDER BY timestamp,id""",
                (lower,issued)).fetchall()
            gaps=src.execute(
                """SELECT id,start_timestamp,
                          CASE WHEN end_timestamp IS NOT NULL AND end_timestamp<=?
                               THEN end_timestamp ELSE NULL END,
                          COALESCE(reason,'historical')
                   FROM collection_gaps
                   WHERE start_timestamp<=? ORDER BY start_timestamp,id""",
                (issued,issued)).fetchall()
            with dst:
                if stock: dst.executemany("INSERT OR IGNORE INTO stock_history VALUES(?,?,?,?,?,?)",stock)
                if polls: dst.executemany("INSERT OR IGNORE INTO poll_heartbeats VALUES(?,?,?,?)",polls)
                dst.execute("DELETE FROM collection_gaps")
                if gaps: dst.executemany("INSERT INTO collection_gaps VALUES(?,?,?,?)",gaps)
        self.clock=issued


def _checkpoint4_single_tick(db,key,issued):
    """Exact recovered checkpoint4 policy, evaluated causally at one issue."""
    country,item=key.split(":",1)
    days=CHECKPOINT4_DAYS[key]
    ctx=ResearchContext.build(db,asof=issued,readonly=True)
    try:
        starts=valid_starts(ctx,country,item)
        if not starts:
            return dict(status="NO_VALID_STARTS",departure=None)
        planners={
            e:TemplatePlanner(ctx,country,item,lags=e[0],lookback=e[1],
                              shift_range=e[2]).plan
            for e in CHECKPOINT4_EXPERTS
        }
        timeline=ctx.timelines[(country,item)]
        cut=issued-days*DAY
        past=[s for s in starts if cut<=s<issued]
        scores=[]
        for e,p in planners.items():
            ys=[]
            for s in past:
                q=s;deadline=s+MAX_WAIT;sched=None;resolved=None
                while q<=deadline:
                    z=p(q)
                    if z and z[0]<=deadline:sched=z
                    if sched and sched[0]<=q+STEP:
                        dep=max(q,int(sched[0]))
                        arrival=dep+TRAVEL_SECONDS[country]+GRACE
                        if arrival<issued:
                            ys.append(int(timeline.success(dep+TRAVEL_SECONDS[country],GRACE)))
                        resolved=arrival
                        break
                    q+=STEP
            score=(sum(ys)+2)/(len(ys)+4) if ys else .5
            scores.append((score,len(ys),e))
        expert=max(scores,key=lambda x:(x[0],x[1]))[2]
        choice=planners[expert](float((issued//STEP)*STEP))
        if choice is None:
            return dict(status="NO_RECOMMENDATION",departure=None,expert=expert)
        dep=int(choice[0])
        if not issued<=dep<=issued+MAX_WAIT:
            return dict(status="OUT_OF_BOUNDS",departure=None,expert=expert)
        return dict(status="CHECKPOINT4_CAUSAL_PROPOSAL",departure=dep,expert=expert)
    finally:
        ctx.con.close()


def specialist_plan(db,key,issued):
    country,item=key.split(":",1)
    if key in CHECKPOINT4_DAYS:
        return _checkpoint4_single_tick(db,key,issued)

    if key in ("chi:Panda Plushie","sou:Lion Plushie"):
        from research.v52_pair_trained_tick import predict
        from research.v81_pair_forward_comparison import PINS
        root=Path(__file__).resolve().parents[1]
        target="panda" if key.startswith("chi:") else "lion"
        artifact=Path("/home/ubuntu/torn-fren-private-models")/(target+"_selector_artifact.json")
        # On PC the reviewed artifacts may instead be copied under research artifacts.
        if not artifact.is_file():
            local=root/"historical_pc_data"/(target+"_selector_artifact.json")
            artifact=local if local.is_file() else artifact
        r=predict(db,target,issued,artifact,PINS[target])
        dep=r.get("research_departure_timestamp")
        return dict(status=r.get("candidate_status") or r.get("status"),departure=dep)

    if key=="uae:Camel Plushie":
        from research.v38_camel_single_tick import predict
    elif key=="uni:Nessie Plushie":
        from research.v38_nessie_single_tick import predict
    elif key=="uni:Red Fox Plushie":
        from research.v38_red_fox_single_tick import predict
    else:
        raise ValueError("unsupported V166 specialist")
    r=predict(db,country,item,issued)
    return dict(status=r.get("status"),departure=r.get("recommended_departure_timestamp"))


def _score_departure(source,key,issued,dep,truth_cutoff):
    country=key.split(":",1)[0]
    flight=TRAVEL_SECONDS[country]
    rows,gaps=_truth_rows(source,key,truth_cutoff)
    target=_earliest_reachable_window(rows,gaps,issued,flight,truth_cutoff)
    out=dict(target_status=target["status"])
    if dep is None:
        return out
    arr=dep+flight
    evidence=source_data(source,now=truth_cutoff,item_key=key)[3]
    state=evidence.score(arr)[0]
    out.update(departure=dep,arrival=arr,arrival_state=state)
    if target["status"]=="EARLIEST_REACHABLE_FOUND":
        start,end=target["restock"],target["depletion"]
        scored=arr+GRACE
        out["target_restock"]=start
        out["oracle_earliest_departure"]=target["oracle_earliest_departure"]
        out["departure_delay_vs_oracle_seconds"]=dep-target["oracle_earliest_departure"]
        out["arrival_minus_restock_seconds"]=arr-start
        if scored<start: out["earliest_outcome"]="TOO_EARLY"
        elif end is not None and scored>=end:
            later=next((w for w in _clean_windows(rows,gaps,truth_cutoff)
                        if w[0]>start and w[0]<=scored and
                        (w[1] is None or scored<w[1])),None)
            out["earliest_outcome"]="SKIPPED_TO_LATER" if later else "TOO_LATE"
        else:
            out["earliest_outcome"]="HIT"
    return out


def replay_item(*,source,key,start,end,step=STEP,workdir):
    if key not in SEVEN: raise ValueError("key not in seven-specialist roster")
    if start<MODEL_FREEZE_EPOCH:
        raise ValueError("V166 refuses pre-freeze specialist evaluation")
    if end<=start or step!=STEP:
        raise ValueError("invalid replay window")
    truth_cutoff=source_data(source,item_key=key)[4]
    if end+MAX_WAIT+TRAVEL_SECONDS[key.split(":",1)[0]]+GRACE>truth_cutoff:
        raise ValueError("replay window has immature future truth")
    scratch=Path(workdir)/(key.replace(":","__").replace(" ","_")+".sqlite")
    mirror=CausalMirror(source,scratch,start)
    records=[]
    try:
        previous=None
        for issued in range(start,end+1,STEP):
            mirror.advance(issued)
            raw=specialist_plan(scratch,key,issued)
            dep=raw.get("departure")
            scored=_score_departure(source,key,issued,dep,truth_cutoff)
            same=(previous is not None and dep is not None and
                  previous.get("departure") is not None and abs(dep-previous["departure"])<=STEP)
            row=dict(item_key=key,issued=issued,status=raw.get("status"),
                     departure=dep,reconfirmed_previous=bool(same),**scored)
            records.append(row)
            previous=row
    finally:
        try: scratch.unlink()
        except OSError: pass

    c=Counter()
    for r in records:
        c["issues"]+=1
        if r.get("departure") is None:
            c["abstain"]+=1
            continue
        c["proposals"]+=1
        if r.get("arrival_state") in ("SUCCESS","FAILURE"):
            c["arrival_known"]+=1
            c["arrival_success"]+=int(r["arrival_state"]=="SUCCESS")
        eo=r.get("earliest_outcome")
        if eo:
            c["earliest_scored"]+=1
            c["earliest_hit"]+=int(eo=="HIT")
            c["earliest_"+eo.lower()]+=1
        c["reconfirmed_previous"]+=int(r.get("reconfirmed_previous",False))
    return {
        "item_key":key,"start":start,"end":end,"step_seconds":STEP,
        "counts":dict(c),
        "arrival_success_fraction":c["arrival_success"]/c["arrival_known"] if c["arrival_known"] else None,
        "earliest_restock_hit_fraction":c["earliest_hit"]/c["earliest_scored"] if c["earliest_scored"] else None,
        "proposal_coverage":c["proposals"]/c["issues"] if c["issues"] else None,
        "records":records,
        "production_modified":False,"actual_flights":False,
        "post_freeze_only":True,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--item-key",required=True,choices=SEVEN)
    p.add_argument("--start-epoch",required=True,type=int)
    p.add_argument("--end-epoch",required=True,type=int)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    out=Path(a.output).expanduser().resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v166-") as td:
        result=replay_item(source=a.source,key=a.item_key,start=a.start_epoch,
                           end=a.end_epoch,workdir=td)
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    c=result["counts"]
    print(json.dumps({
        "item":a.item_key,
        "issues":c.get("issues",0),
        "proposals":c.get("proposals",0),
        "arrival_success_fraction":result["arrival_success_fraction"],
        "earliest_restock_hit_fraction":result["earliest_restock_hit_fraction"],
        "proposal_coverage":result["proposal_coverage"],
        "output":str(out),
    },sort_keys=True))


if __name__=="__main__":
    main()
