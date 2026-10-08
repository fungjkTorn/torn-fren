"""V36 isolated, round-robin prospective museum/Japan capture.

Designed specifically to avoid expensive private V2 recomputation in the
public FastAPI process. ONE item per five-minute systemd timer firing:
Heather (frozen V18), Wolverine (frozen V18), Nessie (baseline only), Japan
Xanax (baseline only), then repeat. Each item is observed every 20 min.

Native V18 uses a read-only child worker with a hard timeout. V2 is sampled
from the existing bounded/nonblocking /api/history route (may be warming).
Never use a slow private shadow endpoint, credentials, gameplay APIs, or
Torn's collector DB for writes. Store both complete and missed predictions.
"""
from __future__ import annotations
import argparse
import http.client
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from research.v31_shadow_evidence_capture import CREATE_TABLE, SOURCE_SCHEMA
from research.v33_private_shadow_sampler import (
    _open_ledger, _start_attempt, _finish_attempt
)

ORDER=("uni:Heather","can:Wolverine Plushie",
       "uni:Nessie Plushie","jap:Xanax")
NATIVE={"uni:Heather":"dyn3","can:Wolverine Plushie":"dyn8"}
TRAVEL={"uni":6360,"can":1620,"jap":8940}
PILOT="pilot-museum-japan-v36"
NATIVE_TIMEOUT=38
WEB_TIMEOUT=10
MAX_RESPONSE_BYTES=1024*1024


def scheduled_item(epoch):
    return ORDER[(int(epoch)//300)%len(ORDER)]


def _v2_from_public_history(country,item,*,connection_factory=http.client.HTTPConnection):
    """GET only the public, bounded, nonblocking history route. No token."""
    conn=connection_factory("127.0.0.1",8000,timeout=WEB_TIMEOUT)
    try:
        uri="/api/history?"+urlencode(
            {"country":country,"item":item,"minutes":60})
        conn.request("GET",uri)
        response=conn.getresponse()
        if response.status!=200:
            return {"status":"PUBLIC_HISTORY_UNAVAILABLE"}
        raw=response.read(MAX_RESPONSE_BYTES+1)
        if len(raw)>MAX_RESPONSE_BYTES:
            return {"status":"PUBLIC_HISTORY_TOO_LARGE"}
        obj=json.loads(raw)
        if obj.get("country")!=country or obj.get("item")!=item:
            return {"status":"PUBLIC_HISTORY_IDENTITY_MISMATCH"}
        analysis=obj.get("analysis") or {}
        p=analysis.get("prediction_v2") or {}
        if not isinstance(p,dict):
            return {"status":"V2_UNAVAILABLE"}
        display=p.get("display_prediction") or {}
        if display and type(display.get("recommended_leave_by_timestamp")) in (int,float):
            return {"status":("available_stale" if analysis.get("prediction_v2_stale") is True
                                 else "available"),
                "recommended_leave_by_timestamp":int(display["recommended_leave_by_timestamp"]),
                "recommended_arrival_timestamp":(
                   int(display["recommended_arrival_timestamp"])
                   if type(display.get("recommended_arrival_timestamp")) in (int,float)
                   else None)}
        return {"status":str(p.get("status") or "V2_WARMING_OR_UNAVAILABLE")[:75]}
    except TimeoutError:
        return {"status":"PUBLIC_HISTORY_TIMEOUT"}
    except (OSError,ValueError,json.JSONDecodeError):
        return {"status":"PUBLIC_HISTORY_CONNECTION_OR_FORMAT_ERROR"}
    finally:
        conn.close()


def _native_single_tick(db,key,now,*,runner=subprocess.run):
    if key not in NATIVE:
        return {"status":"SPECIALIST_NOT_INTEGRATED","champion_executed":False}
    country,item=key.split(":",1)
    args=[sys.executable,"-m","services.private_v18_champion_worker_v35",
          "--db",str(db),"--country",country,"--item",item,
          "--config",NATIVE[key],"--now",str(now)]
    try:
        job=runner(args,capture_output=True,text=True,
                   timeout=NATIVE_TIMEOUT,check=False)
        if job.returncode or len(job.stdout)>8192:
            return {"status":"NATIVE_WORKER_ERROR","champion_executed":False}
        result=json.loads(job.stdout)
        if not isinstance(result,dict):
            raise ValueError("invalid response")
        if result.get("status")!="RESEARCH_PROPOSAL_ONLY":
            return {"status":str(result.get("status") or "NATIVE_NO_RESULT")[:75],
                    "champion_executed":False}
        dep=result.get("recommended_departure_timestamp")
        arr=result.get("recommended_arrival_timestamp")
        if (result.get("key")!=key or result.get("model_generation")!="V18" or
            result.get("model_config")!=NATIVE[key] or
            result.get("probability_calibrated") is not False or
            type(dep) is not int or type(arr) is not int or
            dep<now or dep>now+28800 or arr-dep!=TRAVEL[country] or
            result.get("replan_step_seconds")!=300 or
            result.get("research_horizon_seconds")!=28800):
            return {"status":"NATIVE_RESULT_REJECTED","champion_executed":False}
        return {"status":"RESEARCH_PROPOSAL_ONLY","champion_executed":True,
                "departure":dep,"arrival":arr,"config":NATIVE[key]}
    except subprocess.TimeoutExpired:
        return {"status":"NATIVE_WORKER_TIMEOUT","champion_executed":False}
    except (OSError,ValueError,json.JSONDecodeError):
        return {"status":"NATIVE_WORKER_ERROR","champion_executed":False}


def _record_direct(con,experiment,key,tick,attempted,generated,model,baseline,
                   native):
    """Insert a V36 provenance row into the established research-only ledger."""
    con.execute(CREATE_TABLE)
    native_ok=native.get("status")=="RESEARCH_PROPOSAL_ONLY" and native.get("champion_executed") is True
    b_dep=baseline.get("recommended_leave_by_timestamp")
    b_arr=baseline.get("recommended_arrival_timestamp")
    if (type(b_dep) is not int or type(b_arr) is not int or
        b_dep<generated or b_arr<=b_dep or b_arr-b_dep!=TRAVEL[key[:3]]):
        b_dep=b_arr=None
    values=(experiment,key,tick,generated,
            "torn-fren-v36-isolated-native-with-public-v2-reference",
            generated,model,native.get("config") or NATIVE.get(key) or "",
            native.get("status") or "UNKNOWN",int(native_ok),
            native.get("departure") if native_ok else None,
            native.get("arrival") if native_ok else None,
            baseline.get("status") or "V2_UNAVAILABLE",
            b_dep,b_arr,1,1)
    with con:
        cur=con.execute("""
        INSERT OR IGNORE INTO shadow_decisions
        (experiment_id,item_key,tick_epoch,recorded_at,source_schema,
         source_generated_at,candidate_model_family,candidate_config,challenger_status,
         challenger_executed,challenger_departure,challenger_arrival,v2_status,
         v2_departure,v2_arrival,source_is_private,live_routing_unchanged)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,values)
        row=con.execute("SELECT id FROM shadow_decisions "
                        "WHERE experiment_id=? AND item_key=? AND tick_epoch=?",
                        (experiment,key,tick)).fetchone()
    return int(row[0]),cur.rowcount==1


def capture(key,*,db,ledger,experiment=PILOT,clock=time.time,
            native_fn=_native_single_tick,v2_fn=_v2_from_public_history):
    if key not in ORDER:
        raise ValueError("not an approved private pilot item")
    if Path(db).resolve()==Path(ledger).resolve():
        raise ValueError("evidence cannot be collector")
    country,item=key.split(":",1)
    now=int(clock())
    with _open_ledger(ledger) as con:
        attempt=_start_attempt(con,experiment,key,now)
        if attempt is None:
            return {"item":key,"status":"DUPLICATE_FIVE_MINUTE_SLOT"}
        status="UNRECORDED"
        evidence_id=None
        try:
            # Model first; bounded child process, no HTTP.
            native=native_fn(db,key,now)
            # Cheap public HTTP baseline, never V2 raw profile computation.
            baseline=v2_fn(country,item)
            generated=int(clock())
            if generated//300!=now//300 or generated<now:
                status="CROSSED_FIVE_MINUTE_SLOT"
            else:
                evidence_id,inserted=_record_direct(
                    con,experiment,key,now//300*300,now,generated,
                    "V18" if key in NATIVE else
                    ("japan_xanax_specialist" if key=="jap:Xanax"
                     else "recent_phase_template"),
                    baseline,native)
                status="RECORDED" if inserted else "DUPLICATE_DECISION"
        except Exception as exc:
            status="CAPTURE_ERROR_"+type(exc).__name__
        finally:
            _finish_attempt(con,attempt,status,evidence_id,clock=clock)
    return {"item":key,"status":status,
            "native_status":native.get("status") if evidence_id else None,
            "v2_status":baseline.get("status") if evidence_id else None,
            "champion_executed":native.get("champion_executed") if evidence_id else False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--evidence-db",required=True)
    p.add_argument("--experiment",default=PILOT)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--rotate",action="store_true")
    mode.add_argument("--item",choices=ORDER)
    a=p.parse_args()
    if not a.experiment or len(a.experiment)>64 or not all(
       x.isalnum() or x in "._-" for x in a.experiment):
        p.error("invalid experiment identity")
    if not Path(a.db).is_file():
        p.error("stock DB missing")
    item=scheduled_item(int(time.time())) if a.rotate else a.item
    result=capture(item,db=a.db,ledger=a.evidence_db,experiment=a.experiment)
    print(json.dumps(result,sort_keys=True),flush=True)
    if result["status"] not in ("RECORDED","DUPLICATE_FIVE_MINUTE_SLOT"):
        raise SystemExit(1)


if __name__=="__main__":main()
