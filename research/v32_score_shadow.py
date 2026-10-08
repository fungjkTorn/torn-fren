"""V32 strictly read-only resolution of prospectively captured private shadow decisions.

Outputs a JSON audit; never updates either SQLite DB. Refuses to count old
researched data as independent prospective evidence. A model succeeds only
when sufficient pre/post arrival observations confirm >=30 stock through the
arrival/+10s window without an ambiguous transition or collector gap.

This intentionally scores ONE recorded single-tick proposal, not an unrecorded
replanning policy. Multi-tick decisions must be captured prospectively.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

QUANTITY=30
GRACE=10
MAX_OBSERVATION_GAP=180
TRAVEL={"mex":1620,"cay":2100,"can":2460,"haw":3960,"uni":5580,
        "arg":6660,"swi":6660,"jap":8940,"chi":9840,"uae":10020,"sou":10320}
# Known original model travel values should be audited against the
# source planner before being used for any live decision.
ALL_TABLES=("stock_history","poll_heartbeats","collection_gaps")


def _conn(path: str|Path):
    source=Path(path).resolve(strict=True)
    return sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)


def _sha(path):
    d=hashlib.sha256()
    with open(path,"rb") as stream:
        for b in iter(lambda:stream.read(1048576),b""):
            d.update(b)
    return d.hexdigest()


def _stock_bracket(con,country,item,arrival):
    a=con.execute("""
         SELECT timestamp,quantity FROM stock_history
         WHERE country=? AND item_name=? AND timestamp<=?
         ORDER BY timestamp DESC,id DESC LIMIT 1""",
         (country,item,arrival)).fetchone()
    b=con.execute("""
         SELECT timestamp,quantity FROM stock_history
         WHERE country=? AND item_name=? AND timestamp>=?
         ORDER BY timestamp ASC,id ASC LIMIT 1""",
         (country,item,arrival+GRACE)).fetchone()
    return a,b


def _nearby_poll_coverage(con,arrival):
    a=con.execute("""
       SELECT MAX(timestamp) FROM poll_heartbeats
       WHERE mode='poll-cycle' AND success=1 AND timestamp<=?""",
       (arrival,)).fetchone()[0]
    b=con.execute("""
       SELECT MIN(timestamp) FROM poll_heartbeats
       WHERE mode='poll-cycle' AND success=1 AND timestamp>=?""",
       (arrival+GRACE,)).fetchone()[0]
    return a,b


def _overlaps_known_gap(con,start,end):
    return bool(con.execute("""
      SELECT 1 FROM collection_gaps
      WHERE start_timestamp<=? AND COALESCE(end_timestamp,9223372036854775807)>=?
      LIMIT 1""",(end,start)).fetchone())


def arrival_truth(con,country,item,arrival,asof):
    arrival=int(arrival)
    if asof < arrival+GRACE+MAX_OBSERVATION_GAP:
        return {"status":"PENDING","success":None}
    pre,post=_stock_bracket(con,country,item,arrival)
    if pre is None or post is None:
        return {"status":"UNSCORABLE_NO_BRACKETING_STOCK","success":None}
    if arrival-int(pre[0])>MAX_OBSERVATION_GAP or int(post[0])-(arrival+GRACE)>MAX_OBSERVATION_GAP:
        return {"status":"UNSCORABLE_STOCK_GAP","success":None}
    poll0,poll1=_nearby_poll_coverage(con,arrival)
    if poll0 is None or poll1 is None or arrival-poll0>MAX_OBSERVATION_GAP or poll1-(arrival+GRACE)>MAX_OBSERVATION_GAP:
        return {"status":"UNSCORABLE_COLLECTOR_GAP","success":None}
    if _overlaps_known_gap(con,int(pre[0]),int(post[0])):
        return {"status":"UNSCORABLE_KNOWN_GAP","success":None}
    low=int(pre[1])>=QUANTITY
    high=int(post[1])>=QUANTITY
    if low!=high:
        return {"status":"UNSCORABLE_TRANSITION_NEAR_ARRIVAL","success":None}
    return {"status":"RESOLVED_SUCCESS" if low else "RESOLVED_MISS",
            "success":low, "pre_stock_time":int(pre[0]),
            "post_stock_time":int(post[0])}


def score_capture(evidence_db,stock_db,*,experiment,freeze_epoch,asof_epoch,
                  max_wait_seconds=28800):
    if not experiment or max_wait_seconds<300:
        raise ValueError("invalid experiment/horizon")
    if Path(evidence_db).resolve()==Path(stock_db).resolve():
        raise ValueError("evidence cannot be collector db")
    if asof_epoch<freeze_epoch:
        raise ValueError("asof precedes freeze")
    out={"schema":"torn-fren-v32-prospective-single-tick-audit-v1",
         "experiment":experiment,"freeze_epoch":int(freeze_epoch),
         "asof_epoch":int(asof_epoch),"source_stock_sha256":_sha(stock_db),
         "evidence_sha256":_sha(evidence_db),
         "read_only":True,"model_promotion_approved":False,"items":{}}
    with _conn(evidence_db) as e, _conn(stock_db) as con:
        types={row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(ALL_TABLES).issubset(types):
            raise ValueError("missing collector tables")
        if "shadow_decisions" not in {r[0] for r in e.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}:
            raise ValueError("missing prospective evidence table")
        rows=e.execute("""
          SELECT id,item_key,tick_epoch,recorded_at,source_generated_at,
                 challenger_status,challenger_executed,challenger_departure,
                 challenger_arrival,v2_status,v2_departure,v2_arrival
          FROM shadow_decisions
          WHERE experiment_id=? ORDER BY item_key,tick_epoch,id
        """,(experiment,)).fetchall()
        grouped=defaultdict(list)
        for row in rows:
            id,key,tick,recorded,generated,cstatus,executed,cdep,carr,vstatus,vdep,varr=row
            country,item=key.split(":",1)
            entry={"id":id,"tick":tick,"source_generated_at":generated,
                   "challenger_status":cstatus}
            if generated<freeze_epoch or generated>recorded or recorded-generated>180:
                entry["status"]="EXCLUDED_PRE_FREEZE_OR_INVALID_CAPTURE"
                grouped[key].append(entry);continue
            # Entire potential travel+waiting horizon must have elapsed before
            # counting NO_RECOMMENDATION as an attempted recommendation.
            mature_at=generated+max_wait_seconds+TRAVEL.get(country,10320)+GRACE+MAX_OBSERVATION_GAP
            if asof_epoch<mature_at:
                entry["status"]="PENDING_SESSION_HORIZON"
                grouped[key].append(entry);continue
            if executed and cdep is not None and carr is not None:
                if cdep<generated or cdep>generated+max_wait_seconds or carr<=cdep:
                    entry["status"]="INVALID_RECOMMENDATION"
                else:
                    entry["status"]="CHALLENGER_"+arrival_truth(con,country,item,carr,asof_epoch)["status"]
                    entry["arrival"]=carr
                    truth=arrival_truth(con,country,item,carr,asof_epoch)
                    entry["challenger_success"]=truth["success"]
            else:
                entry["status"]="NO_CHALLENGER_RECOMMENDATION"
                entry["challenger_success"]=False
            if vdep is not None and varr is not None and vdep>=generated:
                bt=arrival_truth(con,country,item,varr,asof_epoch)
                entry["v2_status"]=bt["status"]
                entry["v2_success"]=bt["success"]
            grouped[key].append(entry)
        for key,entries in sorted(grouped.items()):
            resolved=[x for x in entries if x.get("challenger_success") is not None
                      and x.get("status") in ("CHALLENGER_RESOLVED_SUCCESS",
                                           "CHALLENGER_RESOLVED_MISS",
                                           "NO_CHALLENGER_RECOMMENDATION")]
            success=sum(x.get("challenger_success") is True for x in resolved)
            recommendations=sum(x["status"].startswith("CHALLENGER_RESOLVED") for x in resolved)
            n=len(resolved)
            out["items"][key]={
                "captured":len(entries),
                "resolved_eligible_sessions":n,
                "successful_arrivals":success,
                "all_start_success":success/n if n else None,
                "recommendations":recommendations,
                "coverage":recommendations/n if n else None,
                "unscorable_or_pending":len(entries)-n,
                "qualified_independent_windows":None,
                "independent_window_certified":False,
                "rows":entries,
            }
    out["totals"]={
        "items_with_prospectively_scored_sessions":sum(
             x["resolved_eligible_sessions"]>0 for x in out["items"].values()),
        "provisional_winners_approved":0,
        "note":"No independent stock-window certification; clustered start rows must not be treated as independent stock events.",
    }
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence-db",required=True)
    p.add_argument("--stock-db",required=True)
    p.add_argument("--experiment",required=True)
    p.add_argument("--freeze-epoch",type=int,required=True)
    p.add_argument("--asof-epoch",type=int,required=True)
    p.add_argument("--max-wait-seconds",type=int,default=28800)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=score_capture(a.evidence_db,a.stock_db,experiment=a.experiment,
          freeze_epoch=a.freeze_epoch,asof_epoch=a.asof_epoch,
          max_wait_seconds=a.max_wait_seconds)
    target=Path(a.output)
    if target.exists():p.error("refusing to replace previous evidence report")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result["totals"],indent=2))


if __name__=="__main__":
    main()
