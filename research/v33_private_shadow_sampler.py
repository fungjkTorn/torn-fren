"""V33 local-only prospective shadow sampler.

Each run attempts a new private observation for one or two explicitly approved
Canadian item keys. All attempts, INCLUDING failed HTTP / stale / rejected
snapshots, go into a separate shadow_capture_attempts ledger. Successful valid
responses also get the V31 timestamped shadow_decisions row. No API keys,
tokens, query strings, or raw forecast JSON are written to logs.

This utility NEVER touches the Torn foreign-stock database and NEVER sends
a public prediction. Schedule only *after* a successful manual one-shot run.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlencode

from research.v31_shadow_evidence_capture import record_private_decision

HOST="127.0.0.1"  # Intentionally non-configurable: never transmit private token remotely
PORT=8000
TOKEN_ENV="TORN_FREN_CHAMPION_SHADOW_TOKEN"
FLAG_ENV="TORN_FREN_CHAMPION_SHADOW_ENABLED"
NATIVE_ENV="TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED"
ALLOWED={"can:Bear Gall","can:Fire Hydrant"}
EXPERIMENT="canary-v33-20261008"

ATTEMPT_SCHEMA="""
CREATE TABLE IF NOT EXISTS shadow_capture_attempts (
    id INTEGER PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    item_key TEXT NOT NULL,
    tick_epoch INTEGER NOT NULL,
    attempted_at INTEGER NOT NULL,
    completed_at INTEGER,
    status TEXT NOT NULL,
    evidence_id INTEGER,
    UNIQUE(experiment_id,item_key,tick_epoch)
)
"""


class PrivateSamplingError(RuntimeError):
    pass


def fetch_private(country,item,token,*,connection_factory=http.client.HTTPConnection):
    """Loopback-only HTTP. No redirect-following; no external hostnames."""
    conn=connection_factory(HOST,PORT,timeout=65)
    try:
        uri="/api/research/champion-shadow?"+urlencode({"country":country,"item":item})
        conn.request("GET",uri,headers={"X-Torn-Fren-Shadow-Token":token})
        response=conn.getresponse()
        if response.status!=200:
            raise PrivateSamplingError("PRIVATE_HTTP_NON_200")
        raw=response.read(16385)
        if len(raw)>16384:
            raise PrivateSamplingError("PRIVATE_RESPONSE_TOO_LARGE")
        result=json.loads(raw)
        if not isinstance(result,dict) or result.get("key")!=country+":"+item:
            raise PrivateSamplingError("PRIVATE_RESPONSE_IDENTITY_MISMATCH")
        return result
    finally:
        conn.close()


def _open_ledger(path):
    path=Path(path).resolve()
    if path.exists():
        with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as probe:
            forbidden=probe.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND "
                "name IN ('stock_history','collection_gaps') LIMIT 1").fetchone()
        if forbidden:
            raise ValueError("refusing to open Torn collector database as evidence")
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=10)
    try:
        con.execute(ATTEMPT_SCHEMA)
        con.commit()
    except Exception:
        con.close()
        raise
    return con


def _start_attempt(con,experiment,key,now):
    tick=now//300*300
    with con:
        cur=con.execute(
            "INSERT OR IGNORE INTO shadow_capture_attempts "
            "(experiment_id,item_key,tick_epoch,attempted_at,status) "
            "VALUES (?,?,?,?,?)",
            (experiment,key,tick,now,"STARTED"))
    if cur.rowcount!=1:
        return None
    return int(cur.lastrowid)


def _finish_attempt(con,attempt_id,status,evidence_id=None,*,clock=time.time):
    with con:
        con.execute(
            "UPDATE shadow_capture_attempts "
            "SET completed_at=?,status=?,evidence_id=? "
            "WHERE id=? AND status='STARTED'",
            (int(clock()),status,evidence_id,attempt_id))


def capture_one(key,*,ledger,experiment,token,clock=time.time,
                fetcher=fetch_private):
    if key not in ALLOWED:
        raise ValueError("unapproved canary item")
    country,item=key.split(":",1)
    now=int(clock())
    with _open_ledger(ledger) as con:
        attempt=_start_attempt(con,experiment,key,now)
        if attempt is None:
            return {"item":key,"status":"DUPLICATE_FIVE_MINUTE_SLOT"}
        status="ERROR"
        id=None
        try:
            snap=fetcher(country,item,token)
            # The API generates this timestamp only at the END of prediction.
            # A delayed or stale response must never be saved as a fresh capture.
            generated=snap.get("generated_at")
            if type(generated) is not int or generated<now or generated>int(clock())+5:
                raise PrivateSamplingError("UNTRUSTED_GENERATION_TIMESTAMP")
            if generated//300 != now//300:
                raise PrivateSamplingError("CROSSED_FIVE_MINUTE_SLOT")
            if snap.get("key")!=key:
                raise PrivateSamplingError("PRIVATE_RESPONSE_IDENTITY_MISMATCH")
            evidence=record_private_decision(ledger,snap,experiment,now=int(clock()))
            status=evidence["status"]
            id=evidence["id"]
        except Exception as exc:
            # Deliberately print only exception CLASS, not args containing token
            # or internal private response content.
            status=("PRIVATE_REJECTED_"+str(exc)
                    if isinstance(exc,PrivateSamplingError)
                    and str(exc).isupper() and len(str(exc))<90
                    else "PRIVATE_FAILURE_"+type(exc).__name__)
        finally:
            _finish_attempt(con,attempt,status,id,clock=clock)
    return {"item":key,"status":status,"captured":bool(id)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-db",required=True)
    p.add_argument("--experiment",default=EXPERIMENT)
    p.add_argument("--item",action="append",required=True,choices=sorted(ALLOWED))
    args=p.parse_args()
    if len(args.item)!=len(set(args.item)) or len(args.item)>2:
        p.error("at most two unique approved items per sampling run")
    if not args.experiment or len(args.experiment)>64 or not all(
        c.isalnum() or c in "-_." for c in args.experiment
    ):
        p.error("invalid experiment identity")
    env=os.environ
    if env.get(FLAG_ENV)!="1" or env.get(NATIVE_ENV)!="1":
        p.error("private AND native research gates must be enabled")
    token=env.get(TOKEN_ENV,"")
    if len(token)<32:
        p.error("missing private token in protected service environment")
    target=Path(args.evidence_db).resolve()
    # Evidence store must remain separate from code and Torn data by convention.
    if target.name in ("stock_history.db","torn-fren-stock-history-fresh.db"):
        p.error("cannot use the live collector database as evidence")
    results=[capture_one(key,ledger=target,experiment=args.experiment,token=token)
             for key in args.item]
    for item in results:
        print(json.dumps(item,sort_keys=True),flush=True)
    if any(r["status"].startswith(("PRIVATE_FAILURE","PRIVATE_REJECTED"))
           for r in results):
        raise SystemExit(1)


if __name__=="__main__":
    main()
