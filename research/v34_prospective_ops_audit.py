"""Read-only V34 prospective audit for the live V33 private shadow ledger.

Scores completed, timestamped five-minute recommendations, not hypothetical
replanned routes. Records failed capture attempts and explicitly expected-but-
missing scheduled ticks in conservative operational success denominators.

No writes to the Torn stock DB or the private capture DB. No promotion claims.
Independent restock-window validation is NOT certified by this version.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

QUANTITY=30
GRACE=10
MAX_POLL_GAP=180
TRAVEL={"mex":1020,"cay":1380,"can":1620,"haw":5340,"uni":6360,
        "arg":6660,"swi":6960,"jap":8940,"chi":9600,"uae":10800,"sou":11820}
MIN_REQUIRED_TABLES={"stock_history","poll_heartbeats","collection_gaps"}
CAPTURE_TABLES={"shadow_capture_attempts","shadow_decisions"}


def _readonly(path):
    path=Path(path).resolve(strict=True)
    return sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=15)


def _table_names(con):
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _one(con,sql,args):
    return con.execute(sql,args).fetchone()


def _known_gap(con,start,end):
    return _one(con,"""SELECT 1 FROM collection_gaps
        WHERE start_timestamp<=?
        AND COALESCE(end_timestamp,9223372036854775807)>=?
        LIMIT 1""",(end,start)) is not None


def arrival_truth(con,country,item,arrival,asof):
    """Conservative arrival/+10s bracket; never query beyond the requested asof."""
    if asof<arrival+GRACE+MAX_POLL_GAP:
        return ("PENDING",None)
    pre=_one(con,"""SELECT timestamp,quantity FROM stock_history
       WHERE country=? AND item_name=? AND timestamp<=?
       ORDER BY timestamp DESC,id DESC LIMIT 1""",(country,item,arrival))
    post=_one(con,"""SELECT timestamp,quantity FROM stock_history
       WHERE country=? AND item_name=? AND timestamp>=? AND timestamp<=?
       ORDER BY timestamp ASC,id ASC LIMIT 1""",
       (country,item,arrival+GRACE,asof))
    if pre is None or post is None:
        return ("UNSCORABLE_NO_BRACKETING_STOCK",None)
    if arrival-int(pre[0])>MAX_POLL_GAP or int(post[0])-arrival-GRACE>MAX_POLL_GAP:
        return ("UNSCORABLE_STOCK_COVERAGE",None)
    polls=_one(con,"""SELECT
       (SELECT MAX(timestamp) FROM poll_heartbeats
        WHERE mode='poll-cycle' AND success=1 AND timestamp<=?),
       (SELECT MIN(timestamp) FROM poll_heartbeats
        WHERE mode='poll-cycle' AND success=1 AND timestamp>=? AND timestamp<=?)
       """,(arrival,arrival+GRACE,asof))
    if polls[0] is None or polls[1] is None:
        return ("UNSCORABLE_POLL_COVERAGE",None)
    if arrival-polls[0]>MAX_POLL_GAP or polls[1]-arrival-GRACE>MAX_POLL_GAP:
        return ("UNSCORABLE_POLL_COVERAGE",None)
    if _known_gap(con,int(pre[0]),int(post[0])):
        return ("UNSCORABLE_KNOWN_COLLECTION_GAP",None)
    a=int(pre[1])>=QUANTITY
    b=int(post[1])>=QUANTITY
    if a!=b:
        return ("UNSCORABLE_TRANSITION_NEAR_ARRIVAL",None)
    return ("SUCCESS",True) if a else ("MISS",False)


def _proposal_result(con,country,item,generated,recorded,departure,arrival,asof,max_wait):
    if departure is None or arrival is None:
        return ("NO_ACTIONABLE_DEPARTURE",False)
    dep=int(departure); arr=int(arrival)
    if (dep<recorded or dep>generated+max_wait or
        arr<=dep or arr-dep!=TRAVEL[country]):
        return ("INVALID_OR_EXPIRED_DEPARTURE",False)
    return arrival_truth(con,country,item,arr,asof)


def _completed_windows(con,country,item,freeze,asof):
    """Observational diagnostic only: qualified high-stock segments are NOT
    formally certified as independent cycles or proof of model performance."""
    rows=con.execute("""SELECT timestamp,quantity FROM stock_history
        WHERE country=? AND item_name=? AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp,id""",(country,item,freeze,asof)).fetchall()
    active=None
    previous=None
    done=[]
    for ts,qty in rows:
        ts=int(ts);high=int(qty)>=QUANTITY
        if previous is None:
            previous=(ts,high)
            continue
        last,last_high=previous
        if ts-last>MAX_POLL_GAP or _known_gap(con,last,ts):
            active=None
            previous=(ts,high)
            continue
        if not last_high and high:
            active=ts
        elif last_high and not high and active is not None:
            done.append([active,last,ts])
            active=None
        previous=(ts,high)
    return done


def audit(evidence_db,stock_db,*,experiment,freeze_epoch,asof_epoch,
          scheduled_from_epoch,policy_max_wait=43200,items=None,
          schedule_stride_seconds=300):
    if (not experiment or freeze_epoch<=0 or asof_epoch<freeze_epoch or
        policy_max_wait<300 or policy_max_wait>43200):
        raise ValueError("invalid temporal or experimental configuration")
    if scheduled_from_epoch is not None and (
        scheduled_from_epoch<freeze_epoch or scheduled_from_epoch%300!=60
    ):
        raise ValueError("scheduled_from must represent an actual :01/:06/... minute")
    if schedule_stride_seconds not in (300,1200):
        raise ValueError("unsupported explicitly scheduled item stride")
    if Path(evidence_db).resolve()==Path(stock_db).resolve():
        raise ValueError("evidence and collector DB must be separate")
    output={"schema":"torn-fren-v34-strict-prospective-ops-audit-v1",
            "experiment":experiment,"freeze_epoch":freeze_epoch,
            "asof_epoch":asof_epoch,
            "scheduled_from_epoch":scheduled_from_epoch,
            "policy_max_wait_seconds":policy_max_wait,
            "schedule_stride_seconds":schedule_stride_seconds,
            "read_only":True,"promotions_approved":0,
            "independent_window_certified":False,"items":{}}
    with _readonly(evidence_db) as ev, _readonly(stock_db) as stock:
        if not CAPTURE_TABLES.issubset(_table_names(ev)):
            raise ValueError("missing required V33 private evidence tables")
        if not MIN_REQUIRED_TABLES.issubset(_table_names(stock)):
            raise ValueError("missing required Torn collector tables")
        attempts=ev.execute("""SELECT id,item_key,tick_epoch,attempted_at,completed_at,
                status,evidence_id FROM shadow_capture_attempts
                WHERE experiment_id=? ORDER BY item_key,tick_epoch""",
                (experiment,)).fetchall()
        forecasts=ev.execute("""SELECT id,item_key,tick_epoch,recorded_at,
                source_generated_at,challenger_status,challenger_executed,
                challenger_departure,challenger_arrival,
                v2_status,v2_departure,v2_arrival
                FROM shadow_decisions WHERE experiment_id=?""",(experiment,)).fetchall()
        decisions={(r[1],r[2]):r for r in forecasts}
        attempt_by_item=defaultdict(list)
        for r in attempts:
            attempt_by_item[r[1]].append(r)
        observed_keys=set(attempt_by_item)|{r[1] for r in forecasts}
        if items:
            observed_keys|=set(items)
        if not observed_keys:
            raise ValueError("no captured attempts or configured item keys")
        for key in sorted(observed_keys):
            if ":" not in key or key.split(":",1)[0] not in TRAVEL:
                raise ValueError("invalid item key")
            country,item=key.split(":",1)
            window_horizon=policy_max_wait+TRAVEL[country]+GRACE+MAX_POLL_GAP
            eligible=[]
            statuses=Counter()
            attempts_for_key=attempt_by_item[key]
            attempted_ticks={r[2] for r in attempts_for_key}
            seen_decisions=set()
            for id,_,tick,attempted,completed,status,evidence_id in attempts_for_key:
                if attempted>asof_epoch or attempted<freeze_epoch:
                    statuses["EXCLUDED_OUTSIDE_FREEZE_OR_ASOF"]+=1
                    continue
                decision=decisions.get((key,tick))
                if decision:
                    seen_decisions.add((key,tick))
                if attempted+window_horizon>asof_epoch:
                    statuses["PENDING_HORIZON"]+=1
                    continue
                entry={"tick":tick,"attempt_status":status,
                       "challenger":("CAPTURE_FAILED",False),
                       "v2":("CAPTURE_FAILED",False)}
                if (status=="RECORDED" and decision and
                    evidence_id==decision[0]):
                    (_,_,_,recorded,generated,cstatus,executed,
                     cdep,carr,vstatus,vdep,varr)=decision
                    if (recorded<attempted or recorded>asof_epoch or
                        generated<attempted or generated>recorded or
                        recorded-generated>180 or
                        generated//300!=tick//300):
                        entry["challenger"]=("INVALID_CAPTURE_TIMESTAMPS",False)
                        entry["v2"]=("INVALID_CAPTURE_TIMESTAMPS",False)
                    else:
                        if executed==1 and cstatus=="RESEARCH_PROPOSAL_ONLY":
                            entry["challenger"]=_proposal_result(
                                stock,country,item,generated,recorded,
                                cdep,carr,asof_epoch,policy_max_wait)
                        else:
                            entry["challenger"]=("NO_CHALLENGER_RECOMMENDATION",False)
                        entry["v2"]=_proposal_result(stock,country,item,generated,
                            recorded,vdep,varr,asof_epoch,policy_max_wait)
                else:
                    entry["challenger"]=("NO_VALID_CAPTURE",False)
                    entry["v2"]=("NO_VALID_CAPTURE",False)
                eligible.append(entry)
                statuses[status]+=1
            # Do not silently discard orphaned decisions; flag for investigation.
            orphans=sum(1 for r in forecasts if r[1]==key
                         and (r[1],r[2]) not in seen_decisions)
            if orphans:
                statuses["ORPHANED_DECISIONS"]+=orphans
            missing_ticks=[]
            if scheduled_from_epoch is not None:
                # The timer fires at :01/:06 etc; its evidence tick is :00/:05.
                # Allow 180 sec after its scheduled call before flagging absent.
                for scheduled in range(scheduled_from_epoch,asof_epoch-179,schedule_stride_seconds):
                    tick=scheduled//300*300
                    if tick not in attempted_ticks:
                        missing_ticks.append(tick)
                        if tick+window_horizon<=asof_epoch:
                            eligible.append({"tick":tick,"attempt_status":"MISSING_TIMER_TICK",
                                "challenger":("MISSING_TIMER_TICK",False),
                                "v2":("MISSING_TIMER_TICK",False)})
                statuses["MISSING_TIMER_TICKS"]+=len(missing_ticks)
            n=len(eligible)
            def metrics(which):
                resolved=sum(1 for x in eligible if x[which][1] is not None)
                wins=sum(1 for x in eligible if x[which][1] is True)
                unscorable=sum(1 for x in eligible if x[which][1] is None)
                recommendations=sum(1 for x in eligible
                    if x[which][0] in ("SUCCESS","MISS"))
                return {"confirmed_success":wins,"matured_opportunities":n,
                        "conservative_success_lower_bound":wins/n if n else None,
                        "resolved_or_penalized":resolved,
                        "unknown_outcomes":unscorable,
                        "verified_arrival_recommendations":recommendations,
                        "recorded_arrival_rate":wins/recommendations if recommendations else None,
                        "actionable_coverage":recommendations/n if n else None}
            completed_windows=_completed_windows(stock,country,item,freeze_epoch,asof_epoch)
            output["items"][key]={
                "attempts":len(attempts_for_key),
                "valid_decisions":sum(1 for r in forecasts if r[1]==key),
                "expected_timer_ticks": (
                  max(0,(asof_epoch-180-scheduled_from_epoch)//schedule_stride_seconds+1)
                  if scheduled_from_epoch is not None and
                     asof_epoch>=scheduled_from_epoch+180 else None),
                "missing_timer_ticks":len(missing_ticks),
                "matured_attempts_or_missing_ticks":n,
                "pending_attempts":statuses["PENDING_HORIZON"],
                "status_counts":dict(sorted(statuses.items())),
                "v21":metrics("challenger"),
                "v2":metrics("v2"),
                "observed_completed_high_stock_segments_diagnostic_only":len(completed_windows),
                "independent_window_certified":False,
                "eligible_row_summaries":[
                    {"tick":x["tick"],"capture":x["attempt_status"],
                     "v21_result":x["challenger"][0],"v2_result":x["v2"][0]}
                     for x in eligible],
            }
    output["note"]=(
        "Only preexisting, prospective captures; no evaluation of arrivals until "
        "the entire frozen horizon matures. Missing scheduled ticks and failed "
        "captures count against conservative operational success; unscorable "
        "stock/poll intervals do not become false confirmed wins. "
        "Five-minute starts are correlated and do NOT certify independent cycles."
    )
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-db",required=True)
    p.add_argument("--stock-db",required=True)
    p.add_argument("--experiment",default="pilot-beargall-v33")
    p.add_argument("--freeze-epoch",type=int,required=True)
    p.add_argument("--scheduled-from-epoch",type=int,
                   help="Actual first eligible five-minute systemd timer firing")
    p.add_argument("--asof-epoch",type=int)
    p.add_argument("--max-wait-seconds",type=int,default=43200)
    p.add_argument("--item",action="append",default=[])
    p.add_argument("--schedule-stride-seconds",type=int,default=300,
                   choices=(300,1200))
    p.add_argument("--output",help="Optional new JSON report; refuses overwrite")
    args=p.parse_args()
    asof=int(time.time()) if args.asof_epoch is None else args.asof_epoch
    report=audit(args.evidence_db,args.stock_db,experiment=args.experiment,
                 freeze_epoch=args.freeze_epoch,asof_epoch=asof,
                 scheduled_from_epoch=args.scheduled_from_epoch,
                 policy_max_wait=args.max_wait_seconds,items=args.item,
                 schedule_stride_seconds=args.schedule_stride_seconds)
    summary={k:{f:v for f,v in result.items() if f not in
        ("eligible_row_summaries",)}
        for k,result in report["items"].items()}
    print(json.dumps({"schema":report["schema"],"items":summary,
          "independent_window_certified":False},indent=2))
    if args.output:
        dest=Path(args.output)
        if dest.exists():
            p.error("report already exists; refusing overwrite")
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
